"""
REST API for dashboard: portfolio, positions, trades, risk, strategies.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func

from backend.backtest.engine import run_backtest
from backend.broker.emergency_stop import run_emergency_stop
from backend.models.database import SessionLocal
from backend.models.models import Alert, Order, Position, RiskAudit, Trade

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PortfolioSummary(BaseModel):
    nav: float
    cash: float
    dailyPnl: float
    dailyPnlPct: float
    allTimePnl: float
    winRate30d: float


class PositionRow(BaseModel):
    ticker: str
    strategy: str
    direction: str
    entryPrice: float
    currentPrice: float
    unrealizedPnl: float
    stopPrice: float | None
    distanceToStop: float
    holdTime: str
    atr: float | None


class ClosedTradeRow(BaseModel):
    ticker: str
    strategy: str
    entry: float
    exit: float
    pnl: float
    pnlPct: float
    holdTime: str
    exitReason: str


class TradeLogRow(BaseModel):
    date: str
    ticker: str
    strategy: str
    direction: str
    entry: float
    exit: float
    pnl: float
    pnlPct: float
    holdTime: str
    exitReason: str
    slippageBps: float | None


class RiskRuleStatus(BaseModel):
    ruleName: str
    scope: str
    status: str
    details: dict[str, Any] | None = None


class StrategyInfo(BaseModel):
    id: str
    name: str
    enabled: bool
    totalTrades: int
    winRate: float
    avgWin: float
    avgLoss: float
    profitFactor: float
    sharpe30d: float
    avgHoldTime: str


class StatusResponse(BaseModel):
    status: str  # ACTIVE | HALTED | PAPER


class EmergencyStopRequest(BaseModel):
    confirm: str


class EmergencyStopResponse(BaseModel):
    ok: bool
    cancelled_orders: int
    flatten_orders_placed: int
    errors: list[str]


class BacktestRequest(BaseModel):
    strategyId: str
    startDate: str
    endDate: str
    startingCapital: float = 100_000.0


class BacktestResponse(BaseModel):
    equityCurve: list[dict[str, Any]]
    maxDrawdown: float
    sharpe: float
    sortino: float
    winRate: float
    profitFactor: float
    totalReturnPct: float
    avgTradePnl: float
    bestTrade: float
    worstTrade: float
    totalTrades: int
    trades: list[dict[str, Any]]


class UpdateStrategyRequest(BaseModel):
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_hold_time(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    """Trading status for banner (PAPER when not connected, ACTIVE when running)."""
    # If we have strategy_engine and IB connected, consider ACTIVE; else PAPER
    engine = getattr(request.app.state, "strategy_engine", None)
    ib = getattr(request.app.state, "ib", None)
    if engine is not None and ib is not None and ib.isConnected():
        return StatusResponse(status="ACTIVE")
    return StatusResponse(status="PAPER")


@router.get("/portfolio", response_model=PortfolioSummary)
async def get_portfolio(request: Request) -> PortfolioSummary:
    """Portfolio summary (NAV, cash, P&L, win rate)."""
    state = getattr(request.app.state, "portfolio_state", None)
    if state is not None:
        snap = state.snapshot()
        # Win rate 30d: compute from trades in DB if needed; placeholder here
        session = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=30)
            subq = session.query(Trade.id).join(Order, Order.id == Trade.entry_order_id).filter(Order.timestamp >= since)
            total = session.query(func.count(Trade.id)).filter(Trade.id.in_(subq)).scalar() or 0
            wins = session.query(func.count(Trade.id)).filter(Trade.id.in_(subq), Trade.pnl_abs > 0).scalar() or 0
            win_rate = (wins / total) if total else 0.0
        except Exception:
            win_rate = 0.0
        finally:
            session.close()
        return PortfolioSummary(
            nav=snap.nav,
            cash=snap.cash,
            dailyPnl=snap.realized_pnl_today + snap.unrealized_pnl,
            dailyPnlPct=snap.drawdown_pct * 100,
            allTimePnl=snap.realized_pnl_today + snap.unrealized_pnl,
            winRate30d=win_rate,
        )
    return PortfolioSummary(
        nav=0.0,
        cash=0.0,
        dailyPnl=0.0,
        dailyPnlPct=0.0,
        allTimePnl=0.0,
        winRate30d=0.0,
    )


@router.get("/positions", response_model=list[PositionRow])
async def get_positions() -> list[PositionRow]:
    """Open positions from DB."""
    session = SessionLocal()
    try:
        rows = session.query(Position).filter(Position.status == "OPEN").all()
        out = []
        for p in rows:
            current = p.avg_price
            unrealized = (current - p.avg_price) * p.quantity if p.direction == "LONG" else (p.avg_price - current) * p.quantity
            stop = p.stop_price or 0.0
            dist = abs(current - stop) if stop else 0.0
            hold_sec = int((datetime.utcnow() - p.entry_time).total_seconds()) if p.entry_time else 0
            out.append(PositionRow(
                ticker=p.ticker,
                strategy=p.strategy_id,
                direction=p.direction,
                entryPrice=p.entry_price,
                currentPrice=current,
                unrealizedPnl=unrealized,
                stopPrice=p.stop_price,
                distanceToStop=dist,
                holdTime=_format_hold_time(hold_sec),
                atr=p.atr_at_entry,
            ))
        return out
    finally:
        session.close()


@router.get("/trades/today", response_model=list[ClosedTradeRow])
async def get_trades_today() -> list[ClosedTradeRow]:
    """Today's closed trades for Overview."""
    session = SessionLocal()
    try:
        today = datetime.utcnow().date()
        trades = (
            session.query(Trade, Position.ticker, Order.limit_price, Order.fill_price)
            .join(Position, Position.id == Trade.position_id)
            .join(Order, Order.id == Trade.entry_order_id)
            .filter(func.date(Order.timestamp) == today)
            .all()
        )
        out = []
        for t, ticker, limit_price, fill_price in trades:
            exit_order = session.query(Order).filter(Order.id == t.exit_order_id).first()
            exit_price = (exit_order.fill_price or exit_order.limit_price or 0.0) if exit_order else 0.0
            entry = fill_price or limit_price or 0.0
            out.append(ClosedTradeRow(
                ticker=ticker,
                strategy=t.strategy_id,
                entry=entry,
                exit=exit_price,
                pnl=t.pnl_abs,
                pnlPct=t.pnl_pct,
                holdTime=_format_hold_time(t.hold_time_sec),
                exitReason=t.exit_reason or "",
            ))
        return out
    finally:
        session.close()


