"""
Core type definitions for IATB.

Provides strict type aliases for financial data to ensure type safety
and prevent floating-point arithmetic errors.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import NewType

# Decimal-based financial types to prevent floating-point errors
Price = NewType("Price", Decimal)
Quantity = NewType("Quantity", Decimal)

# UTC-aware timestamp type
Timestamp = NewType("Timestamp", datetime)


def create_price(value: str | int | Decimal) -> Price:
    """Create a Price value with validation."""
    decimal_value = Decimal(str(value))
    if decimal_value < 0:
        msg = f"Price cannot be negative: {decimal_value}"
        raise ValueError(msg)
    return Price(decimal_value)


def create_quantity(value: str | int | Decimal) -> Quantity:
    """Create a Quantity value with validation."""
    decimal_value = Decimal(str(value))
    if decimal_value < 0:
        msg = f"Quantity cannot be negative: {decimal_value}"
        raise ValueError(msg)
    return Quantity(decimal_value)


def create_timestamp(dt: datetime) -> Timestamp:
    """Create a Timestamp, ensuring it's UTC-aware."""
    if dt.tzinfo is None:
        msg = "Timestamp must be timezone-aware (UTC)"
        raise ValueError(msg)
    if dt.tzinfo != UTC or dt.utcoffset() != timedelta(0):
        msg = "Timestamp must use UTC timezone (tzinfo=UTC)"
        raise ValueError(msg)
    return Timestamp(dt)
