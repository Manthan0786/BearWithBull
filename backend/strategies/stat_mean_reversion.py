from __future__ import annotations

from datetime import datetime, date
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


class StatMeanReversion(BaseStrategy):
    """
    Statistical mean-reversion strategy on 15-minute bars.

    High-level (aligned with spec but simplified for first pass):
      - Universe: driven by watchlist and daily pre-filter handled upstream.
      - LONG when:
          * close < lower Bollinger Band (bb_lower)
          * RSI(2) very oversold (e.g. < 10)
          * close > 200 SMA (uptrend filter)
      - SHORT when:
          * close > upper Bollinger Band (bb_upper)
          * RSI(2) very overbought (e.g. > 90)
          * close < 200 SMA (downtrend filter)

      - Position sizing: ATR-based, using per-strategy risk_per_trade_pct.
      - Exits: stop at 1.5×ATR, target at 2×ATR (handled by engine via ATR distances).
    """

    id = "stat_mean_reversion"

    def __init__(self, risk_per_trade_pct: float = 0.004):
        self.risk_per_trade_pct = risk_per_trade_pct

    def generate_signals(self, market_data: dict[str, pd.DataFrame]) -> List[Signal]:
        """
        market_data: ticker -> DataFrame with at least:
          close, rsi2, sma200, atr14, bb_lower, bb_upper
        """
        if not market_data:
            return []

        signals: List[Signal] = []
        now = datetime.utcnow()

        for ticker, df in market_data.items():
            if df.empty:
                continue

            last = df.iloc[-1]
            close = float(last.get("close", 0.0))
            rsi2 = float(last.get("rsi2", 50.0))
            sma200 = float(last.get("sma200", close))
            atr14 = float(last.get("atr14", 0.0))
            bb_lower = float(last.get("bb_lower", close))
            bb_upper = float(last.get("bb_upper", close))

            if atr14 <= 0 or close <= 0:
                continue

            # Long mean reversion: oversold above 200 SMA
            if close < bb_lower and rsi2 < 10 and close > sma200:
                signals.append(
                    Signal(
                        ticker=ticker,
                        strategy_id=self.id,
                        direction="LONG",
                        timestamp=now,
                        timeframe="15m",
                        indicator_snapshot={
                            "close": close,
                            "rsi2": rsi2,
                            "sma200": sma200,
                            "atr14": atr14,
                            "bb_lower": bb_lower,
                            "bb_upper": bb_upper,
                        },
                        reason_tags=["stat_mean_reversion_long"],
                    )
                )

            # Short mean reversion: overbought below 200 SMA
            if close > bb_upper and rsi2 > 90 and close < sma200:
                signals.append(
                    Signal(
                        ticker=ticker,
                        strategy_id=self.id,
                        direction="SHORT",
                        timestamp=now,
                        timeframe="15m",
                        indicator_snapshot={
                            "close": close,
                            "rsi2": rsi2,
                            "sma200": sma200,
                            "atr14": atr14,
                            "bb_lower": bb_lower,
                            "bb_upper": bb_upper,
                        },
                        reason_tags=["stat_mean_reversion_short"],
                    )
                )

        return signals

    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        atr = float(signal.indicator_snapshot.get("atr14", 0.0))
        if atr <= 0 or portfolio_value <= 0:
            return 0.0
        risk_amount = portfolio_value * self.risk_per_trade_pct
        size = risk_amount / (2.0 * atr)
        return max(float(int(size)), 0.0)

    def get_exit_conditions(self, position_price: float, atr: float) -> List[ExitCondition]:
        """
        Per spec (simplified):
          - Stop loss: entry ∓ 1.5× ATR
          - Profit target: entry ± 2× ATR
        Engine interprets these ATR distances based on direction.
        """
        return [
            ExitCondition(type="STOP_ATR", value=1.5 * atr),
            ExitCondition(type="TARGET_ATR", value=2.0 * atr),
        ]

    def on_fill(self, fill: OrderFill) -> None:
        # No internal state for now.
        return

    def on_bar(self, bar: BarData) -> None:
        # Time-based exits can be handled by engine/scheduler; no-op here.
        return

    def backtest(self, start: date, end: date, data: pd.DataFrame) -> BacktestResult:
        """
        Placeholder backtest implementation. A full version would mirror the
        intraday mean-reversion logic using historical 15m bars.
        """
        equity = pd.Series(dtype=float)
        stats: dict[str, Any] = {}
        trades = pd.DataFrame()
        return BacktestResult(equity_curve=equity, stats=stats, trades=trades)

