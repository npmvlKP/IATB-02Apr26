"""
CCXT live executor adapter.
"""

import os
from collections.abc import Callable, Mapping
from decimal import Decimal

from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest

_LIVE_GATE_ENV = "LIVE_TRADING_ENABLED"
_OAUTH_2FA_GATE_ENV = "BROKER_OAUTH_2FA_VERIFIED"


class CCXTExecutor(Executor):
    """Executes live crypto orders via injected CCXT adapter callables."""

    def __init__(
        self,
        create_order: Callable[[Mapping[str, str]], Mapping[str, object]],
        cancel_all_orders: Callable[[], int],
    ) -> None:
        self._create_order = create_order
        self._cancel_all_orders = cancel_all_orders

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        _assert_live_enabled()
        payload = _request_payload(request)
        response = self._create_order(payload)
        return _parse_response(response)

    def cancel_all(self) -> int:
        _assert_live_enabled()
        return int(self._cancel_all_orders())

    def close_order(self, order_id: str) -> bool:
        """Close a specific order by ID.

        Args:
            order_id: The order ID to close.

        Returns:
            True if order was found and closed, False otherwise.

        Note:
            CCXT order cancellation is handled via cancel_all in this implementation.
            Individual order cancellation requires additional CCXT API integration.
        """
        _assert_live_enabled()
        # For now, CCXT executor only supports cancel_all
        # Individual order cancellation would require cancel_order callable
        return False


def _assert_live_enabled() -> None:
    if os.getenv(_LIVE_GATE_ENV, "").strip().lower() != "true":
        msg = "live execution blocked: set LIVE_TRADING_ENABLED=true to proceed"
        raise ConfigError(msg)
    if os.getenv(_OAUTH_2FA_GATE_ENV, "").strip().lower() != "true":
        msg = "broker access blocked: set BROKER_OAUTH_2FA_VERIFIED=true after OAuth 2FA"
        raise ConfigError(msg)


def _request_payload(request: OrderRequest) -> dict[str, str]:
    _require_algo_id(request.metadata)
    payload = {
        "exchange": request.exchange.value,
        "symbol": request.symbol,
        "side": request.side.value.lower(),
        "type": request.order_type.value.lower(),
        "amount": str(request.quantity),
    }
    if request.price is not None:
        payload["price"] = str(request.price)
    payload.update(request.metadata)
    return payload


def _require_algo_id(metadata: Mapping[str, str]) -> None:
    algo_id = metadata.get("algo_id", "").strip()
    if not algo_id:
        msg = "live execution blocked: algo_id metadata is required for SEBI compliance"
        raise ConfigError(msg)


def _parse_response(response: Mapping[str, object]) -> ExecutionResult:
    order_id = str(response.get("id", "")).strip()
    if not order_id:
        msg = "ccxt response missing id"
        raise ConfigError(msg)
    status_raw = str(response.get("status", "open")).upper()
    status = _status_from_ccxt(status_raw)
    filled = Decimal(str(response.get("filled", "0")))
    avg_price = Decimal(str(response.get("average", response.get("price", "0"))))
    return ExecutionResult(order_id, status, filled, avg_price, "ccxt fill")


def _status_from_ccxt(value: str) -> OrderStatus:
    mapping = {
        "OPEN": OrderStatus.OPEN,
        "CLOSED": OrderStatus.FILLED,
        "CANCELED": OrderStatus.CANCELLED,
        "REJECTED": OrderStatus.REJECTED,
    }
    return mapping.get(value, OrderStatus.PENDING)
