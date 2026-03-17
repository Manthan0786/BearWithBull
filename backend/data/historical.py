from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import pandas as pd
import yfinance as yf
from ib_insync import IB, Stock

from backend.models.database import SessionLocal
from backend.models.models import OHLCVDaily


async def fetch_ibkr_daily(
    ib: IB,
    symbol: str,
    days: int = 252,
) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV from IBKR. Returns a DataFrame or None on failure.
    """
    contract = Stock(symbol, "SMART", "USD")
    bars = await ib.reqHistoricalDataAsync(  # type: ignore[attr-defined]
        contract,
        endDateTime="",
        durationStr=f"{days} D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        return None
    df = pd.DataFrame(
        [
            {
                "date": b.date.date(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )
    return df.set_index("date")


def fetch_yfinance_daily(symbol: str, days: int = 252) -> pd.DataFrame | None:
    end = datetime.utcnow().date()
    start = end - timedelta(days=days * 2)
    df = yf.download(symbol, start=start, end=end, progress=False)
    if df.empty:
        return None
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index = df.index.date
    return df[["open", "high", "low", "close", "adj_close", "volume"]]


def upsert_ohlcv_daily(symbol: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    session = SessionLocal()
    try:
        for date, row in df.iterrows():
            existing = (
                session.query(OHLCVDaily)
                .filter(OHLCVDaily.ticker == symbol, OHLCVDaily.date == date)
                .one_or_none()
            )
            if existing:
                existing.open = float(row["open"])
                existing.high = float(row["high"])
                existing.low = float(row["low"])
                existing.close = float(row["close"])
                existing.adj_close = float(row.get("adj_close", row["close"]))
                existing.volume = float(row["volume"])
            else:
                session.add(
                    OHLCVDaily(
                        ticker=symbol,
                        date=date,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adj_close=float(row.get("adj_close", row["close"])),
                        volume=float(row["volume"]),
                    )
                )
        session.commit()
    finally:
        session.close()


async def bootstrap_historical(
    ib: IB,
    symbols: Sequence[str],
    days: int = 252,
) -> None:
    """
    Populate ohlcv_daily for each symbol using IBKR primary and yFinance fallback.
    """
    for symbol in symbols:
        df_ib = None
        try:
            df_ib = await fetch_ibkr_daily(ib, symbol, days=days)
        except Exception:
            df_ib = None

        if df_ib is not None:
            upsert_ohlcv_daily(symbol, df_ib)
            continue

        df_yf = fetch_yfinance_daily(symbol, days=days)
        if df_yf is not None:
            upsert_ohlcv_daily(symbol, df_yf)

