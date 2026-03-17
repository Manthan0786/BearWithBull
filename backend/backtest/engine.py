"""
Backtest engine: loads daily OHLCV from DB, computes indicators, simulates
momentum_breakout-style entries/exits, returns equity curve, stats, and trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import pandas_ta as ta

from backend.models.database import SessionLocal
from backend.models.models import OHLCVDaily


@dataclass
class BacktestTrade:
    ticker: str
    direction: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    exit_reason: str  # "stop" | "target" | "eod" | "eob"


@dataclass
class BacktestOutput:
    equity_curve: list[dict[str, Any]]  # [{"date": "YYYY-MM-DD", "value": float}]
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    win_rate: float
    profit_factor: float
    total_return_pct: float
    avg_trade_pnl: float
    best_trade: float
    worst_trade: float
    total_trades: int
    trades: list[dict[str, Any]]


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add sma50, rsi14, atr14, rolling_high_20, rolling_low_20, vol_sma20."""
    if df.empty or len(df) < 50:
        return df
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    df = df.copy()
    df["sma50"] = ta.sma(close, length=50)
    df["sma20"] = ta.sma(close, length=20)
    df["rsi14"] = ta.rsi(close, length=14)
    df["atr14"] = ta.atr(high, low, close, length=14)
    df["rolling_high_20"] = high.rolling(window=20).max()
    df["rolling_low_20"] = low.rolling(window=20).min()
    df["vol_sma20"] = ta.sma(vol, length=20)
    return df


def _load_daily_data(tickers: list[str], start: date, end: date) -> dict[str, pd.DataFrame]:
    """Load OHLCV daily from DB and add indicators. Returns ticker -> DataFrame indexed by date."""
    session = SessionLocal()
    try:
        out: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            rows = (
                session.query(OHLCVDaily)
                .filter(
                    OHLCVDaily.ticker == ticker,
                    OHLCVDaily.date >= start,
                    OHLCVDaily.date <= end,
                )
                .order_by(OHLCVDaily.date)
                .all()
            )
            if len(rows) < 50:
                continue
            df = pd.DataFrame(
                [
                    {
                        "date": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume,
                    }
                    for r in rows
                ]
            )
            df = df.set_index("date")
            df = _add_indicators(df)
            df = df.dropna(subset=["sma50", "rsi14", "atr14", "rolling_high_20", "vol_sma20"])
            if not df.empty:
                out[ticker] = df
        return out
    finally:
        session.close()


