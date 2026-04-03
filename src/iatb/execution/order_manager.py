"""
Order lifecycle manager with dead-man switch protections.
"""

from datetime import UTC, datetime, timedelta

from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest


class OrderManager:
    """Tracks order lifecycle and triggers cancel-all on heartbeat loss."""

    def __init__(self, executor: Executor, heartbeat_timeout_seconds: int = 30) -> None:
        if heartbeat_timeout_seconds <= 0:
            msg = "heartbeat_timeout_seconds must be positive"
            raise ConfigError(msg)
        self._executor = executor
        self._heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)
        self._last_heartbeat_utc: datetime | None = None
        self._order_status: dict[str, OrderStatus] = {}

    def receive_heartbeat(self, heartbeat_utc: datetime) -> None:
        if heartbeat_utc.tzinfo != UTC:
            msg = "heartbeat_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        self._last_heartbeat_utc = heartbeat_utc

    def place_order(self, request: OrderRequest) -> ExecutionResult:
        result = self._executor.execute_order(request)
        self._order_status[result.order_id] = result.status
        return result

    def check_dead_man_switch(self, now_utc: datetime) -> bool:
        if now_utc.tzinfo != UTC:
            msg = "now_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        if self._last_heartbeat_utc is None:
            return self._trigger_cancel_all()
        stale = now_utc - self._last_heartbeat_utc > self._heartbeat_timeout
        return self._trigger_cancel_all() if stale else False

    def get_order_status(self, order_id: str) -> OrderStatus | None:
        return self._order_status.get(order_id)

    def _trigger_cancel_all(self) -> bool:
        cancelled_count = self._executor.cancel_all()
        if cancelled_count > 0:
            for key in self._order_status:
                if self._order_status[key] in {OrderStatus.OPEN, OrderStatus.PENDING}:
                    self._order_status[key] = OrderStatus.CANCELLED
        return True
