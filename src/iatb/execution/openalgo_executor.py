"""
OpenAlgo live executor adapter.
"""

import os
from collections.abc import Callable, Mapping
from decimal import Decimal

from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest

_LIVE_GATE_ENV = "LIVE_TRADING_ENABLED"


class OpenAlgoExecutor(Executor):
    """Executes live orders via injected OpenAlgo API callables."""

    def __init__(
        self,
        place_order: Callable[[Mapping[str, str]], Mapping[str, object]],
        cancel_all_orders: Callable[[], int],
    ) -> None:
        self._place_order = place_order
        self._cancel_all_orders = cancel_all_orders

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        _assert_live_enabled()
        payload = _request_payload(request)
        response = self._place_order(payload)
        return _parse_response(response)

    def cancel_all(self) -> int:
        _assert_live_enabled()
        return int(self._cancel_all_orders())


def _assert_live_enabled() -> None:
    if os.getenv(_LIVE_GATE_ENV, "").strip().lower() != "true":
        msg = "live execution blocked: set LIVE_TRADING_ENABLED=true to proceed"
        raise ConfigError(msg)


def _request_payload(request: OrderRequest) -> dict[str, str]:
    payload = {
        "exchange": request.exchange.value,
        "symbol": request.symbol,
        "side": request.side.value,
        "quantity": str(request.quantity),
        "order_type": request.order_type.value,
    }
    if request.price is not None:
        payload["price"] = str(request.price)
    payload.update(request.metadata)
    return payload


def _parse_response(response: Mapping[str, object]) -> ExecutionResult:
    order_id = str(response.get("order_id", "")).strip()
    if not order_id:
        msg = "openalgo response missing order_id"
        raise ConfigError(msg)
    status_raw = str(response.get("status", "PENDING")).upper()
    status = _parse_status(status_raw)
    filled = Decimal(str(response.get("filled_quantity", "0")))
    avg_price = Decimal(str(response.get("average_price", "0")))
    message = str(response.get("message", ""))
    return ExecutionResult(order_id, status, filled, avg_price, message)


def _parse_status(value: str) -> OrderStatus:
    try:
        return OrderStatus(value)
    except ValueError:
        return OrderStatus.PENDING
