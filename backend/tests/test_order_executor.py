import asyncio
from types import SimpleNamespace

import pytest

from backend.broker.order_executor import OrderExecutor, Signal
from backend.broker.ibkr_client import IBKRClient, MarketSnapshot
from backend.config import AppConfig, TradingConfig
from backend.risk.portfolio_state import PortfolioState
from backend.risk.risk_manager import RiskManager


class DummyIB:
    def __init__(self):
        self.placed = []

    def placeOrder(self, contract, order):
        self.placed.append((contract, order))

    def reqMktData(self, contract, genericTickList, snapshot, regulatorySnapshot):
        # return simple object with bid/ask/last
        return SimpleNamespace(bid=100.0, ask=100.2, last=100.1)


@pytest.mark.asyncio
async def test_order_executor_places_entry_and_stop(monkeypatch):
    ib = DummyIB()
    client = IBKRClient(ib)
    cfg = AppConfig(trading=TradingConfig(), strategies={}, watchlist=[])
    ps = PortfolioState(account_id=1)
    ps._nav = 100_000.0  # type: ignore[attr-defined]
    rm = RiskManager(cfg, ps)

    # speed up _await_fill_or_timeout
    async def fast_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    executor = OrderExecutor(client, rm)
    signal = Signal(
        ticker="AAPL",
        strategy_id="test",
        side="BUY",
        atr=2.0,
        entry_price_hint=100.0,
        stop_distance_atr=2.0,
        target_distance_atr=None,
    )

    decision = await executor.submit_signal(signal, portfolio_nav=100_000.0)

    assert decision.allowed is True
    # ensure two orders placed: entry + stop
    assert len(ib.placed) == 2

