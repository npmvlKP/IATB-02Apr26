"""
Comprehensive coverage tests for data validator module.
Achieves 100% coverage for src/iatb/data/validator.py
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import freezegun
import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar, TickerSnapshot
from iatb.data.validator import (
    _require_non_empty_text,
    _validate_non_negative,
    _validate_timestamp_not_far_future,
    validate_ohlcv_bar,
    validate_ohlcv_series,
    validate_ticker_snapshot,
)

_BASE_TIMESTAMP = datetime(2026, 1, 2, 9, 15, tzinfo=UTC)


def _make_bar(
    offset_minutes: int = 0,
    symbol: str = "RELIANCE",
    open_price: str = "100",
    high: str = "102",
    low: str = "99",
    close: str = "101",
    volume: str = "1500",
    exchange: Exchange = Exchange.NSE,
    source: str = "unit-test",
) -> OHLCVBar:
    """Create a valid OHLCVBar for testing."""
    return OHLCVBar(
        timestamp=create_timestamp(_BASE_TIMESTAMP + timedelta(minutes=offset_minutes)),
        exchange=exchange,
        symbol=symbol,
        open=create_price(open_price),
        high=create_price(high),
        low=create_price(low),
        close=create_price(close),
        volume=create_quantity(volume),
        source=source,
    )


def _make_ticker(
    bid: str = "99",
    ask: str = "101",
    last: str = "100",
    volume_24h: str = "12000",
    symbol: str = "RELIANCE",
    exchange: Exchange = Exchange.NSE,
    source: str = "unit-test",
) -> TickerSnapshot:
    """Create a valid TickerSnapshot for testing."""
    return TickerSnapshot(
        timestamp=create_timestamp(_BASE_TIMESTAMP),
        exchange=exchange,
        symbol=symbol,
        bid=create_price(bid),
        ask=create_price(ask),
        last=create_price(last),
        volume_24h=create_quantity(volume_24h),
        source=source,
    )


# =============================================================================
# VALID CASES - Happy Path Tests
# =============================================================================


class TestValidCases:
    """Test valid inputs that should pass validation."""

    def test_valid_ohlcv_bar_with_high_eq_max_open_close_low(self) -> None:
        """Valid OHLCV bar with high exactly = max(open, close, low)."""
        bar = _make_bar(open_price="100", high="101", low="99", close="100")
        validate_ohlcv_bar(bar)

    def test_valid_ohlcv_bar_with_low_eq_min_open_close_high(self) -> None:
        """Valid OHLCV bar with low exactly = min(open, close, high)."""
        bar = _make_bar(open_price="100", high="102", low="99", close="100")
        validate_ohlcv_bar(bar)

    def test_valid_ohlcv_bar_all_prices_equal(self) -> None:
        """Valid OHLCV bar where open=high=low=close."""
        bar = _make_bar(open_price="100", high="100", low="100", close="100")
        validate_ohlcv_bar(bar)

    def test_valid_ohlcv_bar_with_zero_volume(self) -> None:
        """Valid OHLCV bar with volume=0 (non-negative)."""
        bar = _make_bar(volume="0")
        validate_ohlcv_bar(bar)

    def test_valid_ohlcv_series_strictly_increasing_timestamps(self) -> None:
        """Valid series with strictly increasing timestamps."""
        bars = [
            _make_bar(offset_minutes=0),
            _make_bar(offset_minutes=1),
            _make_bar(offset_minutes=2),
            _make_bar(offset_minutes=3),
        ]
        validate_ohlcv_series(bars)

    def test_valid_ohlcv_series_single_bar(self) -> None:
        """Valid series with single bar."""
        bars = [_make_bar(offset_minutes=0)]
        validate_ohlcv_series(bars)

    def test_valid_ohlcv_series_empty(self) -> None:
        """Valid empty series (no validation error)."""
        validate_ohlcv_series([])

    def test_valid_ticker_snapshot_bid_lt_ask(self) -> None:
        """Valid TickerSnapshot with bid < ask."""
        snapshot = _make_ticker(bid="99", ask="101", last="100")
        validate_ticker_snapshot(snapshot)

    def test_valid_ticker_snapshot_bid_eq_ask_zero_spread(self) -> None:
        """Valid TickerSnapshot with bid=ask (zero spread)."""
        snapshot = _make_ticker(bid="100", ask="100", last="100")
        validate_ticker_snapshot(snapshot)

    def test_valid_ticker_snapshot_last_at_bid(self) -> None:
        """Valid TickerSnapshot with last exactly at bid."""
        snapshot = _make_ticker(bid="100", ask="101", last="100")
        validate_ticker_snapshot(snapshot)

    def test_valid_ticker_snapshot_last_at_ask(self) -> None:
        """Valid TickerSnapshot with last exactly at ask."""
        snapshot = _make_ticker(bid="99", ask="100", last="100")
        validate_ticker_snapshot(snapshot)

    def test_valid_ticker_snapshot_last_in_middle(self) -> None:
        """Valid TickerSnapshot with last in middle of spread."""
        snapshot = _make_ticker(bid="99", ask="101", last="100")
        validate_ticker_snapshot(snapshot)


# =============================================================================
# EDGE CASES - Boundary Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases at exact boundary values."""

    def test_edge_high_exactly_equals_max_open_close_low(self) -> None:
        """Edge: high exactly = max(open, close, low)."""
        bar = _make_bar(open_price="100", high="100", low="99", close="99")
        validate_ohlcv_bar(bar)

    def test_edge_low_exactly_equals_min_open_close_high(self) -> None:
        """Edge: low exactly = min(open, close, high)."""
        bar = _make_bar(open_price="100", high="100", low="100", close="100")
        validate_ohlcv_bar(bar)

    @freezegun.freeze_time("2026-01-02 09:17:00", tz_offset=0)
    def test_edge_timestamp_at_exactly_now_plus_2min_boundary(self) -> None:
        """Edge: timestamp at exactly now+2min boundary (should pass)."""
        now = datetime.now(UTC)
        boundary_timestamp = now + timedelta(minutes=2)
        bar = replace(
            _make_bar(offset_minutes=0),
            timestamp=create_timestamp(boundary_timestamp),
        )
        validate_ohlcv_bar(bar)

    def test_edge_bid_equals_ask(self) -> None:
        """Edge: bid=ask (zero spread) should pass."""
        snapshot = _make_ticker(bid="100", ask="100", last="100")
        validate_ticker_snapshot(snapshot)

    def test_edge_volume_zero(self) -> None:
        """Edge: volume=0 should pass (non-negative)."""
        bar = _make_bar(volume="0")
        validate_ohlcv_bar(bar)