def _run_momentum_breakout_backtest(
    data: dict[str, pd.DataFrame],
    start: date,
    end: date,
    starting_capital: float,
    risk_per_trade_pct: float = 0.005,
) -> BacktestOutput:
    """
    Simulate momentum breakout on daily bars: long when close > rolling_high_20,
    volume > 1.5*vol_sma20, 50<=RSI<=70, close > sma50. One position at a time.
    Exit: stop 2*ATR, target 3*ATR, or end of backtest.
    """
    # Build a single timeline of all trading days
    all_dates: set[date] = set()
    for df in data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)
    if not dates:
        return BacktestOutput(
            equity_curve=[{"date": start.isoformat(), "value": starting_capital}],
            max_drawdown_pct=0.0,
            sharpe=0.0,
            sortino=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_return_pct=0.0,
            avg_trade_pnl=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            total_trades=0,
            trades=[],
        )

    capital = starting_capital
    equity_curve: list[dict[str, Any]] = []
    trades: list[BacktestTrade] = []
    position: dict[str, Any] | None = None  # ticker, direction, entry_date, entry_price, qty, atr, stop, target

    for d in dates:
        # Check exit first (existing position)
        if position is not None:
            ticker = position["ticker"]
            if ticker not in data or d not in data[ticker].index:
                # No bar for this ticker today
                equity_curve.append({"date": d.isoformat(), "value": capital})
                continue
            row = data[ticker].loc[d]
            low, high, close = row["low"], row["high"], row["close"]
            exit_price: float | None = None
            exit_reason: str = "eob"
            if position["direction"] == "LONG":
                if low <= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif high >= position["target"]:
                    exit_price = position["target"]
                    exit_reason = "target"
                else:
                    exit_price = close
                    exit_reason = "eod"
            else:  # SHORT
                if high >= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif low <= position["target"]:
                    exit_price = position["target"]
                    exit_reason = "target"
                else:
                    exit_price = close
                    exit_reason = "eod"

            if exit_price is not None:
                entry_p = position["entry_price"]
                qty = position["qty"]
                if position["direction"] == "LONG":
                    pnl = (exit_price - entry_p) * qty
                else:
                    pnl = (entry_p - exit_price) * qty
                pnl_pct = (pnl / (entry_p * qty)) * 100
                capital += pnl
                trades.append(
                    BacktestTrade(
                        ticker=ticker,
                        direction=position["direction"],
                        entry_date=position["entry_date"].isoformat(),
                        exit_date=d.isoformat(),
                        entry_price=entry_p,
                        exit_price=exit_price,
                        quantity=qty,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        exit_reason=exit_reason,
                    )
                )
                position = None

        # Then check entry (no position)
        if position is None:
            for ticker, df in data.items():
                if d not in df.index:
                    continue
                row = df.loc[d]
                close = float(row["close"])
                vol = float(row["volume"])
                vol_sma20 = float(row["vol_sma20"])
                rsi14 = float(row["rsi14"])
                sma50 = float(row["sma50"])
                rhigh = float(row["rolling_high_20"])
                rlow = float(row["rolling_low_20"])
                atr14 = float(row["atr14"])
                if vol_sma20 <= 0 or atr14 <= 0:
                    continue
                vol_ratio = vol / vol_sma20
                # Long
                if close > rhigh and vol_ratio > 1.5 and 50 <= rsi14 <= 70 and close > sma50:
                    risk_amt = capital * risk_per_trade_pct
                    qty = max(int(risk_amt / (2 * atr14)), 1)
                    stop = close - 2 * atr14
                    target = close + 3 * atr14
                    position = {
                        "ticker": ticker,
                        "direction": "LONG",
                        "entry_date": d,
                        "entry_price": close,
                        "qty": qty,
                        "atr": atr14,
                        "stop": stop,
                        "target": target,
                    }
                    break
                # Short
                if close < rlow and vol_ratio > 1.5 and 30 <= rsi14 <= 50 and close < sma50:
                    risk_amt = capital * risk_per_trade_pct
                    qty = max(int(risk_amt / (2 * atr14)), 1)
                    stop = close + 2 * atr14
                    target = close - 3 * atr14
                    position = {
                        "ticker": ticker,
                        "direction": "SHORT",
                        "entry_date": d,
                        "entry_price": close,
                        "qty": qty,
                        "atr": atr14,
                        "stop": stop,
                        "target": target,
                    }
                    break

        # Unrealized P&L for equity curve
        day_value = capital
        if position is not None and d in data.get(position["ticker"], pd.DataFrame()).index:
            row = data[position["ticker"]].loc[d]
            close = row["close"]
            entry_p = position["entry_price"]
            qty = position["qty"]
            if position["direction"] == "LONG":
                day_value += (close - entry_p) * qty
            else:
                day_value += (entry_p - close) * qty
        equity_curve.append({"date": d.isoformat(), "value": round(day_value, 2)})

    # Flatten any open position at end
    if position is not None:
        ticker = position["ticker"]
        last_date = dates[-1]
        if ticker in data and last_date in data[ticker].index:
            exit_price = float(data[ticker].loc[last_date]["close"])
            entry_p = position["entry_price"]
            qty = position["qty"]
            if position["direction"] == "LONG":
                pnl = (exit_price - entry_p) * qty
            else:
                pnl = (entry_p - exit_price) * qty
            pnl_pct = (pnl / (entry_p * qty)) * 100
            capital += pnl
            trades.append(
                BacktestTrade(
                    ticker=ticker,
                    direction=position["direction"],
                    entry_date=position["entry_date"].isoformat(),
                    exit_date=last_date.isoformat(),
                    entry_price=entry_p,
                    exit_price=exit_price,
                    quantity=qty,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    exit_reason="eob",
                )
            )

    # Stats
    total_return_pct = ((capital - starting_capital) / starting_capital) * 100 if starting_capital else 0.0
    eq_series = pd.Series([e["value"] for e in equity_curve], index=[e["date"] for e in equity_curve])
    peak = eq_series.expanding().max()
    drawdown_pct = (eq_series - peak) / peak * 100
    max_drawdown_pct = float(drawdown_pct.min()) if len(drawdown_pct) else 0.0

    returns = eq_series.pct_change().dropna()
    sharpe = (returns.mean() / returns.std() * (252**0.5)) if returns.std() > 0 else 0.0
    downside = returns[returns < 0]
    sortino = (returns.mean() / downside.std() * (252**0.5)) if len(downside) and downside.std() > 0 else 0.0

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    total_trades = len(trades)
    win_rate = len(wins) / total_trades if total_trades else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    avg_trade_pnl = (sum(t.pnl for t in trades) / total_trades) if total_trades else 0.0
    best_trade = max((t.pnl for t in trades), default=0.0)
    worst_trade = min((t.pnl for t in trades), default=0.0)

    return BacktestOutput(
        equity_curve=equity_curve,
        max_drawdown_pct=round(max_drawdown_pct, 2),
        sharpe=round(sharpe, 2),
        sortino=round(sortino, 2),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 2),
        total_return_pct=round(total_return_pct, 2),
        avg_trade_pnl=round(avg_trade_pnl, 2),
        best_trade=round(best_trade, 2),
        worst_trade=round(worst_trade, 2),
        total_trades=total_trades,
        trades=[
            {
                "ticker": t.ticker,
                "direction": t.direction,
                "entry": t.entry_date,
                "exit": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct,
                "exit_reason": t.exit_reason,
            }
            for t in trades
        ],
    )


