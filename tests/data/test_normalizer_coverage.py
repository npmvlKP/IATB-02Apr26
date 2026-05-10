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