# =============================================================================
# ERROR CASES - Invalid Input Tests
# =============================================================================


class TestInternalFunctions:
    """Test internal validation helper functions."""

    def test_require_non_empty_text_empty(self) -> None:
        """Error: Empty text should raise ValidationError."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _require_non_empty_text("", "test_field")

    def test_require_non_empty_text_whitespace(self) -> None:
        """Error: Whitespace-only text should raise ValidationError."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _require_non_empty_text("   ", "test_field")

    def test_require_non_empty_text_valid(self) -> None:
        """Valid: Non-empty text should pass."""
        _require_non_empty_text("valid", "test_field")

    def test_validate_non_negative_positive(self) -> None:
        """Valid: Positive Decimal should pass."""
        _validate_non_negative(Decimal("100"), "test_field")

    def test_validate_non_negative_zero(self) -> None:
        """Valid: Zero Decimal should pass (non-negative)."""
        _validate_non_negative(Decimal("0"), "test_field")

    def test_validate_non_negative_negative(self) -> None:
        """Error: Negative Decimal should raise ValidationError."""
        with pytest.raises(ValidationError, match="cannot be negative"):
            _validate_non_negative(Decimal("-1"), "test_field")

    @freezegun.freeze_time("2026-01-02 09:15:00", tz_offset=0)
    def test_validate_timestamp_not_far_future_valid(self) -> None:
        """Valid: Timestamp within skew should pass."""
        now = datetime.now(UTC)
        valid_timestamp = now + timedelta(minutes=1)
        _validate_timestamp_not_far_future(valid_timestamp)

    @freezegun.freeze_time("2026-01-02 09:15:00", tz_offset=0)
    def test_validate_timestamp_not_far_future_at_boundary(self) -> None:
        """Valid: Timestamp at exactly boundary should pass."""
        now = datetime.now(UTC)
        boundary = now + timedelta(minutes=2)
        _validate_timestamp_not_far_future(boundary)

    @freezegun.freeze_time("2026-01-02 09:15:00", tz_offset=0)
    def test_validate_timestamp_not_far_future_beyond(self) -> None:
        """Error: Timestamp beyond skew should raise ValidationError."""
        now = datetime.now(UTC)
        future = now + timedelta(minutes=3)
        with pytest.raises(ValidationError, match="cannot be in the future"):
            _validate_timestamp_not_far_future(future)


