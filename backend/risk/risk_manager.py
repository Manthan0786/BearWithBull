from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from backend.config import AppConfig
from backend.models.database import SessionLocal
from backend.models.models import Order, RiskAudit, Trade
from backend.risk.portfolio_state import PortfolioState, PortfolioSnapshot


@dataclass
class RuleResult:
    rule_name: str
    scope: str  # POSITION/PORTFOLIO/SESSION
    status: str  # PASS/FAIL/WARN
    details: dict


@dataclass
class RiskDecision:
    allowed: bool
    rule_results: List[RuleResult]
    messages: List[str]


@dataclass
class OrderRequest:
    ticker: str
    strategy_id: str
    direction: str  # BUY/SELL/SHORT/COVER
    quantity: float
    entry_price: float
    stop_price: float | None
    atr: float | None


class RiskManager:
    """
    Centralized risk checks. This is a first pass, focusing on position size,
    max loss per trade, and simple session limits. Additional rules will be
    layered in as the rest of the system is implemented.
    """

    def __init__(self, cfg: AppConfig, portfolio_state: PortfolioState):
        self.cfg = cfg
        self.portfolio_state = portfolio_state
        self._daily_trades: int = 0
        self._consecutive_losses: int = 0
        self._circuit_breaker_until: datetime | None = None

    def assess_order(self, order: OrderRequest, order_id: int | None = None) -> RiskDecision:
        """
        Assess a proposed order and return a RiskDecision.

        If order_id is provided, rule evaluations are also persisted into
        the risk_audit table for later inspection via the Risk API.
        """
        # Refresh consecutive-loss state from today's realized trades so the
        # circuit breaker is driven by actual P&L in the database.
        self._refresh_consecutive_losses_from_db()

        snapshot: PortfolioSnapshot = self.portfolio_state.snapshot()
        nav = snapshot.nav or 0.0

        results: List[RuleResult] = []
        messages: List[str] = []
        allowed = True

        # ------------------------------------------------------------------
        # Position-level: max 5% NAV per position
        # ------------------------------------------------------------------
        max_pos_nav = 0.05 * nav if nav > 0 else float("inf")
        proposed_value = order.entry_price * order.quantity
        if proposed_value > max_pos_nav:
            allowed = False
            messages.append("Position size exceeds 5% NAV limit")
            results.append(
                RuleResult(
                    rule_name="MAX_POSITION_SIZE",
                    scope="POSITION",
                    status="FAIL",
                    details={
                        "nav": nav,
                        "proposed_value": proposed_value,
                        "max_allowed": max_pos_nav,
                    },
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_name="MAX_POSITION_SIZE",
                    scope="POSITION",
                    status="PASS",
                    details={
                        "nav": nav,
                        "proposed_value": proposed_value,
                        "max_allowed": max_pos_nav,
                    },
                )
            )

        # ------------------------------------------------------------------
        # Portfolio-level: cash reserve & total exposure cap
        #
        # We approximate total gross exposure as sum(|qty * avg_price|) for
        # open positions, and ensure that after adding this order we still
        # respect the configured cash reserve percentage.
        # ------------------------------------------------------------------
        cash_reserve_pct = self.cfg.trading.cash_reserve_pct
        # total capital that can be deployed into positions
        deployable_nav = nav * (1.0 - cash_reserve_pct) if nav > 0 else float("inf")
        current_exposure = 0.0
        for pos in snapshot.positions:
            current_exposure += abs(pos.quantity * pos.avg_price)

        proposed_total_exposure = current_exposure + abs(proposed_value)
        if proposed_total_exposure > deployable_nav:
            allowed = False
            messages.append("Order would breach cash reserve limit")
            results.append(
                RuleResult(
                    rule_name="CASH_RESERVE",
                    scope="PORTFOLIO",
                    status="FAIL",
                    details={
                        "nav": nav,
                        "cash_reserve_pct": cash_reserve_pct,
                        "deployable_nav": deployable_nav,
                        "current_exposure": current_exposure,
                        "proposed_exposure": proposed_total_exposure,
                    },
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_name="CASH_RESERVE",
                    scope="PORTFOLIO",
                    status="PASS",
                    details={
                        "nav": nav,
                        "cash_reserve_pct": cash_reserve_pct,
                        "deployable_nav": deployable_nav,
                        "current_exposure": current_exposure,
                        "proposed_exposure": proposed_total_exposure,
                    },
                )
            )

        # ------------------------------------------------------------------
        # Position-level: max 1% loss per trade using stop
        # ------------------------------------------------------------------
        max_loss = 0.01 * nav if nav > 0 else float("inf")
        if order.stop_price is not None:
            direction_mult = 1.0 if order.direction in ("BUY", "LONG") else -1.0
            risk_per_share = direction_mult * (order.entry_price - order.stop_price)
            risk_value = max(risk_per_share, 0) * order.quantity
            if risk_value > max_loss:
                allowed = False
                messages.append("Stop-loss implies >1% NAV risk")
                results.append(
                    RuleResult(
                        rule_name="MAX_LOSS_PER_TRADE",
                        scope="POSITION",
                        status="FAIL",
                        details={
                            "nav": nav,
                            "risk_value": risk_value,
                            "max_allowed": max_loss,
                        },
                    )
                )
            else:
                results.append(
                    RuleResult(
                        rule_name="MAX_LOSS_PER_TRADE",
                        scope="POSITION",
                        status="PASS",
                        details={
                            "nav": nav,
                            "risk_value": risk_value,
                            "max_allowed": max_loss,
                        },
                    )
                )
        else:
            allowed = False
            messages.append("Entry order missing stop-loss")
            results.append(
                RuleResult(
                    rule_name="REQUIRES_STOP_LOSS",
                    scope="POSITION",
                    status="FAIL",
                    details={},
                )
            )

        # ------------------------------------------------------------------
        # Session-level: daily loss limit (drawdown) based on NAV
        # ------------------------------------------------------------------
        daily_limit_pct = self.cfg.trading.daily_loss_limit_pct
        # snapshot.drawdown_pct is (nav - opening_nav) / opening_nav
        drawdown_pct = snapshot.drawdown_pct
        # drawdown_pct is negative when losing; trigger when it breaches -daily_limit_pct
        if drawdown_pct <= -daily_limit_pct:
            allowed = False
            messages.append("Daily loss limit breached")
            results.append(
                RuleResult(
                    rule_name="DAILY_LOSS_LIMIT",
                    scope="SESSION",
                    status="FAIL",
                    details={
                        "drawdown_pct": drawdown_pct,
                        "limit_pct": -daily_limit_pct,
                    },
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_name="DAILY_LOSS_LIMIT",
                    scope="SESSION",
                    status="PASS",
                    details={
                        "drawdown_pct": drawdown_pct,
                        "limit_pct": -daily_limit_pct,
                    },
                )
            )

        # ------------------------------------------------------------------
        # Session-level: consecutive loss circuit breaker
        #
        # When triggered (via record_trade_result), we pause new entries for
        # circuit_breaker_pause_minutes. Here we only enforce the pause window.
        # ------------------------------------------------------------------
        now = datetime.utcnow()
        if self._circuit_breaker_until is not None and now < self._circuit_breaker_until:
            remaining = (self._circuit_breaker_until - now).total_seconds() / 60.0
            allowed = False
            messages.append("Consecutive-loss circuit breaker active")
            results.append(
                RuleResult(
                    rule_name="CONSECUTIVE_LOSS_BREAKER",
                    scope="SESSION",
                    status="FAIL",
                    details={
                        "circuit_breaker_until": self._circuit_breaker_until.isoformat(),
                        "minutes_remaining": round(remaining, 1),
                    },
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_name="CONSECUTIVE_LOSS_BREAKER",
                    scope="SESSION",
                    status="PASS",
                    details={
                        "circuit_breaker_until": (
                            self._circuit_breaker_until.isoformat()
                            if self._circuit_breaker_until
                            else None
                        ),
                    },
                )
            )

        # ------------------------------------------------------------------
        # Session-level: daily trade count
        # ------------------------------------------------------------------
        max_daily = self.cfg.trading.max_daily_trades
        if self._daily_trades >= max_daily:
            allowed = False
            messages.append("Max daily trade count reached")
            results.append(
                RuleResult(
                    rule_name="MAX_DAILY_TRADES",
                    scope="SESSION",
                    status="FAIL",
                    details={"current": self._daily_trades, "max": max_daily},
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_name="MAX_DAILY_TRADES",
                    scope="SESSION",
                    status="PASS",
                    details={"current": self._daily_trades, "max": max_daily},
                )
            )

        decision = RiskDecision(allowed=allowed, rule_results=results, messages=messages)

        # Persist rule evaluations into risk_audit, if possible.
        self._persist_risk_audit(decision, order_id=order_id)

        return decision

    def increment_trade_count(self) -> None:
        self._daily_trades += 1

    def record_trade_result(self, pnl: float) -> None:
        """
        Record the outcome of a closed trade to maintain consecutive-loss
        statistics and trigger the circuit breaker when needed.
        """
        if pnl < 0:
            self._consecutive_losses += 1
            threshold = self.cfg.trading.consecutive_loss_circuit_breaker
            if self._consecutive_losses >= threshold and threshold > 0:
                pause_minutes = self.cfg.trading.circuit_breaker_pause_minutes
                self._circuit_breaker_until = datetime.utcnow() + timedelta(
                    minutes=pause_minutes
                )
                self._consecutive_losses = 0
        else:
            # Reset on any non-negative trade
            self._consecutive_losses = 0

    def _refresh_consecutive_losses_from_db(self) -> None:
        """
        Recompute today's trailing consecutive loss count from the trades table.

        This lets the circuit breaker work end-to-end without needing explicit
        in-code calls at trade close sites: it derives its state from the DB.
        """
        session = SessionLocal()
        try:
            today = datetime.utcnow().date()
            # Join trades to their exit orders to get timestamp ordering
            rows = (
                session.query(Trade, Order)
                .join(Order, Order.id == Trade.exit_order_id)
                .filter(Order.timestamp >= datetime.combine(today, datetime.min.time()))
                .order_by(Order.timestamp.asc())
                .all()
            )
            # Walk from the end to count trailing losing trades
            streak = 0
            for trade, _order in reversed(rows):
                if trade.pnl_abs < 0:
                    streak += 1
                else:
                    break
            self._consecutive_losses = streak

            # If streak meets threshold and breaker not yet set, arm it
            threshold = self.cfg.trading.consecutive_loss_circuit_breaker
            if threshold > 0 and streak >= threshold:
                if self._circuit_breaker_until is None or self._circuit_breaker_until < datetime.utcnow():
                    pause_minutes = self.cfg.trading.circuit_breaker_pause_minutes
                    self._circuit_breaker_until = datetime.utcnow() + timedelta(
                        minutes=pause_minutes
                    )
        finally:
            session.close()

    def _persist_risk_audit(self, decision: RiskDecision, order_id: int | None) -> None:
        """
        Write each RuleResult into risk_audit for later inspection in the
        risk monitor API. Account_id/position_id are left null for now.
        """
        if not decision.rule_results:
            return
        session = SessionLocal()
        try:
            for rr in decision.rule_results:
                model = RiskAudit(
                    account_id=None,
                    rule_name=rr.rule_name,
                    scope=rr.scope,
                    status=rr.status,
                    details=rr.details,
                    order_id=order_id,
                    position_id=None,
                )
                session.add(model)
            session.commit()
        finally:
            session.close()

