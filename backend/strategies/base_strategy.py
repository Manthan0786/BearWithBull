from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, List

import pandas as pd


@dataclass
class BarData:
    ticker: str
    timeframe: str  # "1m", "5m", "15m", "1d"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    ticker: str
    strategy_id: str
    direction: str  # "LONG" or "SHORT"
    timestamp: datetime
    timeframe: str
    indicator_snapshot: dict[str, Any]
    reason_tags: list[str]


@dataclass
class ExitCondition:
    type: str  # "STOP", "TARGET", "TIME", "TRAIL"
    value: float | int


@dataclass
class OrderFill:
    ticker: str
    strategy_id: str
    direction: str
    quantity: float
    fill_price: float
    timestamp: datetime


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    stats: dict[str, Any]
    trades: pd.DataFrame


class BaseStrategy(ABC):
    """
    Base interface that all strategies must implement.
    """

    id: str  # e.g. "momentum_breakout"

    @abstractmethod
    def generate_signals(self, market_data: dict[str, pd.DataFrame]) -> List[Signal]:
        """
        market_data: mapping of ticker -> DataFrame of recent bars for the
        relevant timeframe(s), including technical indicators.
        """

    @abstractmethod
    def calculate_position_size(self, signal: Signal, portfolio_value: float) -> float:
        """
        Return quantity (shares) to trade for this signal given current
        portfolio value. ATR-based sizing logic is implemented per-strategy.
        """

    @abstractmethod
    def get_exit_conditions(self, position_price: float, atr: float) -> List[ExitCondition]:
        """
        Given current position price and ATR at entry, return a list of exit
        conditions (stop, target, trailing, time-based where applicable).
        """

    @abstractmethod
    def on_fill(self, fill: OrderFill) -> None:
        """
        Callback when an order is filled; strategies can update any
        internal state if needed.
        """

    @abstractmethod
    def on_bar(self, bar: BarData) -> None:
        """
        Optional callback on every new bar; can be used for time-based exits
        etc. For now this can be left as a no-op in concrete strategies.
        """

    @abstractmethod
    def backtest(self, start: date, end: date, data: pd.DataFrame) -> BacktestResult:
        """
        Run a simple backtest over the provided data and return equity curve,
        stats, and per-trade breakdown. Implementation can be incremental;
        core requirement is to be deterministic and log trades that match the
        live signal logic.
        """