@router.get("/trades", response_model=list[TradeLogRow])
async def get_trades(
    date_from: str | None = None,
    date_to: str | None = None,
    strategy: str | None = None,
    ticker: str | None = None,
) -> list[TradeLogRow]:
    """Trade log with optional filters."""
    session = SessionLocal()
    try:
        q = (
            session.query(Trade, Position.ticker, Position.direction)
            .join(Position, Position.id == Trade.position_id)
        )
        if strategy:
            q = q.filter(Trade.strategy_id == strategy)
        if ticker:
            q = q.filter(Position.ticker == ticker)
        rows = q.order_by(Trade.id.desc()).limit(500).all()
        out = []
        for t, pos_ticker, pos_dir in rows:
            entry_o = session.query(Order).filter(Order.id == t.entry_order_id).first()
            exit_o = session.query(Order).filter(Order.id == t.exit_order_id).first()
            entry_ts = entry_o.timestamp if entry_o else datetime.utcnow()
            entry_price = entry_o.fill_price or entry_o.limit_price or 0.0
            exit_price = exit_o.fill_price or exit_o.limit_price or 0.0
            if date_from and entry_ts.date().isoformat() < date_from:
                continue
            if date_to and entry_ts.date().isoformat() > date_to:
                continue
            out.append(TradeLogRow(
                date=entry_ts.date().isoformat(),
                ticker=pos_ticker,
                strategy=t.strategy_id,
                direction=pos_dir or "",
                entry=entry_price,
                exit=exit_price,
                pnl=t.pnl_abs,
                pnlPct=t.pnl_pct,
                holdTime=_format_hold_time(t.hold_time_sec),
                exitReason=t.exit_reason or "",
                slippageBps=t.slippage_bps,
            ))
        return out
    finally:
        session.close()


