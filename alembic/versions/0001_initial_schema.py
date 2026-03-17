"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ib_account_id", sa.String(length=32), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_accounts_ib_account_id", "accounts", ["ib_account_id"], unique=True)

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acknowledged", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("starting_capital", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("summary_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "config_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("user", sa.String(length=64), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )

    op.create_table(
        "ohlcv_daily",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("adj_close", sa.Float, nullable=True),
        sa.Column("volume", sa.Float, nullable=False),
    )
    op.create_index("ix_ohlcv_daily_ticker", "ohlcv_daily", ["ticker"], unique=False)
    op.create_index("ix_ohlcv_daily_date", "ohlcv_daily", ["date"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("avg_price", sa.Float, nullable=False),
        sa.Column("entry_time", sa.DateTime, nullable=False),
        sa.Column("stop_price", sa.Float, nullable=True),
        sa.Column("target_price", sa.Float, nullable=True),
        sa.Column("atr_at_entry", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("exit_time", sa.DateTime, nullable=True),
        sa.Column("exit_reason", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_positions_ticker", "positions", ["ticker"], unique=False)
    op.create_index("ix_positions_status", "positions", ["status"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("limit_price", sa.Float, nullable=True),
        sa.Column("stop_price", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fill_price", sa.Float, nullable=True),
        sa.Column("fill_qty", sa.Float, nullable=True),
        sa.Column("slippage_bps", sa.Float, nullable=True),
        sa.Column("ibkr_order_id", sa.Integer, nullable=True),
        sa.Column("oca_group_id", sa.String(length=64), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("time_in_force", sa.String(length=16), nullable=True),
    )
    op.create_index("ix_orders_ticker", "orders", ["ticker"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("indicator_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("ix_signals_ticker", "signals", ["ticker"], unique=False)
    op.create_index("ix_signals_strategy", "signals", ["strategy_id"], unique=False)

    op.create_table(
        "risk_audit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("rule_name", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("position_id", sa.Integer, sa.ForeignKey("positions.id"), nullable=True),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("position_id", sa.Integer, sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("entry_order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("exit_order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("pnl_abs", sa.Float, nullable=False),
        sa.Column("pnl_pct", sa.Float, nullable=False),
        sa.Column("hold_time_sec", sa.Integer, nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("exit_reason", sa.String(length=64), nullable=False),
        sa.Column("slippage_bps", sa.Float, nullable=True),
    )

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("backtest_run_id", sa.Integer, sa.ForeignKey("backtest_runs.id"), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("entry_time", sa.DateTime, nullable=False),
        sa.Column("exit_time", sa.DateTime, nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=False),
        sa.Column("pnl_abs", sa.Float, nullable=False),
        sa.Column("pnl_pct", sa.Float, nullable=False),
        sa.Column("hold_time_sec", sa.Integer, nullable=False),
        sa.Column("indicator_snapshot_entry", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exit_reason", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("backtest_trades")
    op.drop_table("trades")
    op.drop_table("risk_audit")
    op.drop_table("signals")
    op.drop_table("orders")
    op.drop_table("positions")
    op.drop_table("ohlcv_daily")
    op.drop_table("config_snapshots")
    op.drop_table("backtest_runs")
    op.drop_table("alerts")
    op.drop_index("ix_accounts_ib_account_id", table_name="accounts")
    op.drop_table("accounts")

