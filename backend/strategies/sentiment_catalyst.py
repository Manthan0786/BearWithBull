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


class SentimentCatalyst(BaseStrategy):
    """News-driven strategy reacting to strong sentiment events."""

    id = "sentiment_catalyst"

    def __init__(self, risk_per_trade_pct: float = 0.0025, max_positions: int = 2):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_positions = max_positions

    def generate_signals(self, market_data: dict[str, pd.DataFrame]) -> List[Signal]:
        # Not used in live flow; signals come from NewsEvents.
        return []

    def generate_signals_from_events(
        self,
        events: list[dict[str, Any]],
        indicators: dict[str, pd.Series],
        open_positions_for_strategy: int,
    ) -> List[Signal]:
        signals: List[Signal] = []
        if open_positions_for_strategy >= self.max_positions:
            return signals

        now = datetime.utcnow()
        for ev in events:
            ticker = ev.get("ticker")
            label = ev.get("label")
            if not ticker or label not in {"STRONG_POSITIVE", "STRONG_NEGATIVE"}:
                continue
            snap = indicators.get(ticker)
            if snap is None or snap.empty:
                continue
            close = float(snap.get("close", 0.0))
            atr14 = float(snap.get("atr14", 0.0))
            if close <= 0 or atr14 <= 0:
                continue
            direction = "LONG" if label == "STRONG_POSITIVE" else "SHORT"
            signals.append(
                Signal(
                    ticker=ticker,
                    strategy_id=self.id,
                    direction=direction,
                    timestamp=now,
                    timeframe="15m",
                    indicator_snapshot={
                        "close": close,
                        "atr14": atr14,
                        "news_headline": ev.get("headline"),
                        "sentiment_compound": ev.get("compound"),
                        "sentiment_label": label,
                    },
                    reason_tags=["sentiment_catalyst", label.lower()],
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
        return [
            ExitCondition(type="STOP_ATR", value=1.5 * atr),
            ExitCondition(type="TARGET_ATR", value=2.0 * atr),
            ExitCondition(type="TIME_MINUTES", value=90),
        ]

    def on_fill(self, fill: OrderFill) -> None:
        return

    def on_bar(self, bar: BarData) -> None:
        return

    def backtest(self, start: date, end: date, data: pd.DataFrame) -> BacktestResult:
        equity = pd.Series(dtype=float)
        stats: dict[str, Any] = {}
        trades = pd.DataFrame()
        return BacktestResult(equity_curve=equity, stats=stats, trades=trades)

