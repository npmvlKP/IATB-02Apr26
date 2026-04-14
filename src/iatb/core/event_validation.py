"""
Runtime validation for core event objects.

All checks are fail-closed and raise ValidationError on first violation.
"""

from decimal import Decimal
from typing import Any

from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_timestamp

SUPPORTED_EVENT_TYPES = frozenset(
    {
        "MarketTickEvent",
        "OrderUpdateEvent",
        "SignalEvent",
        "RegimeChangeEvent",
        "ScanUpdateEvent",
        "PnLUpdateEvent",
    }
)

MAX_PRICE = Decimal("1000000000")
MAX_QUANTITY = Decimal("1000000000")
MIN_CONFIDENCE = Decimal("0")
MAX_CONFIDENCE = Decimal("1")
MAX_SYMBOL_LENGTH = 64
MAX_IDENTIFIER_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 512


def validate_event(event: object) -> None:
    """Validate a supported event instance."""
    event_type_name = type(event).__name__
    if event_type_name not in SUPPORTED_EVENT_TYPES:
        msg = f"Unsupported event type for runtime validation: {event_type_name}"
        raise ValidationError(msg)

    _validate_timestamp(event)

    if event_type_name == "MarketTickEvent":
        _validate_market_tick_event(event)
    elif event_type_name == "OrderUpdateEvent":
        _validate_order_update_event(event)
    elif event_type_name == "SignalEvent":
        _validate_signal_event(event)
    elif event_type_name == "ScanUpdateEvent":
        _validate_scan_update_event(event)
    elif event_type_name == "PnLUpdateEvent":
        _validate_pnl_update_event(event)
    else:
        _validate_regime_change_event(event)


def _validate_timestamp(event: object) -> None:
    """Validate event timestamp is strict UTC."""
    timestamp = _get_attr(event, "timestamp")
    if not hasattr(timestamp, "tzinfo"):
        msg = "Event timestamp must be a timezone-aware datetime in UTC"
        raise ValidationError(msg)
    try:
        create_timestamp(timestamp)
    except Exception as exc:
        msg = f"Invalid event timestamp: {exc}"
        raise ValidationError(msg) from exc


def _validate_exchange(event: object) -> None:
    """Validate event exchange domain."""
    exchange = _get_attr(event, "exchange")
    if not isinstance(exchange, Exchange):
        msg = f"Invalid exchange type: {type(exchange).__name__}"
        raise ValidationError(msg)


def _validate_order_side(event: object) -> None:
    """Validate event order side domain."""
    side = _get_attr(event, "side")
    if not isinstance(side, OrderSide):
        msg = f"Invalid order side type: {type(side).__name__}"
        raise ValidationError(msg)


def _validate_order_type(event: object) -> None:
    """Validate event order type domain."""
    order_type = _get_attr(event, "order_type")
    if not isinstance(order_type, OrderType):
        msg = f"Invalid order type: {type(order_type).__name__}"
        raise ValidationError(msg)


def _validate_market_tick_event(event: object) -> None:
    _validate_exchange(event)
    _validate_non_empty_text(_get_attr(event, "symbol"), "symbol", MAX_SYMBOL_LENGTH)
    price = _as_decimal(_get_attr(event, "price"), "price")
    quantity = _as_decimal(_get_attr(event, "quantity"), "quantity")
    volume = _as_decimal(_get_attr(event, "volume"), "volume")
    _validate_decimal_range(price, "price", Decimal("0"), MAX_PRICE)
    _validate_decimal_range(quantity, "quantity", Decimal("0"), MAX_QUANTITY)
    _validate_decimal_range(volume, "volume", Decimal("0"), MAX_QUANTITY)

    bid_price = _get_optional_attr(event, "bid_price")
    ask_price = _get_optional_attr(event, "ask_price")
    if bid_price is not None:
        _validate_decimal_range(
            _as_decimal(bid_price, "bid_price"),
            "bid_price",
            Decimal("0"),
            MAX_PRICE,
        )
    if ask_price is not None:
        _validate_decimal_range(
            _as_decimal(ask_price, "ask_price"),
            "ask_price",
            Decimal("0"),
            MAX_PRICE,
        )
    if bid_price is not None and ask_price is not None and bid_price > ask_price:
        msg = "bid_price cannot be greater than ask_price"
        raise ValidationError(msg)


