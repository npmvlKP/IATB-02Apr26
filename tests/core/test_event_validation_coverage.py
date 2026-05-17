"""
Comprehensive tests for event_validation.py to achieve 100% coverage.

Tests all public functions, edge cases, and error paths as per TIER 2 requirements.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.event_validation import (
    _as_decimal,
    _get_attr,
    _get_optional_attr,
    _validate_decimal_range,
    _validate_exchange,
    _validate_market_tick_event,
    _validate_non_empty_text,
    _validate_order_side,
    _validate_order_type,
    _validate_order_update_event,
    _validate_pnl_update_event,
    _validate_regime_change_event,
    _validate_scan_update_event,
    _validate_signal_event,
    _validate_timestamp,
    validate_event,
)
from iatb.core.exceptions import ValidationError

# =============================================================================
# Helper: Dynamic Event Stub for Testing
# =============================================================================


def _event_stub(event_type_name: str, **attrs: object) -> object:
    """Create a lightweight dynamic object for branch testing."""
    event_type = type(event_type_name, (), {})
    instance = event_type()
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


# =============================================================================
# Fixtures for Valid Event Objects
# =============================================================================


@pytest.fixture()
def valid_timestamp() -> datetime:
    """UTC-aware timestamp for valid event creation."""
    return datetime(2024, 1, 1, 9, 30, 0, tzinfo=UTC)


@pytest.fixture()
def valid_market_tick_event(valid_timestamp) -> object:
    """Valid MarketTickEvent with all required fields."""
    return _event_stub(
        "MarketTickEvent",
        timestamp=valid_timestamp,
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        price=Decimal("100.50"),
        quantity=Decimal("100"),
        volume=Decimal("5000"),
        bid_price=Decimal("100.40"),
        ask_price=Decimal("100.60"),
    )


@pytest.fixture()
def valid_order_update_event(valid_timestamp) -> object:
    """Valid OrderUpdateEvent with FILLED status."""
    return _event_stub(
        "OrderUpdateEvent",
        timestamp=valid_timestamp,
        order_id="ORD-12345",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("100"),
        price=Decimal("100.50"),
        filled_quantity=Decimal("50"),
        avg_price=Decimal("100.60"),
        status=OrderStatus.FILLED,
    )


@pytest.fixture()
def valid_signal_event(valid_timestamp) -> object:
    """Valid SignalEvent with optional price."""
    return _event_stub(
        "SignalEvent",
        timestamp=valid_timestamp,
        strategy_id="STRATEGY-001",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=Decimal("100.50"),
        confidence=Decimal("0.75"),
    )


@pytest.fixture()
def valid_scan_update_event(valid_timestamp) -> object:
    """Valid ScanUpdateEvent with zero errors list."""
    return _event_stub(
        "ScanUpdateEvent",
        timestamp=valid_timestamp,
        total_candidates=100,
        approved_candidates=80,
        trades_executed=50,
        duration_ms=1000,
        errors=[],
    )


@pytest.fixture()
def valid_pnl_update_event(valid_timestamp) -> object:
    """Valid PnLUpdateEvent with negative trade_pnl."""
    return _event_stub(
        "PnLUpdateEvent",
        timestamp=valid_timestamp,
        order_id="ORD-12345",
        symbol="RELIANCE",
        side="BUY",
        quantity=Decimal("100"),
        price=Decimal("100.50"),
        trade_pnl=Decimal("-50.00"),
        cumulative_pnl=Decimal("1000.00"),
    )


@pytest.fixture()
def valid_regime_change_event(valid_timestamp) -> object:
    """Valid RegimeChangeEvent with metadata."""
    return _event_stub(
        "RegimeChangeEvent",
        timestamp=valid_timestamp,
        regime_type="VOLATILITY_SPIKE",
        description="Volatility increasing",
        confidence=Decimal("0.85"),
        metadata={"key1": "value1", "key2": "value2"},
    )


# =============================================================================
# TEST: validate_event() - All 6 event type dispatches + unsupported type
# =============================================================================


class TestValidateEvent:
    """Tests for validate_event() public entry point."""

    def test_validate_market_tick_event_success(self, valid_market_tick_event) -> None:
        """Scenario 1: Valid MarketTickEvent with all fields including optional bid/ask."""
        validate_event(valid_market_tick_event)

    def test_validate_order_update_event_success(
        self, valid_order_update_event
    ) -> None:
        """Scenario 2: Valid OrderUpdateEvent with FILLED status and positive filled_quantity."""
        validate_event(valid_order_update_event)

    def test_validate_signal_event_success(self, valid_signal_event) -> None:
        """Scenario 3: Valid SignalEvent with optional price."""
        validate_event(valid_signal_event)

    def test_validate_scan_update_event_success(self, valid_scan_update_event) -> None:
        """Scenario 4: Valid ScanUpdateEvent with zero errors list."""
        validate_event(valid_scan_update_event)

    def test_validate_pnl_update_event_success(self, valid_pnl_update_event) -> None:
        """Scenario 5: Valid PnLUpdateEvent with negative trade_pnl."""
        validate_event(valid_pnl_update_event)

    def test_validate_regime_change_event_success(
        self, valid_regime_change_event
    ) -> None:
        """Scenario 6: Valid RegimeChangeEvent with metadata."""
        validate_event(valid_regime_change_event)

    def test_unsupported_event_type_raises_validation_error(self) -> None:
        """Scenario 7: Unsupported event type name -> ValidationError."""
        event = _event_stub("UnknownEvent", timestamp=datetime.now(UTC))
        with pytest.raises(ValidationError, match="Unsupported event type"):
            validate_event(event)


# =============================================================================
# TEST: _validate_timestamp() - UTC-aware pass, naive fail
# =============================================================================


class TestValidateTimestamp:
    """Tests for _validate_timestamp()."""

    def test_utc_aware_timestamp_passes(self, valid_timestamp) -> None:
        """UTC-aware timestamp should pass validation."""
        event = _event_stub("MarketTickEvent", timestamp=valid_timestamp)
        _validate_timestamp(event)

    def test_naive_timestamp_raises_validation_error(self) -> None:
        """Scenario 9: Timestamp without tzinfo -> ValidationError."""
        # Intentional naive datetime for validation test
        naive_dt = datetime(2024, 1, 1, 9, 30, 0)  # noqa: DTZ001
        event = _event_stub("MarketTickEvent", timestamp=naive_dt)
        with pytest.raises(ValidationError, match="Timestamp must be timezone-aware"):
            _validate_timestamp(event)

    def test_missing_timestamp_raises_validation_error(self) -> None:
        """Missing timestamp attribute should raise ValidationError."""
        event = _event_stub("MarketTickEvent")
        with pytest.raises(ValidationError, match="missing required attribute"):
            _validate_timestamp(event)


# =============================================================================
# TEST: _validate_exchange() - Valid Exchange enum pass, invalid fail
# =============================================================================


class TestValidateExchange:
    """Tests for _validate_exchange()."""

    def test_valid_exchange_enum_passes(self) -> None:
        """Valid Exchange enum should pass."""
        event = _event_stub("MarketTickEvent", exchange=Exchange.NSE)
        _validate_exchange(event)

    def test_invalid_exchange_type_raises_validation_error(self) -> None:
        """Scenario 18: Invalid exchange type -> ValidationError."""
        event = _event_stub("MarketTickEvent", exchange="NSE")
        with pytest.raises(ValidationError, match="Invalid exchange type"):
            _validate_exchange(event)


# =============================================================================
# TEST: _validate_order_side() - Valid/invalid OrderSide
# =============================================================================


class TestValidateOrderSide:
    """Tests for _validate_order_side()."""

    def test_valid_order_side_passes(self) -> None:
        """Valid OrderSide enum should pass."""
        event = _event_stub("SignalEvent", side=OrderSide.BUY)
        _validate_order_side(event)

    def test_invalid_order_side_raises_validation_error(self) -> None:
        """Invalid OrderSide type -> ValidationError."""
        event = _event_stub("SignalEvent", side="BUY")
        with pytest.raises(ValidationError, match="Invalid order side type"):
            _validate_order_side(event)


# =============================================================================
# TEST: _validate_order_type() - Valid/invalid OrderType
# =============================================================================


class TestValidateOrderType:
    """Tests for _validate_order_type()."""

    def test_valid_order_type_passes(self) -> None:
        """Valid OrderType enum should pass."""
        event = _event_stub("OrderUpdateEvent", order_type=OrderType.MARKET)
        _validate_order_type(event)

    def test_invalid_order_type_raises_validation_error(self) -> None:
        """Invalid OrderType should raise ValidationError."""
        event = _event_stub("OrderUpdateEvent", order_type="MARKET")
        with pytest.raises(ValidationError, match="Invalid order type"):
            _validate_order_type(event)


# =============================================================================
# TEST: _validate_market_tick_event() - Full validation
# =============================================================================


class TestValidateMarketTickEvent:
    """Tests for _validate_market_tick_event()."""

    def test_valid_market_tick_event_passes(self, valid_market_tick_event) -> None:
        """Valid MarketTickEvent should pass all validations."""
        _validate_market_tick_event(valid_market_tick_event)

    def test_bid_greater_than_ask_raises_validation_error(self) -> None:
        """Scenario 10: bid_price > ask_price -> ValidationError."""
        event = _event_stub(
            "MarketTickEvent",
            timestamp=datetime.now(UTC),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            price=Decimal("100"),
            quantity=Decimal("1"),
            volume=Decimal("1"),
            bid_price=Decimal("101"),
            ask_price=Decimal("100"),
        )
        with pytest.raises(
            ValidationError, match="bid_price cannot be greater than ask_price"
        ):
            _validate_market_tick_event(event)

    def test_non_decimal_price_raises_validation_error(self) -> None:
        """Scenario 17: Non-Decimal price -> ValidationError."""
        event = _event_stub(
            "MarketTickEvent",
            timestamp=datetime.now(UTC),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            price=100.50,  # float instead of Decimal
            quantity=Decimal("1"),
            volume=Decimal("1"),
            bid_price=None,
            ask_price=None,
        )
        with pytest.raises(ValidationError, match="price must be Decimal-compatible"):
            _validate_market_tick_event(event)

    def test_empty_symbol_raises_validation_error(self) -> None:
        """Scenario 14: Empty symbol string -> ValidationError."""
        event = _event_stub(
            "MarketTickEvent",
            timestamp=datetime.now(UTC),
            exchange=Exchange.NSE,
            symbol="",
            price=Decimal("100"),
            quantity=Decimal("1"),
            volume=Decimal("1"),
            bid_price=None,
            ask_price=None,
        )
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            _validate_market_tick_event(event)


# =============================================================================
# TEST: _validate_order_update_event() - Status-specific validations
# =============================================================================


class TestValidateOrderUpdateEvent:
    """Tests for _validate_order_update_event()."""

    def test_valid_order_update_event_passes(self, valid_order_update_event) -> None:
        """Valid OrderUpdateEvent should pass all validations."""
        _validate_order_update_event(valid_order_update_event)

    def test_filled_with_zero_filled_quantity_raises_validation_error(self) -> None:
        """Scenario 12: FILLED status with zero filled_quantity -> ValidationError."""
        event = _event_stub(
            "OrderUpdateEvent",
            timestamp=datetime.now(UTC),
            order_id="ORD-1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
            filled_quantity=Decimal("0"),
            price=None,
            avg_price=None,
            status=OrderStatus.FILLED,
        )
        with pytest.raises(
            ValidationError,
            match="filled orders must have a positive filled_quantity",
        ):
            _validate_order_update_event(event)

    def test_filled_quantity_exceeds_quantity_raises_validation_error(self) -> None:
        """Scenario 11: filled_quantity > quantity -> ValidationError."""
        event = _event_stub(
            "OrderUpdateEvent",
            timestamp=datetime.now(UTC),
            order_id="ORD-1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
            filled_quantity=Decimal("15"),
            price=None,
            avg_price=None,
            status=OrderStatus.PARTIALLY_FILLED,
        )
        with pytest.raises(
            ValidationError, match="filled_quantity cannot exceed quantity"
        ):
            _validate_order_update_event(event)

    def test_missing_required_attribute_raises_validation_error(self) -> None:
        """Scenario 8: Missing required attribute -> ValidationError."""
        event = _event_stub("OrderUpdateEvent", timestamp=datetime.now(UTC))
        with pytest.raises(ValidationError, match="missing required attribute"):
            _validate_order_update_event(event)


# =============================================================================
# TEST: _validate_signal_event() - Confidence bounds, optional price
# =============================================================================


class TestValidateSignalEvent:
    """Tests for _validate_signal_event()."""

    def test_valid_signal_event_passes(self, valid_signal_event) -> None:
        """Valid SignalEvent should pass all validations."""
        _validate_signal_event(valid_signal_event)

    def test_confidence_exactly_zero_passes(self) -> None:
        """Scenario 15: confidence exactly 0 -> pass."""
        event = _event_stub(
            "SignalEvent",
            timestamp=datetime.now(UTC),
            strategy_id="S1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("100"),
            confidence=Decimal("0"),
        )
        _validate_signal_event(event)

    def test_confidence_exactly_one_passes(self) -> None:
        """Scenario 15: confidence exactly 1 -> pass."""
        event = _event_stub(
            "SignalEvent",
            timestamp=datetime.now(UTC),
            strategy_id="S1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("100"),
            confidence=Decimal("1"),
        )
        _validate_signal_event(event)

    def test_confidence_greater_than_one_raises_validation_error(self) -> None:
        """Scenario 16: confidence > 1 -> ValidationError."""
        event = _event_stub(
            "SignalEvent",
            timestamp=datetime.now(UTC),
            strategy_id="S1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("100"),
            confidence=Decimal("1.1"),
        )
        with pytest.raises(ValidationError, match="confidence"):
            _validate_signal_event(event)

    def test_signal_without_optional_price_passes(self) -> None:
        """SignalEvent without optional price should pass."""
        event = _event_stub(
            "SignalEvent",
            timestamp=datetime.now(UTC),
            strategy_id="S1",
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            confidence=Decimal("0.5"),
        )
        _validate_signal_event(event)


# =============================================================================
# TEST: _validate_scan_update_event() - Count ordering
# =============================================================================


class TestValidateScanUpdateEvent:
    """Tests for _validate_scan_update_event()."""

    def test_valid_scan_update_event_passes(self, valid_scan_update_event) -> None:
        """Valid ScanUpdateEvent should pass all validations."""
        _validate_scan_update_event(valid_scan_update_event)

    def test_approved_exceeds_total_raises_validation_error(self) -> None:
        """Scenario 13: approved_candidates > total_candidates -> ValidationError."""
        event = _event_stub(
            "ScanUpdateEvent",
            timestamp=datetime.now(UTC),
            total_candidates=50,
            approved_candidates=60,
            trades_executed=30,
            duration_ms=1000,
            errors=[],
        )
        with pytest.raises(
            ValidationError,
            match="approved_candidates cannot exceed total_candidates",
        ):
            _validate_scan_update_event(event)

    def test_errors_not_list_raises_validation_error(self) -> None:
        """Scenario 19: errors field is not a list -> ValidationError."""
        event = _event_stub(
            "ScanUpdateEvent",
            timestamp=datetime.now(UTC),
            total_candidates=100,
            approved_candidates=80,
            trades_executed=50,
            duration_ms=1000,
            errors="not a list",
        )
        with pytest.raises(ValidationError, match="errors must be a list"):
            _validate_scan_update_event(event)

    def test_errors_with_non_string_raises_validation_error(self) -> None:
        """Scenario 20: errors list contains non-string -> ValidationError."""
        event = _event_stub(
            "ScanUpdateEvent",
            timestamp=datetime.now(UTC),
            total_candidates=100,
            approved_candidates=80,
            trades_executed=50,
            duration_ms=1000,
            errors=["error1", 123],
        )
        with pytest.raises(ValidationError, match="errors must contain only strings"):
            _validate_scan_update_event(event)


# =============================================================================
# TEST: _validate_pnl_update_event() - Decimal ranges, negative trade_pnl
# =============================================================================


class TestValidatePnlUpdateEvent:
    """Tests for _validate_pnl_update_event()."""

    def test_valid_pnl_update_event_passes(self, valid_pnl_update_event) -> None:
        """Valid PnLUpdateEvent should pass all validations."""
        _validate_pnl_update_event(valid_pnl_update_event)

    def test_negative_trade_pnl_passes(self) -> None:
        """Scenario 5: Valid PnLUpdateEvent with negative trade_pnl."""
        event = _event_stub(
            "PnLUpdateEvent",
            timestamp=datetime.now(UTC),
            order_id="ORD-1",
            symbol="RELIANCE",
            side="BUY",
            quantity=Decimal("100"),
            price=Decimal("100"),
            trade_pnl=Decimal("-1000"),
            cumulative_pnl=Decimal("5000"),
        )
        _validate_pnl_update_event(event)


# =============================================================================
# TEST: _validate_regime_change_event() - Metadata dict str keys/values
# =============================================================================


class TestValidateRegimeChangeEvent:
    """Tests for _validate_regime_change_event()."""

    def test_valid_regime_change_event_passes(self, valid_regime_change_event) -> None:
        """Valid RegimeChangeEvent should pass all validations."""
        _validate_regime_change_event(valid_regime_change_event)

    def test_non_string_metadata_key_raises_validation_error(self) -> None:
        """Scenario 21: Non-string metadata key -> ValidationError."""
        event = _event_stub(
            "RegimeChangeEvent",
            timestamp=datetime.now(UTC),
            regime_type="VOLATILITY_SPIKE",
            description="Volatility increasing",
            confidence=Decimal("0.85"),
            metadata={123: "value"},
        )
        with pytest.raises(
            ValidationError, match="metadata keys and values must be strings"
        ):
            _validate_regime_change_event(event)

    def test_non_string_metadata_value_raises_validation_error(self) -> None:
        """Non-string metadata value should raise ValidationError."""
        event = _event_stub(
            "RegimeChangeEvent",
            timestamp=datetime.now(UTC),
            regime_type="VOLATILITY_SPIKE",
            description="Volatility increasing",
            confidence=Decimal("0.85"),
            metadata={"key": 123},
        )
        with pytest.raises(
            ValidationError, match="metadata keys and values must be strings"
        ):
            _validate_regime_change_event(event)


# =============================================================================
# TEST: _as_decimal() - Type conversion + fail-closed
# =============================================================================


class TestAsDecimal:
    """Tests for _as_decimal()."""

    def test_valid_decimal_passes(self) -> None:
        """Valid Decimal should pass."""
        result = _as_decimal(Decimal("100.50"), "price")
        assert result == Decimal("100.50")

    def test_bool_raises_validation_error(self) -> None:
        """Scenario 22: _as_decimal with bool -> ValidationError."""
        with pytest.raises(ValidationError, match="price must be Decimal-compatible"):
            _as_decimal(True, "price")

    def test_string_raises_validation_error(self) -> None:
        """String should raise ValidationError (not Decimal-compatible)."""
        with pytest.raises(ValidationError, match="price must be Decimal-compatible"):
            _as_decimal("100.50", "price")


# =============================================================================
# TEST: _validate_decimal_range() - Inclusive bounds, boundary values
# =============================================================================


class TestValidateDecimalRange:
    """Tests for _validate_decimal_range()."""

    def test_boundary_value_passes(self) -> None:
        """Scenario 23: _validate_decimal_range at boundary -> pass."""
        _validate_decimal_range(
            value=Decimal("0"),
            field_name="price",
            lower=Decimal("0"),
            upper=Decimal("100"),
        )
        _validate_decimal_range(
            value=Decimal("100"),
            field_name="price",
            lower=Decimal("0"),
            upper=Decimal("100"),
        )

    def test_outside_range_raises_validation_error(self) -> None:
        """Value outside range should raise ValidationError."""
        with pytest.raises(ValidationError, match="price.*outside allowed range"):
            _validate_decimal_range(
                value=Decimal("101"),
                field_name="price",
                lower=Decimal("0"),
                upper=Decimal("100"),
            )


# =============================================================================
# TEST: _validate_non_empty_text() - Empty after strip, max length
# =============================================================================


class TestValidateNonEmptyText:
    """Tests for _validate_non_empty_text()."""

    def test_valid_text_passes(self) -> None:
        """Valid non-empty text should pass."""
        _validate_non_empty_text("RELIANCE", "symbol", 64)

    def test_empty_after_strip_raises_validation_error(self) -> None:
        """Empty after strip should raise ValidationError."""
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            _validate_non_empty_text("   ", "symbol", 64)

    def test_max_length_passes(self) -> None:
        """Scenario 24: _validate_non_empty_text at max length -> pass."""
        long_text = "A" * 64
        _validate_non_empty_text(long_text, "symbol", 64)

    def test_exceeds_max_length_raises_validation_error(self) -> None:
        """Exceeding max length should raise ValidationError."""
        long_text = "A" * 65
        with pytest.raises(ValidationError, match="symbol exceeds max length"):
            _validate_non_empty_text(long_text, "symbol", 64)

    def test_non_string_raises_validation_error(self) -> None:
        """Non-string should raise ValidationError."""
        with pytest.raises(ValidationError, match="symbol must be a string"):
            _validate_non_empty_text(123, "symbol", 64)


# =============================================================================
# TEST: _get_attr() - Missing attribute -> ValidationError
# =============================================================================


class TestGetAttr:
    """Tests for _get_attr()."""

    def test_existing_attribute_returns_value(self) -> None:
        """Existing attribute should return its value."""
        event = _event_stub("MarketTickEvent", symbol="RELIANCE")
        result = _get_attr(event, "symbol")
        assert result == "RELIANCE"

    def test_missing_attribute_raises_validation_error(self) -> None:
        """Scenario 8: Missing attribute -> ValidationError."""
        event = _event_stub("MarketTickEvent")
        with pytest.raises(ValidationError, match="Event missing required attribute"):
            _get_attr(event, "symbol")


# =============================================================================
# TEST: _get_optional_attr() - Missing -> None, present -> value
# =============================================================================


class TestGetOptionalAttr:
    """Tests for _get_optional_attr()."""

    def test_missing_attribute_returns_none(self) -> None:
        """Missing attribute should return None."""
        event = _event_stub("MarketTickEvent")
        result = _get_optional_attr(event, "optional_field")
        assert result is None

    def test_present_attribute_returns_value(self) -> None:
        """Present attribute should return its value."""
        event = _event_stub("MarketTickEvent", optional_field="value")
        result = _get_optional_attr(event, "optional_field")
        assert result == "value"
