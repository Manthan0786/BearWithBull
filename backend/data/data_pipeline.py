from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import pandas as pd
import redis.asyncio as redis
from ib_insync import BarData, IB, Stock

from backend.data.indicators import IndicatorEngine, Timeframe


class DataPipeline:
    """
    Manages real-time subscriptions, aggregation of 5s bars into higher timeframes,
    and caching of bars and indicators in Redis.
    """

    def __init__(self, ib: IB, redis_client: redis.Redis):
        self.ib = ib
        self.redis = redis_client
        self.indicators = IndicatorEngine(redis_client)
        self._tasks: list[asyncio.Task] = []
        self._bars_5s: Dict[str, List[BarData]] = defaultdict(list)

    async def start(self, symbols: list[str]) -> None:
        """
        Subscribe to 5-second bars for the provided symbols and start aggregation loops.
        """
        loop = asyncio.get_event_loop()
        for symbol in symbols:
            contract = Stock(symbol, "SMART", "USD")
            # Run blocking ib_insync subscription in a thread
            await asyncio.to_thread(self.ib.reqRealTimeBars, contract, 5, "TRADES", False)

        self._tasks.append(loop.create_task(self._collect_bars()))
        self._tasks.append(loop.create_task(self._aggregate_loop("1m", 60)))
        self._tasks.append(loop.create_task(self._aggregate_loop("5m", 300)))
        self._tasks.append(loop.create_task(self._aggregate_loop("15m", 900)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    async def _collect_bars(self) -> None:
        """
        Collect 5s bars from IBKR and append to in-memory buffers.
        """
        while True:
            await asyncio.sleep(1)
            bars = list(self.ib.reqAllRealTimeBars())
            for bar in bars:
                symbol = bar.contract.symbol
                self._bars_5s[symbol].append(bar)

    async def _aggregate_loop(self, timeframe: Timeframe, seconds: int) -> None:
        """
        Periodically aggregate 5s bars into the given timeframe and cache results.
        """
        while True:
            await asyncio.sleep(seconds)
            await self._aggregate_timeframe(timeframe, window_seconds=seconds)

    async def _aggregate_timeframe(self, timeframe: Timeframe, window_seconds: int) -> None:
        now = datetime.utcnow()
        for symbol, bars in list(self._bars_5s.items()):
            # Keep only recent window for simplicity
            recent = [b for b in bars if (now - b.time).total_seconds() <= window_seconds]
            self._bars_5s[symbol] = recent
            if not recent:
                continue

            df = pd.DataFrame(
                [
                    {
                        "time": b.time,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "volume": b.volume,
                    }
                    for b in recent
                ]
            ).set_index("time")

            # simple OHLC aggregation over window
            agg = pd.DataFrame(
                {
                    "open": df["open"].iloc[0],
                    "high": df["high"].max(),
                    "low": df["low"].min(),
                    "close": df["close"].iloc[-1],
                    "volume": df["volume"].sum(),
                },
                index=[df.index[-1]],
            )

            await self._cache_bar(symbol, timeframe, agg)
            await self.indicators.cache_indicators(symbol, timeframe, agg)

    async def _cache_bar(self, symbol: str, timeframe: Timeframe, df: pd.DataFrame) -> None:
        """
        Cache latest aggregated bar in Redis under bars:{symbol}:{timeframe}.
        """
        last = df.iloc[-1]
        payload = {
            "timestamp": df.index[-1].isoformat(),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "volume": float(last["volume"]),
        }
        key = f"bars:{symbol}:{timeframe}"
        await self.redis.set(key, pd.io.json.dumps(payload), ex=600)

