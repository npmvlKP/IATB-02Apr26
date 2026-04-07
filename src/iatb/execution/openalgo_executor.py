"""
OpenAlgo live executor adapter with Zerodha-specific integration.

Reference: marketcalls/openalgo (AGPL-3.0) - proven Zerodha broker adapter.
"""

import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest

_LIVE_GATE_ENV = "LIVE_TRADING_ENABLED"
_OAUTH_2FA_GATE_ENV = "BROKER_OAUTH_2FA_VERIFIED"
_ZERODHA_API_KEY_ENV = "ZERODHA_API_KEY"
_ZERODHA_API_SECRET_ENV = "ZERODHA_API_SECRET"  # noqa: S105  # nosec B105

_LOGGER = logging.getLogger(__name__)


class OpenAlgoExecutor(Executor):
    """Executes live orders via injected OpenAlgo API callables.

    Supports Zerodha broker integration via OpenAlgo adapter.
    """

    def __init__(
        self,
        place_order: Callable[[Mapping[str, str]], Mapping[str, object]],
        cancel_all_orders: Callable[[], int],
        *,
        broker: str = "zerodha",
    ) -> None:
        self._place_order = place_order
        self._cancel_all_orders = cancel_all_orders
        self._broker = broker.lower().strip()
        _validate_broker(self._broker)
        _LOGGER.info(
            "OpenAlgoExecutor initialized",
            extra={"broker": self._broker, "timestamp_utc": datetime.now(UTC).isoformat()},
        )

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        _assert_live_enabled()
        _assert_zerodha_credentials(self._broker)
        payload = _request_payload(request, broker=self._broker)
        _LOGGER.info(
            "Executing order via OpenAlgo",
            extra={
                "broker": self._broker,
                "symbol": request.symbol,
                "side": request.side.value,
                "quantity": str(request.quantity),
                "timestamp_utc": datetime.now(UTC).isoformat(),
            },
        )
        response = self._place_order(payload)
        result = _parse_response(response)
        _LOGGER.info(
            "Order execution completed",
            extra={
                "order_id": result.order_id,
                "status": result.status.value,
                "filled_quantity": str(result.filled_quantity),
                "timestamp_utc": datetime.now(UTC).isoformat(),
            },
        )
        return result

    def cancel_all(self) -> int:
        _assert_live_enabled()
        _assert_zerodha_credentials(self._broker)
        cancelled_count = int(self._cancel_all_orders())
        _LOGGER.info(
            "Cancelled all orders",
            extra={
                "cancelled_count": cancelled_count,
                "timestamp_utc": datetime.now(UTC).isoformat(),
            },
        )
        return cancelled_count

    @property
    def broker(self) -> str:
        """Return configured broker identifier."""
        return self._broker


_SUPPORTED_BROKERS = frozenset({"zerodha", "angelone", "upstox", "icici"})


def _validate_broker(broker: str) -> None:
    """Validate broker is supported by OpenAlgo integration."""
    if broker not in _SUPPORTED_BROKERS:
        msg = f"unsupported broker '{broker}'; supported: {', '.join(sorted(_SUPPORTED_BROKERS))}"
        raise ConfigError(msg)


def _assert_live_enabled() -> None:
    """Assert live trading and OAuth 2FA gates are enabled."""
    if os.getenv(_LIVE_GATE_ENV, "").strip().lower() != "true":
        msg = "live execution blocked: set LIVE_TRADING_ENABLED=true to proceed"
        raise ConfigError(msg)
    if os.getenv(_OAUTH_2FA_GATE_ENV, "").strip().lower() != "true":
        msg = "broker access blocked: set BROKER_OAUTH_2FA_VERIFIED=true after OAuth 2FA"
        raise ConfigError(msg)


def _assert_zerodha_credentials(broker: str) -> None:
    """Assert Zerodha API credentials are configured when broker is zerodha."""
    if broker != "zerodha":
        return
    api_key = os.getenv(_ZERODHA_API_KEY_ENV, "").strip()
    api_secret = os.getenv(_ZERODHA_API_SECRET_ENV, "").strip()
    if not api_key:
        msg = f"Zerodha API key missing: set {_ZERODHA_API_KEY_ENV} in environment"
        raise ConfigError(msg)
    if not api_secret:
        msg = f"Zerodha API secret missing: set {_ZERODHA_API_SECRET_ENV} in environment"
        raise ConfigError(msg)


def _request_payload(request: OrderRequest, broker: str = "zerodha") -> dict[str, str]:
    """Build OpenAlgo order payload with broker-specific fields."""
    _require_algo_id(request.metadata)
    payload = {
        "broker": broker,
        "exchange": request.exchange.value,
        "symbol": request.symbol,
        "side": request.side.value,
        "quantity": str(request.quantity),
        "order_type": request.order_type.value,
        "product": request.metadata.get("product", "MIS"),
        "validity": request.metadata.get("validity", "DAY"),
    }
    if request.price is not None:
        payload["price"] = str(request.price)
    payload.update(request.metadata)
    payload["algo_id"] = request.metadata["algo_id"]
    return payload


def _require_algo_id(metadata: Mapping[str, str]) -> None:
    """Require non-empty algo_id for SEBI compliance."""
    algo_id = metadata.get("algo_id", "").strip()
    if not algo_id:
        msg = "live execution blocked: algo_id metadata is required for SEBI compliance"
        raise ConfigError(msg)


def _parse_response(response: Mapping[str, object]) -> ExecutionResult:
    """Parse OpenAlgo API response into ExecutionResult with Decimal precision."""
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
    """Parse order status string into OrderStatus enum."""
    try:
        return OrderStatus(value)
    except ValueError:
        return OrderStatus.PENDING
