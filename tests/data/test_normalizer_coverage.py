"""
Test coverage for `src/iatb/data/normalizer.py` — focuses on error paths and boundary cases.
Uses shared fixtures from `tests/conftest.py` and avoids float in financial assertions.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.data.normalizer import normalize_ohlcv_batch, normalize_ohlcv_record


@pytest.fixture
@patch("iatb.data.normalizer.create_price")
@patch("iatb.data.normalizer.create_quantity")
@patch("iatb.data.normalizer.create_timestamp")
def mock_helpers(mock_timestamp, mock_quantity, mock_price):
    mock_timestamp.side_effect = create_timestamp
    mock_quantity.side_effect = create_quantity
    mock_price.side_effect = create_price


@pytest.mark.parametrize(
    "timestamp_input,expected_timestamp",
    [
        (
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        ),  # datetime aware
        (
            1_704_097_800,
            datetime(2024, 1, 1, 8, 30, tzinfo=UTC),
        ),  # unix timestamp (seconds) -> UTC
        (
            "2024-01-01T09:30:00+00:00",
            datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        ),  # ISO string
    ],
)
def test_normalize_valid_ohlcv_record(timestamp_input, expected_timestamp, mock_helpers):
    """Valid OHLCV record with varying timestamp types."""
    raw_record = {
        "timestamp": timestamp_input,
        "open": "100.00",
        "high": "101.00",
        "low": "99.00",
        "close": "100.50",
        "volume": "5000",
    }
    bar = normalize_ohlcv_record(
        raw_record,
        symbol="AAPL",
        exchange=Exchange.NSE,
        source="kite",
    )
    assert bar.timestamp == create_timestamp(expected_timestamp)
    assert bar.open == create_price(Decimal("100.00"))
    assert bar.high == create_price(Decimal("101.00"))
    assert bar.low == create_price(Decimal("99.00"))
    assert bar.close == create_price(Decimal("100.50"))
    assert bar.volume == create_quantity(Decimal("5000"))


def test_normalize_batch(mock_helpers):
    """Batch normalization preserves order and validates series."""
    raw_records = [
        {
            "timestamp": "2024-01-01T09:30:00+00:00",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "5000",
        },
        {
            "timestamp": "2024-01-02T09:30:00+00:00",
            "open": "101",
            "high": "102",
            "low": "100",
            "close": "101.5",
            "volume": "6000",
        },
        {
            "timestamp": "2024-01-03T09:30:00+00:00",
            "open": "102",
            "high": "103",
            "low": "101",
            "close": "102.5",
            "volume": "7000",
        },
    ]
    bars = normalize_ohlcv_batch(
        raw_records,
        symbol="AAPL",
        exchange=Exchange.NSE,
        source="kite",
        validate_series=False,
    )
    assert len(bars) == 3
    assert all(isinstance(bar, OHLCVBar) for bar in bars)


@pytest.mark.parametrize(
    "missing_key",
    ["timestamp", "open", "high", "low", "close", "volume"],
)
def test_missing_required_key(missing_key, mock_helpers):
    """Missing required key raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    del raw_record[missing_key]
    with pytest.raises(ValidationError, match=f"OHLCV field missing: {missing_key}"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("open", True),
        ("high", False),
        ("low", True),
        ("close", False),
        ("volume", True),
    ],
)
def test_boolean_value_raises(field, value, mock_helpers):
    """Boolean value raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    raw_record[field] = value
    with pytest.raises(ValidationError, match=f"{field} cannot be boolean"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("open", Decimal("Infinity")),
        ("high", Decimal("-Infinity")),
        ("low", Decimal("NaN")),
        ("close", Decimal("NaN")),
        ("volume", Decimal("NaN")),
    ],
)
def test_non_finite_decimal_raises(field, value, mock_helpers):
    """Non-finite Decimal raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    raw_record[field] = str(value)
    with pytest.raises(ValidationError, match=f"{field} must be finite"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_unsupported_timestamp_type(mock_helpers):
    """Unsupported timestamp type raises ValidationError."""
    raw_record = {
        "timestamp": None,
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="Unsupported timestamp type"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_batch_error_with_index(mock_helpers):
    """Batch error includes index for context."""
    raw_records = [
        {
            "timestamp": "2024-01-01T09:30:00+00:00",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "5000",
        },
        {
            "timestamp": "2024-01-01T09:30:00+00:00",
            "open": "100",
            "high": "101",
            "close": "100.5",  # Missing 'low' and 'volume'
        },
    ]
    with pytest.raises(ValidationError, match="Invalid OHLCV record at index 1"):
        normalize_ohlcv_batch(
            raw_records,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_invalid_type_raises(mock_helpers):
    """Invalid type (not Decimal, int, float, or str) raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00+00:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    raw_record["open"] = object()
    with pytest.raises(ValidationError, match="open must be Decimal, int, float, or str"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_invalid_decimal_string_raises(mock_helpers):
    """Invalid Decimal string raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00+00:00",
        "open": "not_a_number",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="open is not Decimal-compatible"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_naive_datetime_raises(mock_helpers):
    """Naive datetime (no timezone) raises ValidationError."""
    from datetime import datetime as dt

    raw_record = {
        "timestamp": dt(2024, 1, 1, 9, 30),  # noqa: DTZ001
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="timestamp must be timezone-aware"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_invalid_unix_timestamp_raises(mock_helpers):
    """Invalid unix timestamp raises ValidationError."""
    raw_record = {
        "timestamp": 99999999999999999,  # Way too large
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="invalid unix timestamp"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_empty_timestamp_string_raises(mock_helpers):
    """Empty timestamp string raises ValidationError."""
    raw_record = {
        "timestamp": " ",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="timestamp cannot be empty"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_z_suffix_timestamp(mock_helpers):
    """Z suffix is properly converted to +00:00."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00Z",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    bar = normalize_ohlcv_record(
        raw_record,
        symbol="AAPL",
        exchange=Exchange.NSE,
        source="kite",
    )
    assert bar.timestamp.tzinfo == UTC


def test_invalid_iso_timestamp_raises(mock_helpers):
    """Invalid ISO timestamp string raises ValidationError."""
    raw_record = {
        "timestamp": "not-a-valid-timestamp",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="invalid ISO timestamp string"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_timezone_free_iso_string_raises(mock_helpers):
    """ISO string without timezone raises ValidationError."""
    raw_record = {
        "timestamp": "2024-01-01T09:30:00",
        "open": "100",
        "high": "101",
        "low": "99",
        "close": "100.5",
        "volume": "5000",
    }
    with pytest.raises(ValidationError, match="must include timezone information"):
        normalize_ohlcv_record(
            raw_record,
            symbol="AAPL",
            exchange=Exchange.NSE,
            source="kite",
        )


def test_batch_validate_series_enabled(mock_helpers):
    """Batch with validate_series=True calls validate_ohlcv_series."""
    raw_records = [
        {
            "timestamp": "2024-01-01T09:30:00+00:00",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "5000",
        },
        {
            "timestamp": "2024-01-02T09:30:00+00:00",
            "open": "101",
            "high": "102",
            "low": "100",
            "close": "101.5",
            "volume": "6000",
        },
    ]
    # Should pass with validate_series=True (default)
    bars = normalize_ohlcv_batch(
        raw_records,
        symbol="AAPL",
        exchange=Exchange.NSE,
        source="kite",
        validate_series=True,
    )
    assert len(bars) == 2
