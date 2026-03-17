from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from typing import Dict

import pandas as pd
import redis.asyncio as redis

from backend.broker.order_executor import OrderExecutor
from backend.broker.order_executor import Signal as ExecutorSignal
from backend.config import AppConfig
from backend.models.database import SessionLocal
from backend.models.models import Signal as SignalModel
from backend.risk.portfolio_state import PortfolioState
from backend.strategies.base_strategy import BaseStrategy, Signal
from backend.strategies.momentum_breakout import MomentumBreakout
from backend.strategies.stat_mean_reversion import StatMeanReversion
from backend.strategies.sentiment_catalyst import SentimentCatalyst

logger = logging.getLogger(__name__)


class StrategyEngine:
    """
    Orchestrates active strategies, enforcing per-ticker exclusivity and
    scheduling evaluations during market hours.
    """

    def __init__(
        self,
        cfg: AppConfig,
        redis_client: redis.Redis,
        portfolio_state: PortfolioState,
        order_executor: OrderExecutor,
    ):
        self.cfg = cfg
        self.redis = redis_client
        self.portfolio_state = portfolio_state
        self.order_executor = order_executor

        self.strategies: Dict[str, BaseStrategy] = {}
        mb_cfg = cfg.strategies.get("momentum_breakout")
        if mb_cfg and mb_cfg.enabled:
            self.strategies["momentum_breakout"] = MomentumBreakout(
                risk_per_trade_pct=mb_cfg.risk_per_trade_pct
            )

        smr_cfg = cfg.strategies.get("stat_mean_reversion")
        if smr_cfg and smr_cfg.enabled:
            self.strategies["stat_mean_reversion"] = StatMeanReversion(
                risk_per_trade_pct=smr_cfg.risk_per_trade_pct
            )

        sc_cfg = cfg.strategies.get("sentiment_catalyst")
        if sc_cfg and sc_cfg.enabled:
            self.strategies["sentiment_catalyst"] = SentimentCatalyst(
                risk_per_trade_pct=sc_cfg.risk_per_trade_pct,
                max_positions=sc_cfg.max_concurrent,
            )

        self._ticker_owner: Dict[str, str] = {}
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        loop = asyncio.get_event_loop()
        # 5-minute scheduler for MomentumBreakout
        self._tasks.append(loop.create_task(self._run_momentum_breakout()))
        # 15-minute scheduler for StatMeanReversion
        if "stat_mean_reversion" in self.strategies:
            self._tasks.append(loop.create_task(self._run_stat_mean_reversion()))
        # SentimentCatalyst reacts to news events
        if "sentiment_catalyst" in self.strategies:
            self._tasks.append(loop.create_task(self._run_sentiment_catalyst()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    async def _run_momentum_breakout(self) -> None:
        """
        Every 5 minutes during market hours, collect recent data and run
        the MomentumBreakout strategy.
        """
        while True:
            now = datetime.utcnow()
            if self._is_market_hours(now):
                await self._evaluate_momentum_breakout()
            await asyncio.sleep(300)

    async def _run_stat_mean_reversion(self) -> None:
        """
        Every 15 minutes during market hours, collect recent 15m data and run
        the StatMeanReversion strategy.
        """
        while True:
            now = datetime.utcnow()
            if self._is_market_hours(now):
                await self._evaluate_stat_mean_reversion()
            await asyncio.sleep(900)

    async def _run_sentiment_catalyst(self) -> None:
        """
        Polls the Redis news event queue and turns strong sentiment events
        into SentimentCatalyst signals.
        """
        queue_key = "news:events"
        strat = self.strategies.get("sentiment_catalyst")
        if strat is None or not isinstance(strat, SentimentCatalyst):
            return
        while True:
            now = datetime.utcnow()
            if not self._is_market_hours(now):
                await asyncio.sleep(30)
                continue
            events: list[dict] = []
            # Drain up to N events from the queue
            for _ in range(20):
                raw = await self.redis.lpop(queue_key)
                if not raw:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    ev = pd.read_json(raw, typ="series").to_dict()
                except Exception:
                    continue
                events.append(ev)
            if events:
                await self._evaluate_sentiment_catalyst_events(strat, events)
            await asyncio.sleep(10)

    async def _evaluate_momentum_breakout(self) -> None:
        strat = self.strategies.get("momentum_breakout")
        if strat is None:
            return

        # build market_data dict from Redis indicator caches
        market_data: dict[str, pd.DataFrame] = {}
        for ticker in self.cfg.watchlist:
            key = f"indicators:{ticker}:5m"
            raw = await self.redis.get(key)
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                snapshot = pd.read_json(raw, typ="series")
            except Exception:
                continue
            df = pd.DataFrame([snapshot])
            market_data[ticker] = df

        signals = strat.generate_signals(market_data)
        if not signals:
            return

        nav = self.portfolio_state.nav() or 100_000.0

        session = SessionLocal()
        try:
            for s in signals:
                if self._ticker_owner.get(s.ticker) and self._ticker_owner[s.ticker] != s.strategy_id:
                    continue
                atr = float(s.indicator_snapshot.get("atr14") or 0)
                if atr <= 0:
                    logger.debug("Skip signal %s: atr14 missing or zero", s.ticker)
                    continue
                close = float(s.indicator_snapshot.get("close") or 0)
                self._persist_signal(session, s)
                exec_signal = ExecutorSignal(
                    ticker=s.ticker,
                    strategy_id=s.strategy_id,
                    side="BUY" if s.direction == "LONG" else "SELL",
                    atr=atr,
                    entry_price_hint=close,
                    stop_distance_atr=2.0,
                    target_distance_atr=3.0,
                )
                try:
                    decision = await self.order_executor.submit_signal(exec_signal, nav)
                    if decision.allowed:
                        self._ticker_owner[s.ticker] = s.strategy_id
                    else:
                        logger.warning(
                            "Order rejected for %s: %s",
                            s.ticker,
                            decision.messages,
                        )
                except Exception as e:
                    logger.exception("Order submission failed for %s: %s", s.ticker, e)
        finally:
            session.close()

    async def _evaluate_stat_mean_reversion(self) -> None:
        strat = self.strategies.get("stat_mean_reversion")
        if strat is None:
            return

        # build market_data dict from Redis indicator caches on 15m timeframe
        market_data: dict[str, pd.DataFrame] = {}
        for ticker in self.cfg.watchlist:
            key = f"indicators:{ticker}:15m"
            raw = await self.redis.get(key)
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                snapshot = pd.read_json(raw, typ="series")
            except Exception:
                continue
            df = pd.DataFrame([snapshot])
            market_data[ticker] = df

        signals = strat.generate_signals(market_data)
        if not signals:
            return

        nav = self.portfolio_state.nav() or 100_000.0

        session = SessionLocal()
        try:
            for s in signals:
                # ticker exclusivity: skip if owned by another strategy
                if self._ticker_owner.get(s.ticker) and self._ticker_owner[s.ticker] != s.strategy_id:
                    continue

                atr = float(s.indicator_snapshot.get("atr14") or 0)
                if atr <= 0:
                    logger.debug("Skip SMR signal %s: atr14 missing or zero", s.ticker)
                    continue
                close = float(s.indicator_snapshot.get("close") or 0)
                self._persist_signal(session, s)
                exec_signal = ExecutorSignal(
                    ticker=s.ticker,
                    strategy_id=s.strategy_id,
                    side="BUY" if s.direction == "LONG" else "SELL",
                    atr=atr,
                    entry_price_hint=close,
                    stop_distance_atr=1.5,
                    target_distance_atr=2.0,
                )
                try:
                    decision = await self.order_executor.submit_signal(exec_signal, nav)
                    if decision.allowed:
                        self._ticker_owner[s.ticker] = s.strategy_id
                    else:
                        logger.warning(
                            "Order rejected for %s (stat_mean_reversion): %s",
                            s.ticker,
                            decision.messages,
                        )
                except Exception as e:
                    logger.exception("Order submission failed for %s (stat_mean_reversion): %s", s.ticker, e)
        finally:
            session.close()

    async def _evaluate_sentiment_catalyst_events(
        self, strat: SentimentCatalyst, events: list[dict]
    ) -> None:
        # build indicator snapshots from 15m cache
        indicators: dict[str, pd.Series] = {}
        for ticker in {e.get("ticker") for e in events if e.get("ticker")}:
            key = f"indicators:{ticker}:15m"
            raw = await self.redis.get(key)
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                snap = pd.read_json(raw, typ="series")
            except Exception:
                continue
            indicators[ticker] = snap

        if not indicators:
            return

        # approximate number of open positions for this strategy from ticker_owner
        open_for_strategy = sum(
            1 for owner in self._ticker_owner.values() if owner == strat.id
        )

        signals = strat.generate_signals_from_events(
            events, indicators, open_positions_for_strategy=open_for_strategy
        )
        if not signals:
            return

        nav = self.portfolio_state.nav() or 100_000.0
        session = SessionLocal()
        try:
            for s in signals:
                if (
                    self._ticker_owner.get(s.ticker)
                    and self._ticker_owner[s.ticker] != s.strategy_id
                ):
                    continue
                atr = float(s.indicator_snapshot.get("atr14") or 0)
                if atr <= 0:
                    logger.debug(
                        "Skip SentimentCatalyst signal %s: atr14 missing or zero",
                        s.ticker,
                    )
                    continue
                close = float(s.indicator_snapshot.get("close") or 0)
                self._persist_signal(session, s)
                exec_signal = ExecutorSignal(
                    ticker=s.ticker,
                    strategy_id=s.strategy_id,
                    side="BUY" if s.direction == "LONG" else "SELL",
                    atr=atr,
                    entry_price_hint=close,
                    stop_distance_atr=1.5,
                    target_distance_atr=2.0,
                )
                try:
                    decision = await self.order_executor.submit_signal(exec_signal, nav)
                    if decision.allowed:
                        self._ticker_owner[s.ticker] = s.strategy_id
                    else:
                        logger.warning(
                            "Order rejected for %s (sentiment_catalyst): %s",
                            s.ticker,
                            decision.messages,
                        )
                except Exception as e:
                    logger.exception(
                        "Order submission failed for %s (sentiment_catalyst): %s",
                        s.ticker,
                        e,
                    )
        finally:
            session.close()

    @staticmethod
    def _persist_signal(session, s: Signal) -> None:
        model = SignalModel(
            ticker=s.ticker,
            strategy_id=s.strategy_id,
            direction="LONG" if s.direction == "LONG" else "SHORT",
            timeframe=s.timeframe,
            indicator_snapshot=s.indicator_snapshot,
            reason_tags=s.reason_tags,
        )
        session.add(model)
        session.commit()

    @staticmethod
    def _is_market_hours(now: datetime) -> bool:
        # Simple UTC-based approximation; production version should use
        # proper market calendars and timezone handling.
        # Assume NYSE 9:30–16:00 ET; adjust as needed.
        t = now.time()
        return time(13, 30) <= t <= time(20, 0)

