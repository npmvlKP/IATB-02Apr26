"""
Temporal decay for signal freshness weighting.
"""

import math
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.selection._util import clamp_01

_DECAY_RATES: dict[str, Decimal] = {
    "sentiment": Decimal("0.25"),
    "strength": Decimal("0.10"),
    "volume_profile": Decimal("0.15"),
    "drl": Decimal("0.05"),
}

_SECONDS_PER_HOUR = Decimal("3600")


def temporal_decay(
    signal_timestamp: datetime,
    current_timestamp: datetime,
    signal_name: str,
    decay_overrides: dict[str, Decimal] | None = None,
) -> Decimal:
    """Compute exp(-lambda * hours_elapsed) decay factor in [0, 1]."""
    _validate_timestamps(signal_timestamp, current_timestamp)
    rate = _decay_rate_for(signal_name, decay_overrides)
    elapsed_seconds = Decimal(
        str((current_timestamp - signal_timestamp).total_seconds()),
    )
    if elapsed_seconds < Decimal("0"):
        msg = "signal_timestamp cannot be in the future"
        raise ConfigError(msg)
    hours_elapsed = elapsed_seconds / _SECONDS_PER_HOUR
    # API boundary: math.exp requires float; convert immediately to Decimal.
    exponent = -(rate * hours_elapsed)
    # Clamp exponent to avoid overflow in math.exp.
    clamped = max(Decimal("-500"), exponent)
    raw = Decimal(str(math.exp(float(clamped))))  # float required: math.exp API
    return clamp_01(raw)


def _validate_timestamps(signal: datetime, current: datetime) -> None:
    if signal.tzinfo != UTC:
        msg = "signal_timestamp must be UTC"
        raise ConfigError(msg)
    if current.tzinfo != UTC:
        msg = "current_timestamp must be UTC"
        raise ConfigError(msg)


def _decay_rate_for(
    signal_name: str,
    overrides: dict[str, Decimal] | None = None,
) -> Decimal:
    if overrides and signal_name in overrides:
        return overrides[signal_name]
    rate = _DECAY_RATES.get(signal_name)
    if rate is None:
        msg = f"unknown signal_name for decay: {signal_name!r}"
        raise ConfigError(msg)
    return rate