def _validate_order_update_event(event: object) -> None:
    _validate_exchange(event)
    _validate_order_side(event)
    _validate_order_type(event)
    _validate_non_empty_text(_get_attr(event, "order_id"), "order_id", MAX_IDENTIFIER_LENGTH)
    _validate_non_empty_text(_get_attr(event, "symbol"), "symbol", MAX_SYMBOL_LENGTH)

    quantity = _as_decimal(_get_attr(event, "quantity"), "quantity")
    filled_quantity = _as_decimal(_get_attr(event, "filled_quantity"), "filled_quantity")
    _validate_decimal_range(quantity, "quantity", Decimal("0"), MAX_QUANTITY)
    _validate_decimal_range(filled_quantity, "filled_quantity", Decimal("0"), MAX_QUANTITY)
    if filled_quantity > quantity:
        msg = "filled_quantity cannot exceed quantity"
        raise ValidationError(msg)

    status = _get_attr(event, "status")
    if not isinstance(status, OrderStatus):
        msg = f"Invalid order status type: {type(status).__name__}"
        raise ValidationError(msg)
    if status == OrderStatus.FILLED and filled_quantity <= Decimal("0"):
        msg = "filled orders must have a positive filled_quantity"
        raise ValidationError(msg)

    for field_name in ("price", "avg_price"):
        value = _get_optional_attr(event, field_name)
        if value is None:
            continue
        _validate_decimal_range(
            _as_decimal(value, field_name),
            field_name,
            Decimal("0"),
            MAX_PRICE,
        )


def _validate_signal_event(event: object) -> None:
    _validate_exchange(event)
    _validate_order_side(event)
    _validate_non_empty_text(_get_attr(event, "strategy_id"), "strategy_id", MAX_IDENTIFIER_LENGTH)
    _validate_non_empty_text(_get_attr(event, "symbol"), "symbol", MAX_SYMBOL_LENGTH)
    quantity = _as_decimal(_get_attr(event, "quantity"), "quantity")
    _validate_decimal_range(quantity, "quantity", Decimal("0"), MAX_QUANTITY)

    confidence = _as_decimal(_get_attr(event, "confidence"), "confidence")
    _validate_decimal_range(confidence, "confidence", MIN_CONFIDENCE, MAX_CONFIDENCE)

    price = _get_optional_attr(event, "price")
    if price is not None:
        _validate_decimal_range(_as_decimal(price, "price"), "price", Decimal("0"), MAX_PRICE)


def _validate_scan_update_event(event: object) -> None:
    """Validate scan update events for SSE broadcasting."""
    total_candidates = _get_attr(event, "total_candidates")
    approved_candidates = _get_attr(event, "approved_candidates")
    trades_executed = _get_attr(event, "trades_executed")
    duration_ms = _get_attr(event, "duration_ms")
    errors = _get_attr(event, "errors")

    if not isinstance(total_candidates, int) or total_candidates < 0:
        msg = "total_candidates must be a non-negative integer"
        raise ValidationError(msg)

    if not isinstance(approved_candidates, int) or approved_candidates < 0:
        msg = "approved_candidates must be a non-negative integer"
        raise ValidationError(msg)

    if approved_candidates > total_candidates:
        msg = "approved_candidates cannot exceed total_candidates"
        raise ValidationError(msg)

    if not isinstance(trades_executed, int) or trades_executed < 0:
        msg = "trades_executed must be a non-negative integer"
        raise ValidationError(msg)

    if trades_executed > approved_candidates:
        msg = "trades_executed cannot exceed approved_candidates"
        raise ValidationError(msg)

    if not isinstance(duration_ms, int) or duration_ms < 0:
        msg = "duration_ms must be a non-negative integer"
        raise ValidationError(msg)

    if not isinstance(errors, list):
        msg = "errors must be a list of strings"
        raise ValidationError(msg)
    for error in errors:
        if not isinstance(error, str):
            msg = "errors must contain only strings"
            raise ValidationError(msg)


