from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from ib_insync import IB, Contract, Order


@dataclass
class MarketSnapshot:
    bid: float | None
    ask: float | None
    last: float | None


class IBKRClient:
    """
    Thin async wrapper around ib_insync.IB with simple rate limiting and
    helpers needed by the OrderExecutor.
    """

    def __init__(self, ib: IB, max_hist_per_sec: int = 40, max_other_per_sec: int = 20):
        self.ib = ib
        self._hist_semaphore = asyncio.Semaphore(max_hist_per_sec)
        self._other_semaphore = asyncio.Semaphore(max_other_per_sec)

    async def _run_limited(
        self,
        sem: asyncio.Semaphore,
        func: Callable[..., Any],
        *args: Any,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> Any:
        async with sem:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=timeout,
            )

    async def place_order(self, contract: Contract, order: Order) -> Any:
        return await self._run_limited(self._other_semaphore, self.ib.placeOrder, contract, order)

    async def cancel_order(self, order_id: int) -> None:
        await self._run_limited(self._other_semaphore, self.ib.cancelOrder, order_id)

    async def get_open_orders(self) -> list[Any]:
        return await self._run_limited(self._other_semaphore, self.ib.openOrders)

    async def get_market_snapshot(self, contract: Contract) -> MarketSnapshot:
        tickers = await self._run_limited(self._other_semaphore, self.ib.reqMktData, contract, "", False, False)
        # ib_insync returns a Ticker object; read snapshot fields
        bid = getattr(tickers, "bid", None)
        ask = getattr(tickers, "ask", None)
        last = getattr(tickers, "last", None)
        return MarketSnapshot(bid=bid, ask=ask, last=last)

