"""
Shared utilities for the selection module.
"""

from decimal import Decimal
from enum import StrEnum


class DirectionalIntent(StrEnum):
    """Trade direction the selection pipeline is evaluating."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


def clamp_01(value: Decimal) -> Decimal:
    """Clamp a Decimal to [0, 1]."""
    return max(Decimal("0"), min(Decimal("1"), value))


_MIN_CONFIDENCE_GATE = Decimal("0.20")


def confidence_ramp(
    confidence: Decimal,
    threshold: Decimal = _MIN_CONFIDENCE_GATE,
) -> Decimal:
    """Soft ramp: 0 below threshold, linear to 1 above."""
    if confidence < threshold:
        return Decimal("0")
    ceiling = Decimal("1") - threshold
    if ceiling <= Decimal("0"):
        return Decimal("1")
    return clamp_01((confidence - threshold) / ceiling)


def rank_percentile(values: list[Decimal]) -> list[Decimal]:
    """Convert raw scores to rank-percentile [0, 1] across the list.

    Highest value → 1.0, lowest → 1/N.  Ties share the same rank.
    Returns the original list unchanged if it has fewer than 2 elements.
    """
    size = len(values)
    if size < 2:
        return [Decimal("1")] * size
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    result = [Decimal("0")] * size
    rank = 0
    divisor = Decimal(size - 1)
    for pos, (original_idx, _) in enumerate(indexed):
        if pos > 0 and indexed[pos][1] != indexed[pos - 1][1]:
            rank = pos
        result[original_idx] = Decimal(rank) / divisor
    return result
