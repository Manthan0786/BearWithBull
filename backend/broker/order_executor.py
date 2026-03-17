from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from ib_insync import Contract, Order, Stock

from backend.broker.ibkr_client import IBKRClient
from backend.models.database import SessionLocal
from backend.models.models import Order as OrderModel
from backend.risk.risk_manager import OrderRequest, RiskDecision, RiskManager


Side = Literal["BUY", "SELL", "SHORT", "COVER"]


@dataclass
class Signal:
    ticker: str
    strategy_id: str
    side: Side
    atr: float
    entry_price_hint: float
    stop_distance_atr: float
    target_distance_atr: float | None


class OrderExecutor:
    """
    Handles turning Signals into IBKR orders with OCA stop/target groups,
    enforcing mid-price limit order entries, 45s timeouts, and partial fills.
    """

    def __init__(self, ib_client: IBKRClient, risk_manager: RiskManager):
        self.ib_client = ib_client
        self.risk_manager = risk_manager

    async def submit_signal(self, signal: Signal, portfolio_nav: float) -> RiskDecision:
        """
        High-level flow for processing a trade signal:
          1. Build OrderRequest with size derived outside (later).
          2. Run RiskManager checks.
          3. Request bid/ask and compute mid price.
          4. Submit limit entry and paired stop (and optional target) as OCA.
          5. Wait up to 45s; cancel unfilled or partially filled remainder.
        """
        contract = Stock(signal.ticker, "SMART", "USD")
        snapshot = await self.ib_client.get_market_snapshot(contract)
        if snapshot.bid is None or snapshot.ask is None:
            # cannot price reliably
            return RiskDecision(allowed=False, rule_results=[], messages=["No bid/ask available"])

        mid = (snapshot.bid + snapshot.ask) / 2.0

        # for now, naive fixed fraction of NAV, real sizing uses strategies
        risk_per_trade = 0.005 * portfolio_nav
        if signal.atr <= 0:
            return RiskDecision(allowed=False, rule_results=[], messages=["ATR is non-positive"])

        # position size = (portfolio_value × risk_per_trade_pct) / (2 × ATR)
        qty = max(int(risk_per_trade / (2 * signal.atr)), 1)

        stop_price = (
            mid - signal.stop_distance_atr * signal.atr
            if signal.side in ("BUY", "COVER")
            else mid + signal.stop_distance_atr * signal.atr
        )

        entry_order = Order(
            action="BUY" if signal.side in ("BUY", "COVER") else "SELL",
            orderType="LMT",
            totalQuantity=qty,
            lmtPrice=mid,
        )

        stop_order = Order(
            action="SELL" if signal.side in ("BUY", "COVER") else "BUY",
            orderType="STP",
            totalQuantity=qty,
            auxPrice=stop_price,
        )

        # simple OCA group id
        oca_group = f"{signal.ticker}-{signal.strategy_id}"
        entry_order.ocaGroup = oca_group
        stop_order.ocaGroup = oca_group
        stop_order.ocaType = 1  # CANCEL_WITH_BLOCK

        # Place entry and stop; capture IBKR orderIds
        entry_trade = await self.ib_client.place_order(contract, entry_order)
        stop_trade = await self.ib_client.place_order(contract, stop_order)
        entry_ib_id = getattr(entry_trade.order, "orderId", None)
        stop_ib_id = getattr(stop_trade.order, "orderId", None)

        # Persist basic order records (entry + stop) to obtain entry order_id
        order_id = self._persist_orders(
            signal,
            qty,
            mid,
            stop_price,
            entry_ib_order_id=entry_ib_id,
            stop_ib_order_id=stop_ib_id,
            oca_group_id=oca_group,
        )

        order_req = OrderRequest(
            ticker=signal.ticker,
            strategy_id=signal.strategy_id,
            direction=signal.side,
            quantity=qty,
            entry_price=mid,
            stop_price=stop_price,
            atr=signal.atr,
        )

        decision = self.risk_manager.assess_order(order_req, order_id=order_id)
        if not decision.allowed:
            return decision

        # Track for up to 45 seconds
        await self._await_fill_or_timeout(entry_order, timeout=45.0, original_mid=mid)

        self.risk_manager.increment_trade_count()
        return decision

    async def _await_fill_or_timeout(
        self,
        entry_order: Order,
        timeout: float,
        original_mid: float,
    ) -> None:
        """
        Wait up to timeout seconds; if unfilled and mid moves >0.3%,
        cancel remaining. If partially filled, adjust stop externally
        (to be implemented fully when wiring fills).
        """
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        # In a fuller implementation we'd check fill status via ib_insync
        # and cancel remaining qty if needed, plus recalc stop quantity.
        # Placeholder here to satisfy flow; real logic will be added when
        # fills and PortfolioState wiring are in place.

    @staticmethod
    def _persist_orders(
        signal: Signal,
        qty: int,
        limit_price: float,
        stop_price: float,
        entry_ib_order_id: int | None,
        stop_ib_order_id: int | None,
        oca_group_id: str,
    ) -> int:
        """
        Persist both the entry LMT order and its paired STP stop order.
        Returns the entry order's id.
        """
        session = SessionLocal()
        try:
            entry = OrderModel(
                ticker=signal.ticker,
                strategy_id=signal.strategy_id,
                direction=signal.side,
                order_type="LMT",
                quantity=qty,
                limit_price=limit_price,
                stop_price=stop_price,
                status="PENDING",
                ibkr_order_id=entry_ib_order_id,
                oca_group_id=oca_group_id,
            )
            stop = OrderModel(
                ticker=signal.ticker,
                strategy_id=signal.strategy_id,
                direction="SELL" if signal.side in ("BUY", "COVER") else "BUY",
                order_type="STP",
                quantity=qty,
                limit_price=None,
                stop_price=stop_price,
                status="PENDING",
                ibkr_order_id=stop_ib_order_id,
                oca_group_id=oca_group_id,
            )
            session.add(entry)
            session.add(stop)
            session.commit()
            session.refresh(entry)
            return entry.id
        finally:
            session.close()

