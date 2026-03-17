"""
Emergency stop: cancel all open orders and flatten all positions via IBKR.
Bypasses strategy and risk checks. Intended for admin override from the dashboard.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ib_insync import Order

if TYPE_CHECKING:
    from ib_insync import IB


@dataclass
class EmergencyStopResult:
    cancelled_orders: int
    flatten_orders_placed: int
    errors: list[str]


def _run_emergency_stop_sync(ib: "IB") -> EmergencyStopResult:
    """
    Run on a thread: cancel all open orders, then place market orders to close all positions.
    """
    errors: list[str] = []
    cancelled = 0
    flattened = 0

    try:
        # Cancel all open orders (openTrades includes working orders)
        trades = ib.openTrades()
        for trade in trades:
            try:
                trade.cancel()
                cancelled += 1
            except Exception as e:
                errors.append(f"Cancel order: {e!s}")
    except Exception as e:
        errors.append(f"Get/cancel orders: {e!s}")

    try:
        # Flatten all positions with market orders
        positions = ib.positions()
        for pos in positions:
            try:
                qty = abs(int(pos.position))
                if qty <= 0:
                    continue
                # Long -> SELL to close; Short (negative position) -> BUY to close
                action = "SELL" if pos.position > 0 else "BUY"
                contract = pos.contract
                order = Order(orderType="MKT", action=action, totalQuantity=qty)
                ib.placeOrder(contract, order)
                flattened += 1
            except Exception as e:
                errors.append(f"Flatten {getattr(pos.contract, 'symbol', '?')}: {e!s}")
    except Exception as e:
        errors.append(f"Get positions/flatten: {e!s}")

    return EmergencyStopResult(
        cancelled_orders=cancelled,
        flatten_orders_placed=flattened,
        errors=errors,
    )


async def run_emergency_stop(ib: "IB | None") -> EmergencyStopResult:
    """Async wrapper: run emergency stop in a thread. Safe when ib is None or disconnected."""
    if ib is None or not ib.isConnected():
        return EmergencyStopResult(
            cancelled_orders=0,
            flatten_orders_placed=0,
            errors=["Not connected to IB Gateway. No orders or positions to close."],
        )
    return await asyncio.to_thread(_run_emergency_stop_sync, ib)