@router.get("/risk", response_model=dict[str, Any])
async def get_risk(request: Request) -> dict[str, Any]:
    """Risk state: rules, daily loss gauge, recent audit."""
    state = getattr(request.app.state, "portfolio_state", None)
    session = SessionLocal()
    try:
        audit = (
            session.query(RiskAudit)
            .order_by(RiskAudit.timestamp.desc())
            .limit(50)
            .all()
        )
        rules = [
            RiskRuleStatus(ruleName=a.rule_name, scope=a.scope, status=a.status, details=a.details)
            for a in audit
        ]
        daily_loss_pct = state.daily_drawdown_pct() * 100 if state else 0.0
        daily_limit_pct = 3.0
        return {
            "rules": rules,
            "dailyLossPct": daily_loss_pct,
            "dailyLossLimitPct": daily_limit_pct,
        }
    finally:
        session.close()


@router.get("/strategies", response_model=list[StrategyInfo])
async def get_strategies(request: Request) -> list[StrategyInfo]:
    """Strategy list with enabled flag and stats from DB."""
    cfg = getattr(request.app.state, "cfg", None)
    if not cfg:
        return []
    names = {
        "momentum_breakout": "Momentum Breakout",
        "stat_mean_reversion": "Stat Mean Reversion",
        "sentiment_catalyst": "Sentiment Catalyst",
    }
    session = SessionLocal()
    try:
        result = []
        for sid, sc in cfg.strategies.items():
            total = session.query(func.count(Trade.id)).filter(Trade.strategy_id == sid).scalar() or 0
            wins = session.query(func.count(Trade.id)).filter(Trade.strategy_id == sid, Trade.pnl_abs > 0).scalar() or 0
            win_rate = (wins / total) if total else 0.0
            avg_win = session.query(func.avg(Trade.pnl_abs)).filter(Trade.strategy_id == sid, Trade.pnl_abs > 0).scalar() or 0.0
            avg_loss = session.query(func.avg(Trade.pnl_abs)).filter(Trade.strategy_id == sid, Trade.pnl_abs < 0).scalar() or 0.0
            result.append(StrategyInfo(
                id=sid,
                name=names.get(sid, sid),
                enabled=sc.enabled,
                totalTrades=total,
                winRate=win_rate,
                avgWin=float(avg_win),
                avgLoss=float(avg_loss),
                profitFactor=abs(avg_win / avg_loss) if avg_loss else 0.0,
                sharpe30d=0.0,
                avgHoldTime="-",
            ))
        return result
    finally:
        session.close()


