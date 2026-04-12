import random
from datetime import UTC, datetime, timedelta
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


class _StubExecutor(Executor):
    def __init__(self) -> None:
        self.cancel_count = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        _ = request
        return ExecutionResult("OID-1", OrderStatus.OPEN, Decimal("0"), Decimal("0"))

    def cancel_all(self) -> int:
        self.cancel_count += 1
        return 1


def test_order_manager_tracks_status_and_triggers_dead_man_switch() -> None:
    executor = _StubExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    result = manager.place_order(request)
    assert manager.get_order_status(result.order_id) == OrderStatus.OPEN
    manager.receive_heartbeat(datetime(2026, 1, 5, 4, 0, tzinfo=UTC))
    stale_now = datetime(2026, 1, 5, 4, 1, tzinfo=UTC)
    assert manager.check_dead_man_switch(stale_now)
    assert executor.cancel_count == 1
    assert manager.get_order_status(result.order_id) == OrderStatus.CANCELLED


def test_order_manager_validations() -> None:
    manager = OrderManager(_StubExecutor(), heartbeat_timeout_seconds=1)
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        manager.receive_heartbeat(datetime(2026, 1, 5, 4, 0))  # noqa: DTZ001
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        manager.check_dead_man_switch(datetime(2026, 1, 5, 4, 0))  # noqa: DTZ001
    manager.receive_heartbeat(datetime(2026, 1, 5, 4, 0, tzinfo=UTC))
    fresh_now = datetime(2026, 1, 5, 4, 0, tzinfo=UTC) + timedelta(milliseconds=500)
    assert not manager.check_dead_man_switch(fresh_now)


def test_order_manager_multiple_orders() -> None:
    """Test tracking multiple orders."""
    executor = _StubExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    request1 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    result1 = manager.place_order(request1)

    request2 = OrderRequest(Exchange.NSE, "BANKNIFTY", OrderSide.SELL, Decimal("2"))
    result2 = manager.place_order(request2)

    assert manager.get_order_status(result1.order_id) == OrderStatus.OPEN
    assert manager.get_order_status(result2.order_id) == OrderStatus.OPEN


def test_order_manager_dead_man_switch_cancels_all() -> None:
    """Test that dead man switch cancels all open orders."""
    executor = _StubExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    # Place multiple orders
    for i in range(3):
        request = OrderRequest(Exchange.NSE, f"SYM{i}", OrderSide.BUY, Decimal("1"))
        manager.place_order(request)

    # Receive heartbeat
    manager.receive_heartbeat(datetime(2026, 1, 5, 4, 0, tzinfo=UTC))

    # Trigger dead man switch
    stale_time = datetime(2026, 1, 5, 4, 1, tzinfo=UTC)
    assert manager.check_dead_man_switch(stale_time)

    # All orders should be cancelled
    assert executor.cancel_count == 1


def test_order_manager_heartbeat_updates_timestamp() -> None:
    """Test that heartbeat updates the last heartbeat timestamp."""
    executor = _StubExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    heartbeat_time = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    manager.receive_heartbeat(heartbeat_time)

    # Check immediately after heartbeat
    assert not manager.check_dead_man_switch(heartbeat_time + timedelta(seconds=1))

    # Check after timeout
    assert manager.check_dead_man_switch(heartbeat_time + timedelta(seconds=31))


def test_order_manager_no_heartbeat_triggers_switch() -> None:
    """Test that missing heartbeat triggers dead man switch."""
    executor = _StubExecutor()
    manager = OrderManager(executor, heartbeat_timeout_seconds=30)

    # Don't send heartbeat, just check
    check_time = datetime(2026, 1, 5, 4, 1, tzinfo=UTC)

    # Should trigger since no heartbeat received
    assert manager.check_dead_man_switch(check_time)
