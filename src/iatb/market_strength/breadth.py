"""
Breadth indicators used in market strength scoring.
"""

from collections.abc import Sequence
from decimal import Decimal

from iatb.core.exceptions import ConfigError


def advance_decline_ratio(advancers: int, decliners: int) -> Decimal:
    """Advance/decline breadth ratio."""
    if advancers < 0 or decliners < 0:
        msg = "advancers and decliners cannot be negative"
        raise ConfigError(msg)
    if decliners == 0:
        msg = "decliners cannot be zero"
        raise ConfigError(msg)
    return Decimal(advancers) / Decimal(decliners)


def up_down_volume_ratio(up_volume: Decimal, down_volume: Decimal) -> Decimal:
    """Up-volume to down-volume ratio."""
    if up_volume < Decimal("0") or down_volume < Decimal("0"):
        msg = "volume inputs cannot be negative"
        raise ConfigError(msg)
    if down_volume == Decimal("0"):
        msg = "down_volume cannot be zero"
        raise ConfigError(msg)
    return up_volume / down_volume


def mcclellan_oscillator(
    advances: Sequence[int],
    declines: Sequence[int],
    *,
    short_period: int = 19,
    long_period: int = 39,
) -> Decimal:
    """McClellan oscillator = EMA(net advances, short) - EMA(net advances, long)."""
    if not advances or not declines:
        msg = "advances and declines cannot be empty"
        raise ConfigError(msg)
    if len(advances) != len(declines):
        msg = "advances and declines must have equal length"
        raise ConfigError(msg)
    if short_period <= 0 or long_period <= 0 or short_period >= long_period:
        msg = "periods must be positive and short_period < long_period"
        raise ConfigError(msg)
    net_series = [Decimal(adv) - Decimal(dec) for adv, dec in zip(advances, declines, strict=True)]
    return _ema(net_series, short_period) - _ema(net_series, long_period)


def _ema(values: Sequence[Decimal], period: int) -> Decimal:
    if not values:
        msg = "values cannot be empty"
        raise ConfigError(msg)
    multiplier = Decimal("2") / (Decimal(period) + Decimal("1"))
    current = values[0]
    for value in values[1:]:
        current = ((value - current) * multiplier) + current
    return current
