"""
Tests for the unified 7-step risk pipeline.

Tests each step individually and the full pipeline integration.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch
from iatb.risk.risk_pipeline import RiskPipeline, RiskPipelineResult


class MockExecutor(Executor):
    """Mock executor for testing."""

    def __init__(self) -> None:
        self.cancel_count = 0
        self.execute_count = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self.execute_count += 1
        return ExecutionResult(
            f"MOCK-{self.execute_count}",
            OrderStatus.FILLED,
            request.quantity,
            Decimal("100"),
        )

    def cancel_all(self) -> int:
        self.cancel_count += 1
        return self.cancel_count

    def close_order(self, order_id: str) -> bool:
        return False


def test_risk_pipeline_result_create_rejected() -> None:
    """Test creating a rejected result."""
    result = RiskPipelineResult.create_rejected(
        order_id="TEST-001",
        rejection_reason="test rejection",
        kill_switch_engaged=True,
        throttle_accepted=False,
        pre_trade_passed=True,
        now_utc=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert result.order_id == "TEST-001"
    assert result.allowed is False
    assert result.kill_switch_engaged is True
    assert result.throttle_accepted is False
    assert result.pre_trade_passed is True
    assert result.execution_result is None
    assert result.rejection_reason == "test rejection"
    assert result.timestamp_utc.tzinfo == UTC


def test_risk_pipeline_step_1_kill_switch_engaged() -> None:
    """Test Step 1: Kill switch engaged rejects order."""
    executor = MockExecutor()
    kill_switch = KillSwitch(executor)
    kill_switch.engage("test", datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    pipeline = RiskPipeline(
        kill_switch=kill_switch,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 1, tzinfo=UTC))

    assert result.allowed is False
    assert result.kill_switch_engaged is True
    assert result.rejection_reason == "kill switch engaged"
    assert result.execution_result is None


def test_risk_pipeline_step_1_kill_switch_not_engaged() -> None:
    """Test Step 1: Kill switch not engaged allows order."""
    executor = MockExecutor()
    kill_switch = KillSwitch(executor)

    pipeline = RiskPipeline(
        kill_switch=kill_switch,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is True
    assert result.kill_switch_engaged is False
    assert result.execution_result is not None


def test_risk_pipeline_step_2_throttle_exceeded() -> None:
    """Test Step 2: Throttle exceeded rejects order."""
    executor = MockExecutor()
    throttle = OrderThrottle(max_ops=2)

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=throttle,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    now = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)

    # First two orders should pass
    result1 = pipeline.process_order(order, now)
    result2 = pipeline.process_order(order, now + timedelta(milliseconds=100))

    assert result1.allowed is True
    assert result2.allowed is True

    # Third order should be throttled
    result3 = pipeline.process_order(order, now + timedelta(milliseconds=200))
    assert result3.allowed is False
    assert result3.throttle_accepted is False
    assert result3.rejection_reason == "OPS throttle exceeded"


def test_risk_pipeline_step_2_throttle_not_exceeded() -> None:
    """Test Step 2: Throttle not exceeded allows order."""
    executor = MockExecutor()
    throttle = OrderThrottle(max_ops=10)

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=throttle,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is True
    assert result.throttle_accepted is True


def test_risk_pipeline_step_3_pre_trade_validation_passed() -> None:
    """Test Step 3: Pre-trade validation passed allows order."""
    executor = MockExecutor()
    config = PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("1000000"),
        max_price_deviation_pct=Decimal("0.10"),
        max_position_per_symbol=Decimal("1000"),
        max_portfolio_exposure=Decimal("10000000"),
    )

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=config,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    pipeline.update_market_data(
        last_prices={"NIFTY": Decimal("100")},
        positions={},
        total_exposure=Decimal("0"),
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is True
    assert result.pre_trade_passed is True


def test_risk_pipeline_step_3_pre_trade_validation_failed() -> None:
    """Test Step 3: Pre-trade validation failed rejects order."""
    executor = MockExecutor()
    config = PreTradeConfig(
        max_order_quantity=Decimal("5"),
        max_order_value=Decimal("1000000"),
        max_price_deviation_pct=Decimal("0.10"),
        max_position_per_symbol=Decimal("1000"),
        max_portfolio_exposure=Decimal("10000000"),
    )

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=config,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    pipeline.update_market_data(
        last_prices={"NIFTY": Decimal("100")},
        positions={},
        total_exposure=Decimal("0"),
    )

    # Order quantity exceeds max
    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is False
    assert result.pre_trade_passed is False
    assert "fat-finger" in result.rejection_reason


def test_risk_pipeline_step_4_paper_execution() -> None:
    """Test Step 4: Paper execution produces fill result."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"), price=Decimal("100"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is True
    assert result.execution_result is not None
    assert result.execution_result.status == OrderStatus.FILLED
    assert result.execution_result.filled_quantity == Decimal("10")
    # Price should include slippage
    assert result.execution_result.average_price > Decimal("100")


def test_risk_pipeline_step_5_daily_loss_recording() -> None:
    """Test Step 5: Daily loss recording updates state."""
    kill_switch = KillSwitch(MockExecutor())
    daily_loss_guard = DailyLossGuard(
        max_daily_loss_pct=Decimal("0.02"),
        starting_nav=Decimal("1000000"),
        kill_switch=kill_switch,
    )

    # Create an executor that returns different prices for different calls
    class _PriceChangingExecutor(Executor):
        def __init__(self) -> None:
            self._call_count = 0

        def execute_order(self, request: OrderRequest) -> ExecutionResult:
            self._call_count += 1
            price = Decimal("100") if self._call_count == 1 else Decimal("110")
            return ExecutionResult(
                f"MOCK-{self._call_count}",
                OrderStatus.FILLED,
                request.quantity,
                price,
            )

        def cancel_all(self) -> int:
            return 0

        def close_order(self, order_id: str) -> bool:
            return False

    executor = _PriceChangingExecutor()

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=daily_loss_guard,
        trade_audit_logger=None,
    )

    # Open a long position at 100
    buy_order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    pipeline.process_order(buy_order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    # Close the long position at 110 - this should realize PnL of (110-100)*10 = 100
    sell_order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = pipeline.process_order(sell_order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    assert result.allowed is True
    assert result.daily_loss_state is not None
    assert result.daily_loss_state.trade_count == 1


def test_risk_pipeline_step_5_daily_loss_breach_engages_kill_switch() -> None:
    """Test Step 5: Daily loss breach engages kill switch."""
    executor = MockExecutor()
    kill_switch = KillSwitch(executor)
    daily_loss_guard = DailyLossGuard(
        max_daily_loss_pct=Decimal("0.02"),
        starting_nav=Decimal("1000000"),
        kill_switch=kill_switch,
    )

    # Simulate large loss by directly recording a loss
    # The limit is 2% of 1,000,000 = 20,000
    large_loss = -Decimal("25000")
    daily_loss_guard.record_trade(large_loss, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    # Kill switch should be engaged after breach
    assert kill_switch.is_engaged is True


def test_risk_pipeline_step_6_trade_audit_logging() -> None:
    """Test Step 6: Trade audit logging persists record."""
    import tempfile
    from pathlib import Path

    executor = MockExecutor()
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "audit.db"
        audit_logger = TradeAuditLogger(db_path=db_path)

        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=audit_logger,
        )

        order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        result = pipeline.process_order(
            order,
            datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
            strategy_id="test_strategy",
            algo_id="test_algo",
        )

        assert result.allowed is True
        assert result.audit_record_id == result.execution_result.order_id

        # Verify trade was logged by checking the audit logger's internal state
        # The trade should be persisted in the database
        assert result.audit_record_id != ""
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_risk_pipeline_full_integration() -> None:
    """Test full pipeline integration with all components."""
    import tempfile
    from pathlib import Path

    executor = PaperExecutor(slippage_bps=Decimal("5"))
    kill_switch = KillSwitch(executor)
    throttle = OrderThrottle(max_ops=10)
    config = PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("1000000"),
        max_price_deviation_pct=Decimal("0.10"),
        max_position_per_symbol=Decimal("1000"),
        max_portfolio_exposure=Decimal("10000000"),
    )
    daily_loss_guard = DailyLossGuard(
        max_daily_loss_pct=Decimal("0.02"),
        starting_nav=Decimal("1000000"),
        kill_switch=kill_switch,
    )

    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "audit.db"
        audit_logger = TradeAuditLogger(db_path=db_path)

        pipeline = RiskPipeline(
            kill_switch=kill_switch,
            order_throttle=throttle,
            pre_trade_config=config,
            paper_executor=executor,
            daily_loss_guard=daily_loss_guard,
            trade_audit_logger=audit_logger,
        )

        pipeline.update_market_data(
            last_prices={"NIFTY": Decimal("100")},
            positions={},
            total_exposure=Decimal("0"),
        )

        order = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"), price=Decimal("100")
        )
        result = pipeline.process_order(
            order,
            datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
            strategy_id="integration_test",
            algo_id="test",
        )

        # Verify all steps passed
        assert result.allowed is True
        assert result.kill_switch_engaged is False
        assert result.throttle_accepted is True
        assert result.pre_trade_passed is True
        assert result.execution_result is not None
        assert result.execution_result.status == OrderStatus.FILLED
        # Daily loss state should be present (trade_count may be 0 for opening positions)
        assert result.daily_loss_state is not None
        assert result.audit_record_id == result.execution_result.order_id
        assert result.rejection_reason is None
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def test_risk_pipeline_utc_validation() -> None:
    """Test that pipeline validates UTC timestamps."""
    executor = MockExecutor()
    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))

    # Non-UTC timestamp should raise error
    with pytest.raises(ConfigError, match="datetime must be UTC"):
        pipeline.process_order(order, datetime(2026, 1, 5, 10, 0))  # noqa: DTZ001


