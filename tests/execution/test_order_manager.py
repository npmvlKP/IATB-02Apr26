from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager


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
