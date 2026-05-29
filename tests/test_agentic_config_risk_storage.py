from pathlib import Path

import pytest

from tradingagents.agentic.config import AgenticConfig
from tradingagents.agentic.execution import ShadowExecutionGateway, apply_fill_to_portfolio
from tradingagents.agentic.models import (
    Fill,
    MarketSnapshot,
    OrderSide,
    PortfolioState,
    Position,
    ProposedOrder,
)
from tradingagents.agentic.risk import RiskEngine
from tradingagents.agentic.robinhood import LiveTradingDisabledError, RobinhoodMCPGateway
from tradingagents.agentic.storage import SQLiteStore


def _snapshot(**overrides):
    data = {
        "ticker": "AAPL",
        "as_of": "2026-05-29",
        "price": 100.0,
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "close": 100.0,
        "volume": 1_000_000,
        "avg_volume_20d": 1_000_000,
        "volatility_20d": 0.2,
    }
    data.update(overrides)
    return MarketSnapshot(**data)


def _order(**overrides):
    data = {
        "ticker": "AAPL",
        "as_of": "2026-05-29",
        "side": OrderSide.BUY,
        "quantity": 1.0,
        "limit_price": 100.0,
        "notional": 100.0,
        "rationale": "test",
    }
    data.update(overrides)
    return ProposedOrder(**data)


@pytest.mark.unit
def test_agentic_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_TICKERS", "aapl,msft")
    monkeypatch.setenv("AGENTIC_SELECTED_ANALYSTS", "market,news")
    monkeypatch.setenv("AGENTIC_DB_PATH", str(tmp_path / "shadow.sqlite3"))
    monkeypatch.setenv("AGENTIC_INITIAL_CASH", "12345")
    monkeypatch.setenv("AGENTIC_RESEARCH_ENABLED", "false")

    config = AgenticConfig.from_env()

    assert config.tickers == ("AAPL", "MSFT")
    assert config.selected_analysts == ("market", "news")
    assert config.db_path == Path(tmp_path / "shadow.sqlite3")
    assert config.initial_cash == 12345
    assert config.research_enabled is False


@pytest.mark.unit
def test_risk_blocks_oversized_sell_illiquid_and_loss_limit():
    config = AgenticConfig(
        max_order_notional=50,
        max_position_weight=0.5,
        min_avg_volume=500_000,
        daily_loss_limit_pct=0.02,
    )
    risk = RiskEngine(config)
    portfolio = PortfolioState(as_of="2026-05-29", cash=1_000, equity_value=1_000, buying_power=1_000, daily_pnl=-25)

    result = risk.evaluate(
        _order(side=OrderSide.SELL, notional=100),
        _snapshot(avg_volume_20d=100),
        portfolio,
        {},
    )

    assert not result.approved
    assert "Order exceeds max_order_notional" in result.reasons
    assert "Sell, short, margin, options, and derivatives orders are blocked in v1" in result.reasons
    assert "Average 20-day volume is below liquidity threshold" in result.reasons
    assert "Daily loss limit reached" in result.reasons


@pytest.mark.unit
def test_risk_blocks_position_cap():
    config = AgenticConfig(max_order_notional=500, max_position_weight=0.05, min_avg_volume=1)
    portfolio = PortfolioState(as_of="2026-05-29", cash=10_000, equity_value=10_000, buying_power=10_000)

    result = RiskEngine(config).evaluate(
        _order(notional=200),
        _snapshot(),
        portfolio,
        {"AAPL": Position(ticker="AAPL", quantity=4, avg_price=100, market_price=100)},
    )

    assert not result.approved
    assert "Projected position exceeds max_position_weight" in result.reasons


@pytest.mark.unit
def test_sqlite_storage_and_shadow_fill_update_portfolio(tmp_path):
    store = SQLiteStore(tmp_path / "shadow.sqlite3")
    store.initialize()
    state = store.ensure_portfolio_state("2026-05-29", 1_000)
    assert state.cash == 1_000

    order = _order(limit_price=101, notional=101)
    order_id = store.record_order(order)
    fill = ShadowExecutionGateway(AgenticConfig(shadow_fill_slippage_bps=0)).execute(order_id, order, _snapshot())
    fill_id = store.record_fill(fill)
    new_state = apply_fill_to_portfolio(store, fill)

    assert fill_id == 1
    assert store.count_rows("proposed_orders") == 1
    assert store.count_rows("fills") == 1
    assert store.get_position("AAPL").quantity == 1
    assert new_state.cash == 900
    assert new_state.equity_value == 1_000


@pytest.mark.unit
def test_robinhood_gateway_is_disabled():
    gateway = RobinhoodMCPGateway()
    with pytest.raises(LiveTradingDisabledError):
        gateway.place_equity_order(_order())
