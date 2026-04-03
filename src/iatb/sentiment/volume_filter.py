"""
Volume confirmation gate for sentiment-driven trading.
"""

from decimal import Decimal

from iatb.core.exceptions import ConfigError

MIN_VOLUME_RATIO = Decimal("1.5")


def has_volume_confirmation(
    volume_ratio: Decimal,
    threshold: Decimal = MIN_VOLUME_RATIO,
) -> bool:
    """Return True when volume confirmation meets required ratio."""
    if threshold <= Decimal("0"):
        msg = "threshold must be positive"
        raise ConfigError(msg)
    if volume_ratio < Decimal("0"):
        msg = "volume_ratio cannot be negative"
        raise ConfigError(msg)
    return volume_ratio >= threshold
