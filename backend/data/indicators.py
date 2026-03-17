from __future__ import annotations

from typing import Literal

import pandas as pd
import pandas_ta as ta
import redis.asyncio as redis

Timeframe = Literal["1m", "5m", "15m", "1d"]


class IndicatorEngine:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def cache_indicators(
        self,
        ticker: str,
        timeframe: Timeframe,
        df: pd.DataFrame,
    ) -> None:
        """
        Compute indicators on bar close and cache latest values in Redis.

        df is expected to have columns: ['open','high','low','close','volume'] and be
        indexed by datetime in ascending order.
        """
        if df.empty:
            return

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        sma20 = ta.sma(close, length=20)
        sma50 = ta.sma(close, length=50)
        sma200 = ta.sma(close, length=200)
        ema9 = ta.ema(close, length=9)
        ema21 = ta.ema(close, length=21)
        rsi2 = ta.rsi(close, length=2)
        rsi14 = ta.rsi(close, length=14)
        atr14 = ta.atr(high, low, close, length=14)
        bb = ta.bbands(close, length=20, std=2)
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        vol_sma20 = ta.sma(volume, length=20)

        last = df.index[-1]

        data = {
            "timestamp": last.isoformat(),
            "sma20": float(sma20.iloc[-1]) if not pd.isna(sma20.iloc[-1]) else None,
            "sma50": float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None,
            "sma200": float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else None,
            "ema9": float(ema9.iloc[-1]) if not pd.isna(ema9.iloc[-1]) else None,
            "ema21": float(ema21.iloc[-1]) if not pd.isna(ema21.iloc[-1]) else None,
            "rsi2": float(rsi2.iloc[-1]) if not pd.isna(rsi2.iloc[-1]) else None,
            "rsi14": float(rsi14.iloc[-1]) if not pd.isna(rsi14.iloc[-1]) else None,
            "atr14": float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else None,
            "bb_lower": float(bb["BBL_20_2.0"].iloc[-1]) if bb is not None else None,
            "bb_mid": float(bb["BBM_20_2.0"].iloc[-1]) if bb is not None else None,
            "bb_upper": float(bb["BBU_20_2.0"].iloc[-1]) if bb is not None else None,
            "bbw": float(
                (bb["BBU_20_2.0"].iloc[-1] - bb["BBL_20_2.0"].iloc[-1])
                / bb["BBM_20_2.0"].iloc[-1]
            )
            if bb is not None and bb["BBM_20_2.0"].iloc[-1] != 0
            else None,
            "macd": float(macd["MACD_12_26_9"].iloc[-1]) if macd is not None else None,
            "macd_signal": float(macd["MACDs_12_26_9"].iloc[-1])
            if macd is not None
            else None,
            "macd_hist": float(macd["MACDh_12_26_9"].iloc[-1])
            if macd is not None
            else None,
            "vol_sma20": float(vol_sma20.iloc[-1])
            if not pd.isna(vol_sma20.iloc[-1])
            else None,
            "rolling_high_20": float(high.rolling(window=20).max().iloc[-1]),
            "rolling_low_20": float(low.rolling(window=20).min().iloc[-1]),
        }

        key = f"indicators:{ticker}:{timeframe}"
        ttl_seconds = 600 if timeframe == "5m" else 180  # 2x timeframe
        await self.redis.set(key, pd.io.json.dumps(data), ex=ttl_seconds)