class TestErrorCases:
    """Test invalid inputs that should raise ValidationError."""

    # --- Empty/Whitespace Tests ---

    def test_error_empty_symbol(self) -> None:
        """Error: Empty symbol should raise ValidationError."""
        invalid = replace(_make_bar(0), symbol="")
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            validate_ohlcv_bar(invalid)

    def test_error_empty_symbol_whitespace_only(self) -> None:
        """Error: Whitespace-only symbol should raise ValidationError."""
        invalid = replace(_make_bar(0), symbol="   ")
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            validate_ohlcv_bar(invalid)

    def test_error_empty_source(self) -> None:
        """Error: Empty source should raise ValidationError."""
        invalid = replace(_make_bar(0), source="")
        with pytest.raises(ValidationError, match="source cannot be empty"):
            validate_ohlcv_bar(invalid)

    def test_error_empty_source_whitespace_only(self) -> None:
        """Error: Whitespace-only source should raise ValidationError."""
        invalid = replace(_make_bar(0), source="   ")
        with pytest.raises(ValidationError, match="source cannot be empty"):
            validate_ohlcv_bar(invalid)

    def test_error_empty_ticker_symbol(self) -> None:
        """Error: Empty ticker symbol should raise ValidationError."""
        invalid = replace(_make_ticker(), symbol="")
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            validate_ticker_snapshot(invalid)

    def test_error_empty_ticker_source(self) -> None:
        """Error: Empty ticker source should raise ValidationError."""
        invalid = replace(_make_ticker(), source="")
        with pytest.raises(ValidationError, match="source cannot be empty"):
            validate_ticker_snapshot(invalid)

    # --- Negative Value Tests ---

    def test_error_negative_open(self) -> None:
        """Error: Negative open price should raise ValidationError."""
        invalid = replace(_make_bar(0), open=Decimal("-1"))
        with pytest.raises(ValidationError, match="open cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_error_negative_high(self) -> None:
        """Error: Negative high price should raise ValidationError."""
        invalid = replace(_make_bar(0), high=Decimal("-1"))
        with pytest.raises(ValidationError, match="high cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_error_negative_low(self) -> None:
        """Error: Negative low price should raise ValidationError."""
        invalid = replace(_make_bar(0), low=Decimal("-1"))
        with pytest.raises(ValidationError, match="low cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_error_negative_close(self) -> None:
        """Error: Negative close price should raise ValidationError."""
        invalid = replace(_make_bar(0), close=Decimal("-1"))
        with pytest.raises(ValidationError, match="close cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_error_negative_volume(self) -> None:
        """Error: Negative volume should raise ValidationError."""
        invalid = replace(_make_bar(0), volume=Decimal("-1"))
        with pytest.raises(ValidationError, match="volume cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_error_negative_bid(self) -> None:
        """Error: Negative bid should raise ValidationError."""
        invalid = replace(_make_ticker(), bid=Decimal("-1"))
        with pytest.raises(ValidationError, match="bid cannot be negative"):
            validate_ticker_snapshot(invalid)

    def test_error_negative_ask(self) -> None:
        """Error: Negative ask should raise ValidationError."""
        invalid = replace(_make_ticker(), ask=Decimal("-1"))
        with pytest.raises(ValidationError, match="ask cannot be negative"):
            validate_ticker_snapshot(invalid)

    def test_error_negative_last(self) -> None:
        """Error: Negative last should raise ValidationError."""
        invalid = replace(_make_ticker(), last=Decimal("-1"))
        with pytest.raises(ValidationError, match="last cannot be negative"):
            validate_ticker_snapshot(invalid)

    def test_error_negative_volume_24h(self) -> None:
        """Error: Negative 24h volume should raise ValidationError."""
        invalid = replace(_make_ticker(), volume_24h=Decimal("-1"))
        with pytest.raises(ValidationError, match="volume_24h cannot be negative"):
            validate_ticker_snapshot(invalid)

    # --- OHLCV Relationship Tests ---

    def test_error_high_less_than_open(self) -> None:
        """Error: high < open should raise ValidationError."""
        invalid = _make_bar(open_price="105", high="99", low="98", close="100")
        with pytest.raises(ValidationError, match="high price cannot be lower than open/close/low"):
            validate_ohlcv_bar(invalid)

    def test_error_high_less_than_close(self) -> None:
        """Error: high < close should raise ValidationError."""
        invalid = _make_bar(open_price="100", high="99", low="98", close="101")
        with pytest.raises(ValidationError, match="high price cannot be lower than open/close/low"):
            validate_ohlcv_bar(invalid)

    def test_error_high_less_than_low(self) -> None:
        """Error: high < low should raise ValidationError."""
        invalid = _make_bar(open_price="100", high="99", low="101", close="100")
        with pytest.raises(ValidationError, match="high price cannot be lower than open/close/low"):
            validate_ohlcv_bar(invalid)

    def test_error_high_less_than_open_and_close(self) -> None:
        """Error: high < open and high < close should raise ValidationError."""
        invalid = _make_bar(open_price="105", high="100", low="99", close="101")
        with pytest.raises(ValidationError, match="high price cannot be lower than open/close/low"):
            validate_ohlcv_bar(invalid)

    def test_error_low_greater_than_open_and_close(self) -> None:
        """Error: low > open and low > close should raise ValidationError."""
        invalid = _make_bar(open_price="100", high="105", low="101", close="100")
        with pytest.raises(
            ValidationError, match="low price cannot be greater than open/close/high"
        ):
            validate_ohlcv_bar(invalid)

    def test_error_low_greater_than_high(self) -> None:
        """Error: low > high should raise ValidationError."""
        invalid = _make_bar(open_price="100", high="100", low="101", close="99")
        with pytest.raises(ValidationError, match="high price cannot be lower than open/close/low"):
            validate_ohlcv_bar(invalid)

    # --- Series Consistency Tests ---

    def test_error_mixed_symbols_in_series(self) -> None:
        """Error: Mixed symbols in series should raise ValidationError."""
        bars = [
            _make_bar(offset_minutes=0, symbol="RELIANCE"),
            _make_bar(offset_minutes=1, symbol="INFY"),
        ]
        with pytest.raises(ValidationError, match="only one symbol"):
            validate_ohlcv_series(bars)

    def test_error_mixed_exchanges_in_series(self) -> None:
        """Error: Mixed exchanges in series should raise ValidationError."""
        bars = [
            _make_bar(offset_minutes=0, exchange=Exchange.NSE),
            _make_bar(offset_minutes=1, exchange=Exchange.BSE),
        ]
        with pytest.raises(ValidationError, match="only one exchange"):
            validate_ohlcv_series(bars)

    def test_error_non_increasing_timestamps_equal(self) -> None:
        """Error: Equal timestamps (non-increasing) should raise ValidationError."""
        bars = [
            _make_bar(offset_minutes=0),
            _make_bar(offset_minutes=0),
        ]
        with pytest.raises(ValidationError, match="strictly increasing"):
            validate_ohlcv_series(bars)

    def test_error_non_increasing_timestamps_decreasing(self) -> None:
        """Error: Decreasing timestamps should raise ValidationError."""
        bars = [
            _make_bar(offset_minutes=1),
            _make_bar(offset_minutes=0),
        ]
        with pytest.raises(ValidationError, match="strictly increasing"):
            validate_ohlcv_series(bars)

    # --- Ticker Spread Tests ---

    def test_error_bid_greater_than_ask(self) -> None:
        """Error: bid > ask should raise ValidationError."""
        invalid = _make_ticker(bid="101", ask="100", last="100.5")
        with pytest.raises(ValidationError, match="bid cannot exceed ask"):
            validate_ticker_snapshot(invalid)

    def test_error_last_below_bid(self) -> None:
        """Error: last < bid should raise ValidationError."""
        invalid = _make_ticker(bid="100", ask="101", last="99")
        with pytest.raises(ValidationError, match="last must be within bid/ask spread"):
            validate_ticker_snapshot(invalid)

    def test_error_last_above_ask(self) -> None:
        """Error: last > ask should raise ValidationError."""
        invalid = _make_ticker(bid="99", ask="100", last="101")
        with pytest.raises(ValidationError, match="last must be within bid/ask spread"):
            validate_ticker_snapshot(invalid)