@router.post("/strategies/{strategy_id}", response_model=StrategyInfo)
async def update_strategy(
    strategy_id: str, body: UpdateStrategyRequest, request: Request
) -> StrategyInfo:
    """
    Lightweight strategy config update. Currently only supports toggling enabled flag
    in the in-memory AppConfig; changes are not persisted to disk.
    """
    cfg = getattr(request.app.state, "cfg", None)
    if not cfg or strategy_id not in cfg.strategies:
        raise RuntimeError(f"Unknown strategy_id {strategy_id}")

    sc = cfg.strategies[strategy_id]
    if body.enabled is not None:
        sc.enabled = body.enabled

    # Re-read stats from DB for this single strategy
    names = {
        "momentum_breakout": "Momentum Breakout",
        "stat_mean_reversion": "Stat Mean Reversion",
        "sentiment_catalyst": "Sentiment Catalyst",
    }
    session = SessionLocal()
    try:
        total = (
            session.query(func.count(Trade.id))
            .filter(Trade.strategy_id == strategy_id)
            .scalar()
            or 0
        )
        wins = (
            session.query(func.count(Trade.id))
            .filter(Trade.strategy_id == strategy_id, Trade.pnl_abs > 0)
            .scalar()
            or 0
        )
        win_rate = (wins / total) if total else 0.0
        avg_win = (
            session.query(func.avg(Trade.pnl_abs))
            .filter(Trade.strategy_id == strategy_id, Trade.pnl_abs > 0)
            .scalar()
            or 0.0
        )
        avg_loss = (
            session.query(func.avg(Trade.pnl_abs))
            .filter(Trade.strategy_id == strategy_id, Trade.pnl_abs < 0)
            .scalar()
            or 0.0
        )
        return StrategyInfo(
            id=strategy_id,
            name=names.get(strategy_id, strategy_id),
            enabled=sc.enabled,
            totalTrades=total,
            winRate=win_rate,
            avgWin=float(avg_win),
            avgLoss=float(avg_loss),
            profitFactor=abs(avg_win / avg_loss) if avg_loss else 0.0,
            sharpe30d=0.0,
            avgHoldTime="-",
        )
    finally:
        session.close()


@router.post("/backtest", response_model=BacktestResponse)
async def post_backtest(request: Request, body: BacktestRequest) -> BacktestResponse:
    """Run a backtest for the given strategy and date range. Uses config watchlist."""
    from datetime import date as date_type
    cfg = getattr(request.app.state, "cfg", None)
    if not cfg or not cfg.watchlist:
        # Fallback tickers if no config
        tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "META"]
    else:
        tickers = list(cfg.watchlist)
    try:
        start = date_type.fromisoformat(body.startDate)
        end = date_type.fromisoformat(body.endDate)
    except ValueError:
        start = date_type(2024, 1, 1)
        end = date_type(2024, 12, 31)
    result = await asyncio.to_thread(
        run_backtest,
        body.strategyId,
        tickers,
        start,
        end,
        body.startingCapital,
    )
    return BacktestResponse(
        equityCurve=result.equity_curve,
        maxDrawdown=result.max_drawdown_pct,
        sharpe=result.sharpe,
        sortino=result.sortino,
        winRate=result.win_rate,
        profitFactor=result.profit_factor,
        totalReturnPct=result.total_return_pct,
        avgTradePnl=result.avg_trade_pnl,
        bestTrade=result.best_trade,
        worstTrade=result.worst_trade,
        totalTrades=result.total_trades,
        trades=result.trades,
    )


@router.post("/emergency-stop", response_model=EmergencyStopResponse)
async def post_emergency_stop(request: Request, body: EmergencyStopRequest) -> EmergencyStopResponse:
    """Cancel all open orders and flatten all positions via IBKR. Requires body.confirm == 'CONFIRM'."""
    if body.confirm != "CONFIRM":
        return EmergencyStopResponse(
            ok=False,
            cancelled_orders=0,
            flatten_orders_placed=0,
            errors=["Confirmation required: send { \"confirm\": \"CONFIRM\" } to execute."],
        )
    ib = getattr(request.app.state, "ib", None)
    result = await run_emergency_stop(ib)
    return EmergencyStopResponse(
        ok=len(result.errors) == 0,
        cancelled_orders=result.cancelled_orders,
        flatten_orders_placed=result.flatten_orders_placed,
        errors=result.errors,
    )


@router.get("/alerts", response_model=list[dict[str, Any]])
async def get_alerts() -> list[dict[str, Any]]:
    """Recent alerts from DB."""
    session = SessionLocal()
    try:
        rows = session.query(Alert).order_by(Alert.timestamp.desc()).limit(50).all()
        return [
            {"id": str(a.id), "time": a.timestamp.isoformat() if a.timestamp else "", "level": a.level, "message": a.message}
            for a in rows
        ]
    finally:
        session.close()
