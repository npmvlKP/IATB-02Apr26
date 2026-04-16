"""Additional tests for order_manager.py to improve coverage to 90%+."""

import random
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _MockExecutor(Executor):
    def __init__(self) -> None:
        self.cancel_count = 0
        self.executed_orders: list[OrderRequest] = []

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self.executed_orders.append(request)
        return ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("100"))

    def cancel_all(self) -> int:
        self.cancel_count += 1
        return 1


class _MockKillSwitch:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed

    def check_order_allowed(self) -> bool:
        return self.allowed


class _MockOrderThrottle:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.recorded_count = 0

    def check_and_record(self, now: datetime) -> bool:
        _ = now
        if self.allowed:
            self.recorded_count += 1
            return True
        return False


class _MockDailyLossGuard:
    def __init__(self) -> None:
        self.recorded_trades: list[tuple[Decimal, datetime]] = []

    def record_trade(self, pnl: Decimal, timestamp: datetime) -> None:
        self.recorded_trades.append((pnl, timestamp))


class _MockTradeAuditLogger:
    def __init__(self) -> None:
        self.logged_orders: list[tuple[OrderRequest, ExecutionResult, str, str]] = []

    def log_order(
        self, request: OrderRequest, result: ExecutionResult, strategy_id: str, algo_id: str
    ) -> None:
        self.logged_orders.append((request, result, strategy_id, algo_id))


def test_order_manager_constructor_invalid_heartbeat_timeout():
    """Test that invalid heartbeat timeout raises error."""
    with pytest.raises(ConfigError, match="heartbeat_timeout_seconds must be positive"):
        OrderManager(_MockExecutor(), heartbeat_timeout_seconds=0)

    with pytest.raises(ConfigError, match="heartbeat_timeout_seconds must be positive"):
        OrderManager(_MockExecutor(), heartbeat_timeout_seconds=-10)


def test_order_manager_kill_switch_engaged():
    """Test that engaged kill switch rejects orders."""
    executor = _MockExecutor()
    kill_switch = _MockKillSwitch(allowed=False)
    manager = OrderManager(executor, kill_switch=kill_switch)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    with pytest.raises(ConfigError, match="order rejected: kill switch engaged"):
        manager.place_order(request)

    # Order should not be executed
    assert len(executor.executed_orders) == 0


def test_order_manager_throttle_exceeded():
    """Test that throttle rejection works."""
    executor = _MockExecutor()
    throttle = _MockOrderThrottle(allowed=False)
    manager = OrderManager(executor, order_throttle=throttle)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    with pytest.raises(ConfigError, match="order rejected: OPS throttle exceeded"):
        manager.place_order(request)

    # Order should not be executed
    assert len(executor.executed_orders) == 0


def test_order_manager_throttle_records_check():
    """Test that throttle records check on successful order."""
    executor = _MockExecutor()
    throttle = _MockOrderThrottle(allowed=True)
    manager = OrderManager(executor, order_throttle=throttle)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    manager.place_order(request)

    # Throttle should have recorded the check
    assert throttle.recorded_count == 1


def test_order_manager_update_market_data():
    """Test updating market data."""
    executor = _MockExecutor()
    manager = OrderManager(executor)

    last_prices = {"NIFTY": Decimal("10000")}
    positions = {"NIFTY": Decimal("10")}
    total_exposure = Decimal("100000")

    manager.update_market_data(last_prices, positions, total_exposure)

    # Should update internal state
    assert manager._last_prices == last_prices
    assert manager._positions == positions
    assert manager._total_exposure == total_exposure


def test_order_manager_heartbeat_validation():
    """Test heartbeat validation."""
    executor = _MockExecutor()
    manager = OrderManager(executor)

    # Naive datetime should raise error
    with pytest.raises(ConfigError, match="heartbeat_utc must be timezone-aware UTC datetime"):
        manager.receive_heartbeat(datetime(2024, 1, 1, 10, 0))  # noqa: DTZ001

    # Valid UTC datetime should work
    valid_heartbeat = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    manager.receive_heartbeat(valid_heartbeat)
    assert manager._last_heartbeat_utc == valid_heartbeat


