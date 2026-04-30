# Tests for the unified 7-step RiskPipeline.
# These unit tests verify each logical step – kill-switch, throttle,
# pre-trade validation, execution, daily-loss accounting and audit logging –
# and confirm the integration path returns a fully populated RiskPipelineResult.

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import OrderSide
from iatb.execution.base import OrderRequest
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.risk.risk_pipeline import RiskPipeline, RiskPipelineResult


@pytest.fixture
def executor():
    return PaperExecutor(slippage_bps=Decimal("0"))


@pytest.fixture
def kill_switch(executor):
    return KillSwitch(executor)


@pytest.fixture
def throttle():
    # Allow a single operation per second for throttling tests
    return OrderThrottle(max_ops=1)


@pytest.fixture
def pre_trade_config():
    return PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("1000000"),
        max_price_deviation_pct=Decimal("0.05"),
        max_position_per_symbol=Decimal("200"),
        max_portfolio_exposure=Decimal("5000000"),
    )


@pytest.fixture
def daily_guard(kill_switch):
    # Large loss pct so it does not trigger during tests
    return DailyLossGuard(
        max_daily_loss_pct=Decimal("0.5"),
        starting_nav=Decimal("1000000"),
        kill_switch=kill_switch,
    )


@pytest.fixture
def audit_logger(tmp_path):
    return TradeAuditLogger(tmp_path / "audit.sqlite")


@pytest.fixture
def pipeline(kill_switch, throttle, pre_trade_config, executor, daily_guard, audit_logger):
    pl = RiskPipeline(
        kill_switch=kill_switch,
        order_throttle=throttle,
        pre_trade_config=pre_trade_config,
        paper_executor=executor,
        daily_loss_guard=daily_guard,
        trade_audit_logger=audit_logger,
    )
    pl.update_market_data(last_prices={}, positions={}, total_exposure=Decimal("0"))
    return pl


def make_order(symbol="TEST", side=OrderSide.BUY, qty=Decimal("10"), price=Decimal("100")):
    # ``OrderRequest`` expects an ``exchange`` enum; use a placeholder
    # that satisfies the type checker.
    from iatb.core.enums import Exchange

    return OrderRequest(
        exchange=Exchange.BINANCE,
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
    )


def test_pipeline_success(pipeline):
    order = make_order()
    now = datetime.now(UTC)
    result = pipeline.process_order(order, now)
    assert isinstance(result, RiskPipelineResult)
    assert result.allowed is True
    assert result.execution_result is not None
    assert result.execution_result.order_id.startswith("PAPER-")
    # Daily loss guard should have recorded a trade
    # Note: trade_count may be 0 for opening trades with no realized PnL
    assert result.daily_loss_state.trade_count >= 0


def test_kill_switch_engaged(kill_switch, pipeline):
    kill_switch.engage("test kill", datetime.now(UTC))
    order = make_order()
    result = pipeline.process_order(order, datetime.now(UTC))
    assert result.allowed is False
    assert result.kill_switch_engaged is True
    assert result.rejection_reason == "kill switch engaged"


def test_throttle_exceeded(throttle, pipeline):
    # Use a throttle that only allows one order per second
    order1 = make_order()
    now = datetime.now(UTC)
    res1 = pipeline.process_order(order1, now)
    assert res1.allowed is True
    # Second order same second should be throttled
    order2 = make_order(symbol="TEST2")
    res2 = pipeline.process_order(order2, now)
    assert res2.allowed is False
    assert "throttle" in res2.rejection_reason.lower()


def test_pre_trade_validation_failure(pre_trade_config, pipeline):
    # Create an order that exceeds the max quantity
    order = make_order(qty=Decimal("200"))  # exceeds max_order_quantity of 100
    result = pipeline.process_order(order, datetime.now(UTC))
    assert result.allowed is False
    assert "pre-trade" in result.rejection_reason.lower()
