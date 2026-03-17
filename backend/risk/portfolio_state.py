from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from backend.models.database import SessionLocal
from backend.models.models import Account, OHLCVDaily, Position


@dataclass
class PositionSnapshot:
    ticker: str
    quantity: float
    avg_price: float
    direction: str
    strategy_id: str
    sector: str | None = None


@dataclass
class PortfolioSnapshot:
    nav: float
    cash: float
    realized_pnl_today: float
    unrealized_pnl: float
    drawdown_pct: float
    positions: List[PositionSnapshot] = field(default_factory=list)


class PortfolioState:
    """
    Lightweight in-memory cache of portfolio state, backed by IBKR and Postgres.
    """

    def __init__(self, account_id: int):
        self.account_id = account_id
        self._cash: float = 0.0
        self._nav: float = 0.0
        self._realized_pnl_today: float = 0.0
        self._unrealized_pnl: float = 0.0
        self._opening_nav: float | None = None
        self._positions: Dict[str, PositionSnapshot] = {}

    def load_from_db(self) -> None:
        session = SessionLocal()
        try:
            account = (
                session.query(Account)
                .filter(Account.id == self.account_id)
                .one_or_none()
            )
            if account is None:
                return

            # simple version: recompute from open positions and latest close
            positions = (
                session.query(Position)
                .filter(
                    Position.account_id == self.account_id,
                    Position.status == "OPEN",
                )
                .all()
            )
            self._positions.clear()
            total_value = 0.0
            unrealized = 0.0

            today = datetime.utcnow().date()
            for p in positions:
                price = self._latest_close(session, p.ticker, today) or p.avg_price
                pos_val = price * p.quantity
                total_value += pos_val
                direction_mult = 1.0 if p.direction == "LONG" else -1.0
                unrealized += direction_mult * (price - p.avg_price) * p.quantity
                self._positions[p.ticker] = PositionSnapshot(
                    ticker=p.ticker,
                    quantity=p.quantity,
                    avg_price=p.avg_price,
                    direction=p.direction,
                    strategy_id=p.strategy_id,
                )

            # for now assume cash derived from NAV and positions value;
            # production will use IBKR account summary
            self._unrealized_pnl = unrealized
            self._nav = total_value + self._cash
            if self._opening_nav is None:
                self._opening_nav = self._nav
        finally:
            session.close()

    @staticmethod
    def _latest_close(session, ticker: str, today) -> float | None:
        row = (
            session.query(OHLCVDaily)
            .filter(OHLCVDaily.ticker == ticker, OHLCVDaily.date <= today)
            .order_by(OHLCVDaily.date.desc())
            .first()
        )
        return float(row.close) if row else None

    def nav(self) -> float:
        return self._nav

    def cash_available(self) -> float:
        return self._cash

    def daily_drawdown_pct(self) -> float:
        if not self._opening_nav or self._opening_nav == 0:
            return 0.0
        return (self._nav - self._opening_nav) / self._opening_nav

    def snapshot(self) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            nav=self._nav,
            cash=self._cash,
            realized_pnl_today=self._realized_pnl_today,
            unrealized_pnl=self._unrealized_pnl,
            drawdown_pct=self.daily_drawdown_pct(),
            positions=list(self._positions.values()),
        )