def test_order_manager_pnl_long_opening_position():
    """Test PnL recording for opening long position (BUY)."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("100"))
    manager._record_pnl(request, result)

    # No PnL recorded for opening position
    assert len(loss_guard.recorded_trades) == 0


def test_order_manager_pnl_long_closing_position():
    """Test PnL recording for closing long position (SELL)."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # First, open a long position
    manager._position_state["NIFTY"] = (Decimal("10"), Decimal("100"))

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("110"))
    manager._record_pnl(request, result)

    # PnL should be recorded: (110 - 100) * 10 = 100
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")


def test_order_manager_pnl_short_opening_position():
    """Test PnL recording for opening short position (SELL)."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("100"))
    manager._record_pnl(request, result)

    # No PnL recorded for opening position
    assert len(loss_guard.recorded_trades) == 0


def test_order_manager_pnl_short_closing_position():
    """Test PnL recording for closing short position (BUY)."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # First, open a short position
    manager._position_state["NIFTY"] = (Decimal("-10"), Decimal("100"))

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("90"))
    manager._record_pnl(request, result)

    # PnL should be recorded: (100 - 90) * 10 = 100
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")


def test_order_manager_pnl_partial_close_long():
    """Test PnL recording for partial close of long position."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open long position
    manager._position_state["NIFTY"] = (Decimal("20"), Decimal("100"))

    # Partial close: sell 10 out of 20
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("110"))
    manager._record_pnl(request, result)

    # PnL: (110 - 100) * 10 = 100
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")

    # Remaining position should be 10 shares at 100
    assert manager._position_state["NIFTY"] == (Decimal("10"), Decimal("100"))


def test_order_manager_pnl_partial_close_short():
    """Test PnL recording for partial close of short position."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open short position
    manager._position_state["NIFTY"] = (Decimal("-20"), Decimal("100"))

    # Partial close: buy 10 out of 20
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("90"))
    manager._record_pnl(request, result)

    # PnL: (100 - 90) * 10 = 100
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")

    # Remaining position should be -10 shares at 100
    assert manager._position_state["NIFTY"] == (Decimal("-10"), Decimal("100"))


def test_order_manager_pnl_flip_to_long():
    """Test PnL recording when flipping from short to long."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open short position
    manager._position_state["NIFTY"] = (Decimal("-10"), Decimal("100"))

    # Buy 20 to flip to long
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("20"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("20"), Decimal("90"))
    manager._record_pnl(request, result)

    # PnL: (100 - 90) * 10 = 100 (closing short)
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")

    # New position: 10 shares long at 90
    assert manager._position_state["NIFTY"] == (Decimal("10"), Decimal("90"))


def test_order_manager_pnl_flip_to_short():
    """Test PnL recording when flipping from long to short."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open long position
    manager._position_state["NIFTY"] = (Decimal("10"), Decimal("100"))

    # Sell 20 to flip to short
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("20"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("20"), Decimal("110"))
    manager._record_pnl(request, result)

    # PnL: (110 - 100) * 10 = 100 (closing long)
    assert len(loss_guard.recorded_trades) == 1
    assert loss_guard.recorded_trades[0][0] == Decimal("100")

    # New position: -10 shares short at 110
    assert manager._position_state["NIFTY"] == (Decimal("-10"), Decimal("110"))


def test_order_manager_pnl_adding_to_long_position():
    """Test PnL recording when adding to long position."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open long position
    manager._position_state["NIFTY"] = (Decimal("10"), Decimal("100"))

    # Add to position: buy 10 more at 110
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("110"))
    manager._record_pnl(request, result)

    # No PnL recorded
    assert len(loss_guard.recorded_trades) == 0

    # New position: 20 shares with weighted avg (100+110)/2 = 105
    assert manager._position_state["NIFTY"] == (Decimal("20"), Decimal("105"))


def test_order_manager_pnl_adding_to_short_position():
    """Test PnL recording when adding to short position."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    # Open short position
    manager._position_state["NIFTY"] = (Decimal("-10"), Decimal("100"))

    # Add to position: sell 10 more at 90
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("90"))
    manager._record_pnl(request, result)

    # No PnL recorded
    assert len(loss_guard.recorded_trades) == 0

    # New position: -20 shares with weighted avg (100+90)/2 = 95
    assert manager._position_state["NIFTY"] == (Decimal("-20"), Decimal("95"))


