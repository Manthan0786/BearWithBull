from __future__ import annotations

from datetime import datetime
from typing import Literal

from backend.models.database import SessionLocal
from backend.models.models import Order, Position, Trade


ExitReason = Literal["STOP", "TARGET", "TIME", "MANUAL"]


def process_entry_fill(
    order_id: int,
    fill_price: float,
    fill_qty: float,
    fill_time: datetime | None = None,
) -> None:
    """
    Create or update a Position when an entry order fills.

    Assumes the order row already exists and belongs to a single-account setup.
    """
    session = SessionLocal()
    try:
        order: Order | None = session.query(Order).filter(Order.id == order_id).one_or_none()
        if order is None:
            return

        order.fill_price = fill_price
        order.fill_qty = fill_qty
        order.status = "FILLED"
        if fill_time is None:
            fill_time = datetime.utcnow()
        order.timestamp = fill_time

        # For now, assume single account with id=1
        account_id = 1

        # Find existing open position for this ticker/strategy
        pos: Position | None = (
            session.query(Position)
            .filter(
                Position.account_id == account_id,
                Position.ticker == order.ticker,
                Position.strategy_id == order.strategy_id,
                Position.status == "OPEN",
            )
            .one_or_none()
        )

        if pos is None:
            # Create new position
            pos = Position(
                account_id=account_id,
                ticker=order.ticker,
                strategy_id=order.strategy_id,
                direction="LONG" if order.direction in ("BUY", "COVER") else "SHORT",
                quantity=fill_qty,
                entry_price=fill_price,
                avg_price=fill_price,
                entry_time=fill_time,
                stop_price=order.stop_price,
                target_price=None,
                atr_at_entry=None,
                status="OPEN",
                exit_price=None,
                exit_time=None,
                exit_reason=None,
            )
            session.add(pos)
            session.flush()
        else:
            # Simple averaging-up logic (no partials handling for now)
            total_qty = pos.quantity + fill_qty
            if total_qty > 0:
                pos.avg_price = (pos.avg_price * pos.quantity + fill_price * fill_qty) / total_qty
            pos.quantity = total_qty
            pos.entry_price = pos.avg_price

        session.commit()
    finally:
        session.close()


def process_exit_fill(
    exit_order_id: int,
    entry_order_id: int,
    exit_price: float,
    fill_qty: float,
    exit_reason: ExitReason = "MANUAL",
    fill_time: datetime | None = None,
) -> None:
    """
    Close or partially reduce a Position and create a Trade when an exit
    order fills.
    """
    session = SessionLocal()
    try:
        exit_order: Order | None = (
            session.query(Order).filter(Order.id == exit_order_id).one_or_none()
        )
        entry_order: Order | None = (
            session.query(Order).filter(Order.id == entry_order_id).one_or_none()
        )
        if exit_order is None or entry_order is None:
            return

        exit_order.fill_price = exit_price
        exit_order.fill_qty = fill_qty
        exit_order.status = "FILLED"
        if fill_time is None:
            fill_time = datetime.utcnow()
        exit_order.timestamp = fill_time

        # For now, assume single account with id=1
        account_id = 1

        pos: Position | None = (
            session.query(Position)
            .filter(
                Position.account_id == account_id,
                Position.ticker == entry_order.ticker,
                Position.strategy_id == entry_order.strategy_id,
                Position.status == "OPEN",
            )
            .one_or_none()
        )
        if pos is None:
            session.commit()
            return

        entry_price = pos.entry_price
        qty = fill_qty or pos.quantity
        direction_mult = 1.0 if pos.direction == "LONG" else -1.0
        pnl_abs = direction_mult * (exit_price - entry_price) * qty
        pnl_pct = (pnl_abs / (entry_price * qty)) * 100 if entry_price * qty else 0.0

        hold_time_sec = int((fill_time - pos.entry_time).total_seconds()) if pos.entry_time else 0

        # Handle partial close: reduce quantity and keep position OPEN if remainder > 0
        remaining_qty = (pos.quantity or 0) - qty
        if remaining_qty > 0:
            pos.quantity = remaining_qty
            # Keep status OPEN; we do not set exit_* fields on partials
        else:
            pos.status = "CLOSED"
            pos.exit_price = exit_price
            pos.exit_time = fill_time
            pos.exit_reason = exit_reason

        trade = Trade(
            position_id=pos.id,
            entry_order_id=entry_order.id,
            exit_order_id=exit_order.id,
            pnl_abs=pnl_abs,
            pnl_pct=pnl_pct,
            hold_time_sec=hold_time_sec,
            strategy_id=pos.strategy_id,
            exit_reason=exit_reason,
            slippage_bps=None,
        )
        session.add(trade)

        session.commit()
    finally:
        session.close()

