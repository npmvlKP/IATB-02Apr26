"""Supplemental coverage tests for iatb.core.types — edge cases and boundary values."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)


class TestCreatePriceBoundaries:
    def test_zero_price_accepted(self) -> None:
        price = create_price("0")
        assert price == Decimal("0")

    def test_zero_int_price(self) -> None:
        price = create_price(0)
        assert price == Decimal("0")

    def test_large_price_from_string(self) -> None:
        price = create_price("999999999999.9999")
        assert price == Decimal("999999999999.9999")

    def test_tiny_fractional_price(self) -> None:
        price = create_price("0.0001")
        assert price == Decimal("0.0001")

    def test_negative_int_raises(self) -> None:
        with pytest.raises(ValueError, match="Price cannot be negative"):
            create_price(-1)

    def test_negative_decimal_raises(self) -> None:
        with pytest.raises(ValueError, match="Price cannot be negative"):
            create_price(Decimal("-0.01"))

    def test_price_is_newtype_over_decimal(self) -> None:
        price = create_price("10")
        assert isinstance(price, Decimal)

    def test_price_preserves_precision(self) -> None:
        price = create_price("100.125")
        assert price == Decimal("100.125")

    def test_price_from_scientific_notation_string(self) -> None:
        price = create_price("1E2")
        assert price == Decimal("1E2")

    def test_price_negative_zero(self) -> None:
        price = create_price("-0")
        assert price == Decimal("0")


class TestCreateQuantityBoundaries:
    def test_zero_quantity_accepted(self) -> None:
        qty = create_quantity("0")
        assert qty == Decimal("0")

    def test_zero_int_quantity(self) -> None:
        qty = create_quantity(0)
        assert qty == Decimal("0")

    def test_large_quantity(self) -> None:
        qty = create_quantity("999999999")
        assert qty == Decimal("999999999")

    def test_fractional_quantity(self) -> None:
        qty = create_quantity("0.5")
        assert qty == Decimal("0.5")

    def test_negative_int_raises(self) -> None:
        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            create_quantity(-5)

    def test_negative_decimal_raises(self) -> None:
        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            create_quantity(Decimal("-100"))

    def test_quantity_is_newtype_over_decimal(self) -> None:
        qty = create_quantity("50")
        assert isinstance(qty, Decimal)

    def test_quantity_preserves_precision(self) -> None:
        qty = create_quantity("10.125")
        assert qty == Decimal("10.125")

    def test_quantity_negative_zero(self) -> None:
        qty = create_quantity("-0")
        assert qty == Decimal("0")


class TestCreateTimestampBoundaries:
    def test_exact_utc_epoch(self) -> None:
        epoch = datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)
        ts = create_timestamp(epoch)
        assert ts.tzinfo == UTC
        assert ts.year == 1970

    def test_far_future_utc(self) -> None:
        future = datetime(2099, 12, 31, 23, 59, 59, tzinfo=UTC)
        ts = create_timestamp(future)
        assert ts.tzinfo == UTC
        assert ts.year == 2099

    def test_microsecond_precision(self) -> None:
        dt = datetime(2024, 6, 15, 10, 30, 0, 123456, tzinfo=UTC)
        ts = create_timestamp(dt)
        assert ts.microsecond == 123456

    def test_naive_datetime_raises(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            create_timestamp(datetime(2024, 6, 15, 10, 0))

    def test_non_utc_positive_offset_raises(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ValueError, match="UTC"):
            create_timestamp(datetime(2024, 6, 15, 10, 0, tzinfo=ist))

    def test_non_utc_negative_offset_raises(self) -> None:
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValueError, match="UTC"):
            create_timestamp(datetime(2024, 6, 15, 10, 0, tzinfo=est))

    def test_utc_offset_zero_accepted(self) -> None:
        utc_zero = timezone(timedelta(0))
        dt = datetime(2024, 6, 15, 10, 0, tzinfo=utc_zero)
        ts = create_timestamp(dt)
        assert ts.tzinfo is not None

    def test_timestamp_is_newtype_over_datetime(self) -> None:
        dt = datetime.now(UTC)
        ts = create_timestamp(dt)
        assert isinstance(ts, datetime)


class TestTypeInteractions:
    def test_price_and_quantity_distinct_newtypes(self) -> None:
        price = create_price("100")
        qty = create_quantity("100")
        assert isinstance(price, Decimal)
        assert isinstance(qty, Decimal)
        assert price == qty

    def test_price_arithmetic_with_decimal(self) -> None:
        price = create_price("100.50")
        result = price * Decimal("2")
        assert result == Decimal("201.00")

    def test_quantity_arithmetic_with_decimal(self) -> None:
        qty = create_quantity("50")
        result = qty * Decimal("3")
        assert result == Decimal("150")

    def test_timestamp_arithmetic(self) -> None:
        dt = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        ts = create_timestamp(dt)
        later = ts + timedelta(hours=1)
        assert later.hour == 11


class TestCreatePriceAdditionalEdgeCases:
    def test_price_from_int(self) -> None:
        price = create_price(42)
        assert price == Decimal("42")

    def test_price_from_decimal(self) -> None:
        price = create_price(Decimal("99.99"))
        assert price == Decimal("99.99")

    def test_price_large_precision(self) -> None:
        price = create_price("0.123456789")
        assert price == Decimal("0.123456789")


class TestCreateQuantityAdditionalEdgeCases:
    def test_quantity_from_int(self) -> None:
        qty = create_quantity(100)
        assert qty == Decimal("100")

    def test_quantity_from_decimal(self) -> None:
        qty = create_quantity(Decimal("33.33"))
        assert qty == Decimal("33.33")


class TestCreateTimestampAdditionalEdgeCases:
    def test_utc_timezone_zero_vs_utc_module(self) -> None:
        from datetime import timezone as tz

        dt_with_tz_zero = datetime(2024, 6, 15, 10, 0, tzinfo=tz(timedelta(0)))
        ts = create_timestamp(dt_with_tz_zero)
        assert ts.tzinfo is not None

    def test_create_timestamp_returns_same_datetime_value(self) -> None:
        dt = datetime(2024, 6, 15, 10, 30, 45, 123456, tzinfo=UTC)
        ts = create_timestamp(dt)
        assert ts == dt
        assert ts.year == dt.year
        assert ts.month == dt.month
        assert ts.day == dt.day