def test_order_manager_pnl_no_loss_guard():
    """Test PnL recording when no loss guard is configured."""
    executor = _MockExecutor()
    manager = OrderManager(executor, daily_loss_guard=None)

    # Open and close position
    manager._position_state["NIFTY"] = (Decimal("10"), Decimal("100"))
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("110"))

    # Should not raise error
    manager._record_pnl(request, result)


def test_order_manager_pnl_zero_filled_quantity():
    """Test PnL recording with zero filled quantity."""
    executor = _MockExecutor()
    loss_guard = _MockDailyLossGuard()
    manager = OrderManager(executor, daily_loss_guard=loss_guard)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("0"), Decimal("110"))

    manager._record_pnl(request, result)

    # No PnL recorded for zero quantity
    assert len(loss_guard.recorded_trades) == 0


def test_order_manager_dead_man_switch_no_heartbeat():
    """Test dead man switch when no heartbeat received."""
    executor = _MockExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    # No heartbeat received
    check_time = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

    # Should trigger cancel
    assert manager.check_dead_man_switch(check_time) is True
    assert executor.cancel_count == 1


def test_order_manager_dead_man_switch_naive_datetime():
    """Test dead man switch rejects naive datetime."""
    executor = _MockExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    with pytest.raises(ConfigError, match="now_utc must be timezone-aware UTC datetime"):
        manager.check_dead_man_switch(datetime(2024, 1, 1, 10, 0))  # noqa: DTZ001


def test_order_manager_audit_logging():
    """Test that order audit logging works."""
    executor = _MockExecutor()
    audit_logger = _MockTradeAuditLogger()
    manager = OrderManager(executor, audit_logger=audit_logger)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("100"))

    manager._audit(request, result, "STRAT-1", "ALG-101")

    assert len(audit_logger.logged_orders) == 1
    logged_request, logged_result, strategy_id, algo_id = audit_logger.logged_orders[0]
    assert logged_request == request
    assert logged_result == result
    assert strategy_id == "STRAT-1"
    assert algo_id == "ALG-101"


def test_order_manager_no_audit_logger():
    """Test that missing audit logger doesn't cause error."""
    executor = _MockExecutor()
    manager = OrderManager(executor, audit_logger=None)

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("10"), Decimal("100"))

    # Should not raise error
    manager._audit(request, result, "STRAT-1", "ALG-101")


def test_order_manager_full_pipeline():
    """Test full order placement pipeline."""
    executor = _MockExecutor()
    kill_switch = _MockKillSwitch(allowed=True)
    throttle = _MockOrderThrottle(allowed=True)
    loss_guard = _MockDailyLossGuard()
    audit_logger = _MockTradeAuditLogger()

    manager = OrderManager(
        executor,
        kill_switch=kill_switch,
        order_throttle=throttle,
        daily_loss_guard=loss_guard,
        audit_logger=audit_logger,
        algo_id="ALG-101",
    )

    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
    result = manager.place_order(request, strategy_id="STRAT-1")

    # Verify all gates passed
    assert result.status == OrderStatus.FILLED
    assert len(executor.executed_orders) == 1
    assert throttle.recorded_count == 1
    assert len(audit_logger.logged_orders) == 1


def test_order_manager_get_order_status_nonexistent():
    """Test getting status of non-existent order."""
    executor = _MockExecutor()
    manager = OrderManager(executor)

    status = manager.get_order_status("NONEXISTENT")
    assert status is None


def test_order_manager_multiple_order_status_tracking():
    """Test tracking multiple order statuses."""
    executor = _MockExecutor()
    manager = OrderManager(executor)

    # Place multiple orders
    for i in range(3):
        request = OrderRequest(Exchange.NSE, f"SYM{i}", OrderSide.BUY, Decimal("1"))
        result = manager.place_order(request)
        assert manager.get_order_status(result.order_id) == OrderStatus.FILLED
