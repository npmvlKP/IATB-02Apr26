"""
Stop-loss calculation utilities.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError


def atr_stop_price(
    entry_price: Decimal, atr: Decimal, side: OrderSide, multiple: Decimal = Decimal("2")
) -> Decimal:
    if entry_price <= Decimal("0") or atr <= Decimal("0") or multiple <= Decimal("0"):
        msg = "entry_price, atr, and multiple must be positive"
        raise ConfigError(msg)
    distance = atr * multiple
    if side == OrderSide.BUY:
        return max(Decimal("0"), entry_price - distance)
    return entry_price + distance


def trailing_stop_price(
    previous_stop: Decimal,
    current_price: Decimal,
    side: OrderSide,
    trail_fraction: Decimal = Decimal("0.01"),
) -> Decimal:
    if previous_stop <= Decimal("0") or current_price <= Decimal("0"):
        msg = "previous_stop and current_price must be positive"
        raise ConfigError(msg)
    if trail_fraction <= Decimal("0") or trail_fraction >= Decimal("1"):
        msg = "trail_fraction must be between 0 and 1"
        raise ConfigError(msg)
    distance = current_price * trail_fraction
    candidate = current_price - distance if side == OrderSide.BUY else current_price + distance
    return max(previous_stop, candidate) if side == OrderSide.BUY else min(previous_stop, candidate)


def should_time_exit(entry_time_utc: datetime, now_utc: datetime, max_hold_minutes: int) -> bool:
    if entry_time_utc.tzinfo != UTC or now_utc.tzinfo != UTC:
        msg = "entry_time_utc and now_utc must be timezone-aware UTC datetimes"
        raise ConfigError(msg)
    if max_hold_minutes <= 0:
        msg = "max_hold_minutes must be positive"
        raise ConfigError(msg)
    return now_utc - entry_time_utc >= timedelta(minutes=max_hold_minutes)
