"""
Tests for runtime event validation layer.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderType
from iatb.core.event_validation import validate_event
from iatb.core.exceptions import ValidationError


def _event_stub(event_type_name: str, **attrs: object) -> object:
    """Create a lightweight dynamic object for branch testing."""
    event_type = type(event_type_name, (), {})
    instance = event_type()
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


def test_unsupported_event_type_rejected() -> None:
    """Unknown event type should fail closed."""
    with pytest.raises(ValidationError, match="Unsupported event type"):
        validate_event(_event_stub("UnknownEvent", timestamp=datetime.now(UTC)))


def test_missing_required_attribute_rejected() -> None:
    """Missing required fields should fail closed."""
    event = _event_stub("MarketTickEvent", timestamp=datetime.now(UTC))
    with pytest.raises(ValidationError, match="Event missing required attribute"):
        validate_event(event)


def test_invalid_exchange_type_rejected() -> None:
    """Exchange must be Exchange enum."""
    event = _event_stub(
        "MarketTickEvent",
        timestamp=datetime.now(UTC),
        exchange="NSE",
        symbol="RELIANCE",
        price=Decimal("100"),
        quantity=Decimal("1"),
        volume=Decimal("1"),
        bid_price=None,
        ask_price=None,
    )
    with pytest.raises(ValidationError, match="Invalid exchange type"):
        validate_event(event)


def test_invalid_order_status_type_rejected() -> None:
    """Order status must use OrderStatus enum."""
    event = _event_stub(
        "OrderUpdateEvent",
        timestamp=datetime.now(UTC),
        order_id="ORD-1",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        filled_quantity=Decimal("5"),
        price=Decimal("100"),
        avg_price=Decimal("100"),
        status="FILLED",
    )
    with pytest.raises(ValidationError, match="Invalid order status type"):
        validate_event(event)


def test_regime_metadata_type_rejected() -> None:
    """Metadata must be dictionary[str, str]."""
    event = _event_stub(
        "RegimeChangeEvent",
        timestamp=datetime.now(UTC),
        regime_type="VOLATILITY_SPIKE",
        description="Volatility increasing",
        confidence=Decimal("0.7"),
        metadata=["not-a-dict"],
    )
    with pytest.raises(ValidationError, match="metadata must be a dictionary"):
        validate_event(event)


def test_signal_optional_price_type_rejected() -> None:
    """Signal optional price must be Decimal-compatible."""
    event = _event_stub(
        "SignalEvent",
        timestamp=datetime.now(UTC),
        strategy_id="S1",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal("5"),
        price="100.5",
        confidence=Decimal("0.5"),
    )
    with pytest.raises(ValidationError, match="price must be Decimal-compatible"):
        validate_event(event)


def test_invalid_order_side_type_rejected() -> None:
    """Signal side must use OrderSide enum."""
    event = _event_stub(
        "SignalEvent",
        timestamp=datetime.now(UTC),
        strategy_id="S1",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side="BUY",
        quantity=Decimal("5"),
        price=Decimal("100.5"),
        confidence=Decimal("0.5"),
    )
    with pytest.raises(ValidationError, match="Invalid order side type"):
        validate_event(event)


def test_invalid_order_type_rejected() -> None:
    """Order update order_type must use OrderType enum."""
    event = _event_stub(
        "OrderUpdateEvent",
        timestamp=datetime.now(UTC),
        order_id="ORD-1",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("10"),
        filled_quantity=Decimal("5"),
        price=Decimal("100"),
        avg_price=Decimal("100"),
        status=Decimal("1"),
    )
    with pytest.raises(ValidationError, match="Invalid order type"):
        validate_event(event)


def test_malformed_timestamp_object_rejected() -> None:
    """Malformed timestamp objects should fail as ValidationError."""

    class MalformedTimestamp:
        tzinfo = UTC

    event = _event_stub(
        "MarketTickEvent",
        timestamp=MalformedTimestamp(),
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        price=Decimal("100"),
        quantity=Decimal("1"),
        volume=Decimal("1"),
        bid_price=None,
        ask_price=None,
    )
    with pytest.raises(ValidationError, match="Invalid event timestamp"):
        validate_event(event)
