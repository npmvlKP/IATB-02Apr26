"""
Tests for OHLCV payload normalization.
"""

from datetime import UTC, datetime

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.core.types import create_price
from iatb.data.normalizer import normalize_ohlcv_batch, normalize_ohlcv_record


def _raw_ohlcv(timestamp: object) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": "100.25",
        "high": "102.40",
        "low": "99.90",
        "close": "101.10",
        "volume": "1250",
    }


class TestOHLCVNormalizer:
    """Test OHLCV payload normalization behaviors."""

    def test_normalize_record_with_epoch_milliseconds(self) -> None:
        bar = normalize_ohlcv_record(
            _raw_ohlcv(1711941300000),
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            source="unit-test",
        )
        assert bar.timestamp.tzinfo == UTC
        assert bar.symbol == "RELIANCE"
        assert bar.open == create_price("100.25")

    def test_normalize_record_with_iso_timestamp(self) -> None:
        bar = normalize_ohlcv_record(
            _raw_ohlcv("2026-01-02T09:15:00+05:30"),
            symbol="NIFTY",
            exchange=Exchange.NSE,
            source="unit-test",
        )
        assert bar.timestamp.tzinfo == UTC
        assert bar.close == create_price("101.10")

    def test_normalize_record_missing_field_raises(self) -> None:
        payload = _raw_ohlcv("2026-01-01T09:15:00+00:00")
        payload.pop("volume")
        with pytest.raises(ValidationError, match="field missing: volume"):
            normalize_ohlcv_record(
                payload,
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_naive_timestamp_raises(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            normalize_ohlcv_record(
                _raw_ohlcv(datetime(2026, 1, 2, 9, 15, 0)),  # noqa: DTZ001
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_batch_accepts_monotonic_timestamps(self) -> None:
        records = [
            _raw_ohlcv("2026-01-02T09:15:00+00:00"),
            _raw_ohlcv("2026-01-02T09:16:00+00:00"),
        ]
        bars = normalize_ohlcv_batch(
            records,
            symbol="NIFTY",
            exchange=Exchange.NSE,
            source="unit-test",
        )
        assert len(bars) == 2

    def test_normalize_batch_rejects_non_monotonic_timestamps(self) -> None:
        records = [
            _raw_ohlcv("2026-01-02T09:16:00+00:00"),
            _raw_ohlcv("2026-01-02T09:15:00+00:00"),
        ]
        with pytest.raises(ValidationError, match="strictly increasing"):
            normalize_ohlcv_batch(
                records,
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_boolean_numeric_field(self) -> None:
        payload = _raw_ohlcv("2026-01-01T09:15:00+00:00")
        payload["open"] = True
        with pytest.raises(ValidationError, match="open cannot be boolean"):
            normalize_ohlcv_record(
                payload,
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_invalid_numeric_type(self) -> None:
        payload = _raw_ohlcv("2026-01-01T09:15:00+00:00")
        payload["open"] = object()
        with pytest.raises(ValidationError, match="open must be Decimal, int, float, or str"):
            normalize_ohlcv_record(
                payload,
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_non_finite_numeric(self) -> None:
        payload = _raw_ohlcv("2026-01-01T09:15:00+00:00")
        payload["open"] = "NaN"
        with pytest.raises(ValidationError, match="open must be finite"):
            normalize_ohlcv_record(
                payload,
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_empty_timestamp_string(self) -> None:
        with pytest.raises(ValidationError, match="timestamp cannot be empty"):
            normalize_ohlcv_record(
                _raw_ohlcv(" "),
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_timezone_free_iso_string(self) -> None:
        with pytest.raises(ValidationError, match="must include timezone information"):
            normalize_ohlcv_record(
                _raw_ohlcv("2026-01-01T09:15:00"),
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_record_rejects_unsupported_timestamp_type(self) -> None:
        with pytest.raises(ValidationError, match="Unsupported timestamp type"):
            normalize_ohlcv_record(
                _raw_ohlcv(object()),
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )

    def test_normalize_batch_wraps_invalid_record_with_index(self) -> None:
        invalid = _raw_ohlcv("2026-01-02T09:16:00+00:00")
        invalid.pop("open")
        with pytest.raises(ValidationError, match="index 1"):
            normalize_ohlcv_batch(
                [_raw_ohlcv("2026-01-02T09:15:00+00:00"), invalid],
                symbol="NIFTY",
                exchange=Exchange.NSE,
                source="unit-test",
            )