def _validate_pnl_update_event(event: object) -> None:
    """Validate PnL update events for SSE broadcasting."""
    _validate_non_empty_text(_get_attr(event, "order_id"), "order_id", MAX_IDENTIFIER_LENGTH)
    _validate_non_empty_text(_get_attr(event, "symbol"), "symbol", MAX_SYMBOL_LENGTH)
    _validate_non_empty_text(_get_attr(event, "side"), "side", 16)

    quantity = _as_decimal(_get_attr(event, "quantity"), "quantity")
    price = _as_decimal(_get_attr(event, "price"), "price")
    trade_pnl = _as_decimal(_get_attr(event, "trade_pnl"), "trade_pnl")
    cumulative_pnl = _as_decimal(_get_attr(event, "cumulative_pnl"), "cumulative_pnl")

    _validate_decimal_range(quantity, "quantity", Decimal("0"), MAX_QUANTITY)
    _validate_decimal_range(price, "price", Decimal("0"), MAX_PRICE)
    _validate_decimal_range(trade_pnl, "trade_pnl", Decimal("-1000000000"), MAX_PRICE)
    _validate_decimal_range(
        cumulative_pnl,
        "cumulative_pnl",
        Decimal("-1000000000"),
        Decimal("1000000000"),
    )


def _validate_regime_change_event(event: object) -> None:
    _validate_non_empty_text(_get_attr(event, "regime_type"), "regime_type", MAX_IDENTIFIER_LENGTH)
    _validate_non_empty_text(
        _get_attr(event, "description"),
        "description",
        MAX_DESCRIPTION_LENGTH,
    )
    confidence = _as_decimal(_get_attr(event, "confidence"), "confidence")
    _validate_decimal_range(confidence, "confidence", MIN_CONFIDENCE, MAX_CONFIDENCE)

    metadata = _get_attr(event, "metadata")
    if not isinstance(metadata, dict):
        msg = "metadata must be a dictionary[str, str]"
        raise ValidationError(msg)
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            msg = "metadata keys and values must be strings"
            raise ValidationError(msg)


def _as_decimal(value: object, field_name: str) -> Decimal:
    """Ensure value is Decimal for strict financial safety."""
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be Decimal-compatible, got {type(value).__name__}"
        raise ValidationError(msg)
    return value


def _validate_decimal_range(
    value: Decimal,
    field_name: str,
    lower: Decimal,
    upper: Decimal,
) -> None:
    """Validate a decimal is within inclusive domain bounds."""
    if value < lower or value > upper:
        msg = f"{field_name}={value} outside allowed range [{lower}, {upper}]"
        raise ValidationError(msg)


def _validate_non_empty_text(value: object, field_name: str, max_length: int) -> None:
    """Validate text domain constraints."""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ValidationError(msg)
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} cannot be empty"
        raise ValidationError(msg)
    if len(normalized) > max_length:
        msg = f"{field_name} exceeds max length: {max_length}"
        raise ValidationError(msg)


def _get_attr(event: object, attr_name: str) -> Any:
    """Read a required event attribute, fail-closed when missing."""
    if not hasattr(event, attr_name):
        msg = f"Event missing required attribute: {attr_name}"
        raise ValidationError(msg)
    return getattr(event, attr_name)


def _get_optional_attr(event: object, attr_name: str) -> Any | None:
    """Read an optional event attribute."""
    if not hasattr(event, attr_name):
        return None
    return getattr(event, attr_name)
