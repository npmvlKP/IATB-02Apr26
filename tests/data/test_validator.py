"""
Tests for normalized market-data validation.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar, TickerSnapshot
from iatb.data.validator import (
    validate_ohlcv_bar,
    validate_ohlcv_series,
    validate_ticker_snapshot,
)

_BASE_TIMESTAMP = datetime(2026, 1, 2, 9, 15, tzinfo=UTC)


def _make_bar(offset_minutes: int, symbol: str = "RELIANCE") -> OHLCVBar:
    return OHLCVBar(
        timestamp=create_timestamp(_BASE_TIMESTAMP + timedelta(minutes=offset_minutes)),
        exchange=Exchange.NSE,
        symbol=symbol,
        open=create_price("100"),
        high=create_price("102"),
        low=create_price("99"),
        close=create_price("101"),
        volume=create_quantity("1500"),
        source="unit-test",
    )


def _make_ticker(bid: str = "99", ask: str = "101", last: str = "100") -> TickerSnapshot:
    return TickerSnapshot(
        timestamp=create_timestamp(_BASE_TIMESTAMP),
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        bid=create_price(bid),
        ask=create_price(ask),
        last=create_price(last),
        volume_24h=create_quantity("12000"),
        source="unit-test",
    )


class TestDataValidator:
    """Test normalized data model validation rules."""

    def test_validate_ohlcv_bar_passes_for_valid_input(self) -> None:
        validate_ohlcv_bar(_make_bar(0))

    def test_validate_ohlcv_bar_rejects_invalid_high(self) -> None:
        invalid = OHLCVBar(
            timestamp=create_timestamp(_BASE_TIMESTAMP),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            open=create_price("100"),
            high=create_price("98"),
            low=create_price("97"),
            close=create_price("99"),
            volume=create_quantity("10"),
            source="unit-test",
        )
        with pytest.raises(ValidationError, match="high price cannot be lower"):
            validate_ohlcv_bar(invalid)

    def test_validate_ohlcv_series_rejects_symbol_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="only one symbol"):
            validate_ohlcv_series([_make_bar(0, "RELIANCE"), _make_bar(1, "INFY")])

    def test_validate_ohlcv_series_rejects_non_monotonic_timestamps(self) -> None:
        with pytest.raises(ValidationError, match="strictly increasing"):
            validate_ohlcv_series([_make_bar(1), _make_bar(0)])

    def test_validate_ticker_snapshot_accepts_valid_input(self) -> None:
        validate_ticker_snapshot(_make_ticker())

    def test_validate_ticker_snapshot_rejects_inverted_spread(self) -> None:
        with pytest.raises(ValidationError, match="bid cannot exceed ask"):
            validate_ticker_snapshot(_make_ticker(bid="102", ask="101", last="101"))

    def test_validate_ticker_snapshot_rejects_last_outside_spread(self) -> None:
        with pytest.raises(ValidationError, match="within bid/ask spread"):
            validate_ticker_snapshot(_make_ticker(bid="99", ask="101", last="103"))

    def test_validate_ohlcv_bar_rejects_empty_symbol(self) -> None:
        invalid = replace(_make_bar(0), symbol=" ")
        with pytest.raises(ValidationError, match="symbol cannot be empty"):
            validate_ohlcv_bar(invalid)

    def test_validate_ohlcv_bar_rejects_future_timestamp(self) -> None:
        invalid = replace(
            _make_bar(0),
            timestamp=create_timestamp(datetime.now(UTC) + timedelta(minutes=5)),
        )
        with pytest.raises(ValidationError, match="cannot be in the future"):
            validate_ohlcv_bar(invalid)

    def test_validate_ohlcv_bar_rejects_negative_open(self) -> None:
        invalid = replace(_make_bar(0), open=Decimal("-1"))
        with pytest.raises(ValidationError, match="open cannot be negative"):
            validate_ohlcv_bar(invalid)

    def test_validate_ohlcv_bar_rejects_invalid_low_boundary(self) -> None:
        invalid = replace(_make_bar(0), low=create_price("102"))
        with pytest.raises(ValidationError, match="low price cannot be greater"):
            validate_ohlcv_bar(invalid)

    def test_validate_ohlcv_series_rejects_exchange_mismatch(self) -> None:
        other_exchange_bar = replace(_make_bar(1), exchange=Exchange.BSE)
        with pytest.raises(ValidationError, match="only one exchange"):
            validate_ohlcv_series([_make_bar(0), other_exchange_bar])

    def test_validate_ticker_snapshot_rejects_empty_source(self) -> None:
        invalid = replace(_make_ticker(), source=" ")
        with pytest.raises(ValidationError, match="source cannot be empty"):
            validate_ticker_snapshot(invalid)

    def test_validate_ticker_snapshot_rejects_negative_bid(self) -> None:
        invalid = replace(_make_ticker(), bid=Decimal("-1"))
        with pytest.raises(ValidationError, match="bid cannot be negative"):
            validate_ticker_snapshot(invalid)

    def test_validate_ticker_snapshot_rejects_future_timestamp(self) -> None:
        invalid = replace(
            _make_ticker(),
            timestamp=create_timestamp(datetime.now(UTC) + timedelta(minutes=5)),
        )
        with pytest.raises(ValidationError, match="cannot be in the future"):
            validate_ticker_snapshot(invalid)