def run_backtest(
    strategy_id: str,
    tickers: list[str],
    start_date: date,
    end_date: date,
    starting_capital: float = 100_000.0,
) -> BacktestOutput:
    """
    Run backtest for the given strategy. Only momentum_breakout is implemented.
    """
    if not tickers:
        return BacktestOutput(
            equity_curve=[{"date": start_date.isoformat(), "value": starting_capital}],
            max_drawdown_pct=0.0,
            sharpe=0.0,
            sortino=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_return_pct=0.0,
            avg_trade_pnl=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            total_trades=0,
            trades=[],
        )

    data = _load_daily_data(tickers, start_date, end_date)
    if not data:
        return BacktestOutput(
            equity_curve=[{"date": start_date.isoformat(), "value": starting_capital}],
            max_drawdown_pct=0.0,
            sharpe=0.0,
            sortino=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_return_pct=0.0,
            avg_trade_pnl=0.0,
            best_trade=0.0,
            worst_trade=0.0,
            total_trades=0,
            trades=[],
        )

    if strategy_id == "momentum_breakout":
        return _run_momentum_breakout_backtest(
            data, start_date, end_date, starting_capital, risk_per_trade_pct=0.005
        )

    # Fallback for other strategies (not yet implemented)
    return BacktestOutput(
        equity_curve=[{"date": start_date.isoformat(), "value": starting_capital}],
        max_drawdown_pct=0.0,
        sharpe=0.0,
        sortino=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        total_return_pct=0.0,
        avg_trade_pnl=0.0,
        best_trade=0.0,
        worst_trade=0.0,
        total_trades=0,
        trades=[],
    )
