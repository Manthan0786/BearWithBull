from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Any, List

import pandas as pd

from backend.strategies.base_strategy import (
    BacktestResult,
    BaseStrategy,
    BarData,
    ExitCondition,
    OrderFill,
    Signal,
)


class MomentumBreakout(BaseStrategy):
    """
    Implements the MomentumBreakout strategy on 5-minute bars.

    Signal logic (high level, aligned with spec):
      - Compute 20-day momentum, volume surge, RS vs SPY, rank universe.
      - Only consider top 20% ranked tickers.
      - LONG entry when:
          * close > 20-day rolling high
          * volume > 1.5x 20-day avg volume
          * RSI(14) in [50, 70]
          * close > 50 SMA
      - SHORT entry symmetric with 20-day low, RSI(14) in [30, 50], close < 50 SMA.
    """

    id = "momentum_breakout"

    def __init__(self, risk_per_trade_pct: float = 0.005):
        self.risk_per_trade_pct = risk_per_trade_pct

    def generate_signals(self, market_data: dict[str, pd.DataFrame]) -> List[Signal]:
        """
        market_data: ticker -> DataFrame with at least:
          close, volume, sma20, sma50, rsi14, atr14, rolling_high_20, rolling_low_20,
          vol_sma20, rs_spy_20d, mom_20d
        """
        if not market_data:
            return []

        # Build ranking based on 20d momentum, volume surge, RS vs SPY
        rank_scores = []
        for ticker, df in market_data.items():
            if df.empty:
                continue
            last = df.iloc[-1]
            mom = float(last.get("mom_20d", 0.0))
            vol_surge = float(
                last.get("volume", 0.0) / last.get("vol_sma20", 1.0)
                if last.get("vol_sma20", 0.0) not in (0, None)
                else 0.0
            )
            rs_spy = float(last.get("rs_spy_20d", 0.0))
            score = mom + vol_surge + rs_spy
            rank_scores.append((ticker, score))

        if not rank_scores:
            return []

        rank_scores.sort(key=lambda x: x[1], reverse=True)
        top_n = max(1, int(len(rank_scores) * 0.2))
        top_universe = {t for t, _ in rank_scores[:top_n]}

        signals: List[Signal] = []
        now = datetime.utcnow()

        for ticker, df in market_data.items():
            if ticker not in top_universe or df.empty:
                continue

            last = df.iloc[-1]
            close = float(last["close"])
            rsi14 = float(last.get("rsi14", 50.0))
            sma50 = float(last.get("sma50", close))
            rhigh = float(last.get("rolling_high_20", close))
            rlow = float(last.get("rolling_low_20", close))
            vol = float(last.get("volume", 0.0))
            vol_sma20 = float(last.get("vol_sma20", max(vol, 1.0)))
            atr14 = float(last.get("atr14", 0.0))

            if vol_sma20 <= 0 or atr14 <= 0:
                continue

            vol_ratio = vol / vol_sma20

            # LONG setup
            if (
                close > rhigh
                and vol_ratio > 1.5
                and 50.0 <= rsi14 <= 70.0
                and close > sma50
            ):
                signals.append(
                    Signal(
                        ticker=ticker,
                        strategy_id=self.id,
                        direction="LONG",
                        timestamp=now,
                        timeframe="5m",
                        indicator_snapshot={
                            "close": close,
                            "rsi14": rsi14,
                            "sma50": sma50,
                            "rolling_high_20": rhigh,
                            "volume": vol,
                            "vol_sma20": vol_sma20,
                            "atr14": atr14,
                            "vol_ratio": vol_ratio,
                        },
                        reason_tags=["momentum_breakout_long"],
                    )
                )

            # SHORT setup
            if (
                close < rlow
                and vol_ratio > 1.5
                and 30.0 <= rsi14 <= 50.0
                and close < sma50
            ):
                signals.append(
                    Signal(
                        ticker=ticker,
                        strategy_id=self.id,
                        direction="SHORT",
                        timestamp=now,
                        timeframe="5m",
                        indicator_snapshot={
                            "close": close,
                            "rsi14": rsi14,
                            "sma50": sma50,
                            "rolling_low_20": rlow,
                            "volume": vol,
                            "vol_sma20": vol_sma20,
                            "atr14": atr14,
                            "vol_ratio": vol_ratio,
                        },
                        reason_tags=["momentum_breakout_short"],
                    )
                )

        return signals

    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        atr = float(signal.indicator_snapshot.get("atr14", 0.0))
        if atr <= 0 or portfolio_value <= 0:
            return 0.0
        risk_amount = portfolio_value * self.risk_per_trade_pct
        # per spec: size = (portfolio_value × risk_per_trade) / (2 × ATR)
        size = risk_amount / (2.0 * atr)
        return max(float(int(size)), 0.0)

    def get_exit_conditions(self, position_price: float, atr: float) -> list[ExitCondition]:
        """
        Per spec:
          - Stop loss: entry ∓ 2× ATR
          - Profit target: entry ± 3× ATR
          - Trailing: activates at +1.5× ATR, trail by 1× ATR
          - Time-based: exit 60 minutes before market close (handled via scheduler)
        Here we just encode numeric parameters; direction is handled by caller.
        """
        return [
            ExitCondition(type="STOP_ATR", value=2.0 * atr),
            ExitCondition(type="TARGET_ATR", value=3.0 * atr),
            ExitCondition(type="TRAIL_ATR", value=1.0 * atr),
            ExitCondition(type="TIME_BEFORE_CLOSE_MIN", value=60),
        ]

    def on_fill(self, fill: OrderFill) -> None:
        # For now, no internal state to update.
        return

    def on_bar(self, bar: BarData) -> None:
        # Time-based exit logic will be driven by engine; no-op here.
        return

    def backtest(self, start: date, end: date, data: pd.DataFrame) -> BacktestResult:
        """
        Placeholder backtest that currently returns an empty result. A full
        implementation will simulate trades using generate_signals and the
        exit conditions.
        """
        equity = pd.Series(dtype=float)
        stats: dict[str, Any] = {}
        trades = pd.DataFrame()
        return BacktestResult(equity_curve=equity, stats=stats, trades=trades)

