import math

from backend.config import AppConfig, TradingConfig
from backend.risk.portfolio_state import PortfolioState
from backend.risk.risk_manager import OrderRequest, RiskManager


def make_cfg(nav: float = 100_000.0) -> AppConfig:
    # strategies not needed for these tests
    return AppConfig(
        trading=TradingConfig(),
        strategies={},
        watchlist=[],
    )


def test_max_position_size_rule():
    cfg = make_cfg()
    ps = PortfolioState(account_id=1)
    ps._nav = 100_000.0  # type: ignore[attr-defined]
    rm = RiskManager(cfg, ps)

    # 5% of 100k = 5k, so 50 shares * 100 = 5k -> ok
    ok_order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=50,
        entry_price=100.0,
        stop_price=95.0,
        atr=None,
    )
    decision_ok = rm.assess_order(ok_order)
    assert decision_ok.allowed is True

    # 6% of NAV -> should fail
    bad_order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=60,
        entry_price=100.0,
        stop_price=95.0,
        atr=None,
    )
    decision_bad = rm.assess_order(bad_order)
    assert decision_bad.allowed is False
    assert any(r.rule_name == "MAX_POSITION_SIZE" and r.status == "FAIL" for r in decision_bad.rule_results)


def test_requires_stop_loss():
    cfg = make_cfg()
    ps = PortfolioState(account_id=1)
    ps._nav = 100_000.0  # type: ignore[attr-defined]
    rm = RiskManager(cfg, ps)

    order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=10,
        entry_price=100.0,
        stop_price=None,
        atr=None,
    )
    decision = rm.assess_order(order)
    assert decision.allowed is False
    assert any(r.rule_name == "REQUIRES_STOP_LOSS" and r.status == "FAIL" for r in decision.rule_results)


def test_max_loss_per_trade_rule():
    cfg = make_cfg()
    ps = PortfolioState(account_id=1)
    ps._nav = 100_000.0  # type: ignore[attr-defined]
    rm = RiskManager(cfg, ps)

    # 1% of NAV = 1000
    # risk per share = 2, 400 shares -> 800 risk -> ok
    ok_order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=400,
        entry_price=100.0,
        stop_price=98.0,
        atr=None,
    )
    decision_ok = rm.assess_order(ok_order)
    assert decision_ok.allowed is True

    # 600 shares * 2 = 1200 > 1000 -> fail
    bad_order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=600,
        entry_price=100.0,
        stop_price=98.0,
        atr=None,
    )
    decision_bad = rm.assess_order(bad_order)
    assert decision_bad.allowed is False
    assert any(r.rule_name == "MAX_LOSS_PER_TRADE" and r.status == "FAIL" for r in decision_bad.rule_results)


def test_max_daily_trades_rule():
    cfg = make_cfg()
    cfg.trading.max_daily_trades = 2
    ps = PortfolioState(account_id=1)
    ps._nav = 100_000.0  # type: ignore[attr-defined]
    rm = RiskManager(cfg, ps)

    order = OrderRequest(
        ticker="AAPL",
        strategy_id="test",
        direction="BUY",
        quantity=10,
        entry_price=100.0,
        stop_price=95.0,
        atr=None,
    )

    # First two trades allowed
    d1 = rm.assess_order(order)
    assert d1.allowed is True
    rm.increment_trade_count()
    d2 = rm.assess_order(order)
    assert d2.allowed is True
    rm.increment_trade_count()

    # Third trade should fail
    d3 = rm.assess_order(order)
    assert d3.allowed is False
    assert any(r.rule_name == "MAX_DAILY_TRADES" and r.status == "FAIL" for r in d3.rule_results)

