"""
Tests for core type definitions.
"""

from datetime import UTC, datetime, timezone
from decimal import Decimal

import pytest
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)


class TestPrice:
    """Test Price type."""

    def test_create_price_from_string(self) -> None:
        """Test creating price from string."""
        price = create_price("100.50")
        assert float(price) == 100.50

    def test_create_price_from_int(self) -> None:
        """Test creating price from int."""
        price = create_price(100)
        assert float(price) == 100.0

    def test_create_price_from_decimal(self) -> None:
        """Test creating price from Decimal."""
        price = create_price(Decimal("100.50"))
        assert float(price) == 100.50

    def test_create_price_negative_raises_error(self) -> None:
        """Test that negative price raises ValueError."""
        with pytest.raises(ValueError, match="Price cannot be negative"):
            create_price("-10.0")

    def test_price_type_is_decimal(self) -> None:
        """Test that Price is based on Decimal."""
        price = create_price("100.0")
        assert isinstance(price, Decimal)


class TestQuantity:
    """Test Quantity type."""

    def test_create_quantity_from_string(self) -> None:
        """Test creating quantity from string."""
        quantity = create_quantity("50.25")
        assert float(quantity) == 50.25

    def test_create_quantity_from_int(self) -> None:
        """Test creating quantity from int."""
        quantity = create_quantity(100)
        assert float(quantity) == 100.0

    def test_create_quantity_from_decimal(self) -> None:
        """Test creating quantity from Decimal."""
        quantity = create_quantity(Decimal("50.25"))
        assert float(quantity) == 50.25

    def test_create_quantity_negative_raises_error(self) -> None:
        """Test that negative quantity raises ValueError."""
        with pytest.raises(ValueError, match="Quantity cannot be negative"):
            create_quantity("-10.0")

    def test_quantity_type_is_decimal(self) -> None:
        """Test that Quantity is based on Decimal."""
        quantity = create_quantity("100.0")
        assert isinstance(quantity, Decimal)


class TestTimestamp:
    """Test Timestamp type."""

    def test_create_timestamp_utc(self) -> None:
        """Test creating timestamp with UTC datetime."""
        dt = datetime.now(UTC)
        timestamp = create_timestamp(dt)
        assert timestamp.tzinfo == UTC

    def test_create_timestamp_other_timezone(self) -> None:
        """Test non-UTC timezone is rejected."""
        from datetime import timedelta

        tz = timezone(timedelta(hours=5, minutes=30))
        dt = datetime.now(tz)
        with pytest.raises(ValueError, match="Timestamp must use UTC timezone"):
            create_timestamp(dt)

    def test_create_timestamp_naive_raises_error(self) -> None:
        """Test that naive datetime raises ValueError."""
        dt = datetime.now(UTC).replace(tzinfo=None)
        with pytest.raises(ValueError, match="Timestamp must be timezone-aware"):
            create_timestamp(dt)

    def test_timestamp_type_is_datetime(self) -> None:
        """Test that Timestamp is based on datetime."""
        dt = datetime.now(UTC)
        timestamp = create_timestamp(dt)
        assert isinstance(timestamp, datetime)