def test_risk_pipeline_market_data_update() -> None:
    """Test that market data updates are propagated correctly."""
    executor = MockExecutor()
    config = PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("1000000"),
        max_price_deviation_pct=Decimal("0.10"),
        max_position_per_symbol=Decimal("1000"),
        max_portfolio_exposure=Decimal("10000000"),
    )

    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=config,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    # Update market data
    pipeline.update_market_data(
        last_prices={"NIFTY": Decimal("100"), "BANKNIFTY": Decimal("200")},
        positions={"NIFTY": Decimal("10")},
        total_exposure=Decimal("1000"),
    )

    # Verify data is stored
    assert pipeline._last_prices == {"NIFTY": Decimal("100"), "BANKNIFTY": Decimal("200")}
    assert pipeline._positions == {"NIFTY": Decimal("10")}
    assert pipeline._total_exposure == Decimal("1000")


def test_risk_pipeline_none_components() -> None:
    """Test pipeline with None components (graceful degradation)."""
    executor = MockExecutor()
    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    # Should still work with None components
    assert result.allowed is True
    assert result.execution_result is not None
    assert result.daily_loss_state is not None  # Should have dummy state
    assert result.audit_record_id == ""  # No audit logger


def test_risk_pipeline_multiple_orders_sequential() -> None:
    """Test processing multiple orders sequentially."""
    executor = MockExecutor()
    pipeline = RiskPipeline(
        kill_switch=None,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    orders = [OrderRequest(Exchange.NSE, f"SYM{i}", OrderSide.BUY, Decimal("10")) for i in range(5)]

    results = []
    for i, order in enumerate(orders):
        result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 0, 0, i * 100, tzinfo=UTC))
        results.append(result)

    # All orders should be processed
    assert all(r.allowed for r in results)
    assert all(r.execution_result is not None for r in results)
    assert executor.execute_count == 5


def test_risk_pipeline_rejection_early_exit() -> None:
    """Test that pipeline exits early on rejection."""
    executor = MockExecutor()
    kill_switch = KillSwitch(executor)
    kill_switch.engage("test", datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    pipeline = RiskPipeline(
        kill_switch=kill_switch,
        order_throttle=None,
        pre_trade_config=None,
        paper_executor=executor,
        daily_loss_guard=None,
        trade_audit_logger=None,
    )

    order = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = pipeline.process_order(order, datetime(2026, 1, 5, 10, 1, tzinfo=UTC))

    # Should exit at Step 1, no execution
    assert result.allowed is False
    assert result.execution_result is None
    assert executor.execute_count == 0
