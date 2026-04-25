"""
Per-article recency weighting for sentiment aggregation.

Recent articles (< 30 min) carry 3x weight vs older articles (> 2h).
"""

import math
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.exceptions import ConfigError

_LAMBDA = Decimal("0.5")
_SECONDS_PER_HOUR = Decimal("3600")


def recency_weighted_score(
    article_scores: list[tuple[Decimal, datetime]],
    current_utc: datetime,
) -> Decimal:
    """Compute age-weighted average sentiment from (score, timestamp) pairs."""
    if not article_scores:
        msg = "article_scores cannot be empty"
        raise ConfigError(msg)
    if current_utc.tzinfo != UTC:
        msg = "current_utc must be UTC"
        raise ConfigError(msg)
    weighted_sum = Decimal("0")
    weight_sum = Decimal("0")
    for score, timestamp in article_scores:
        weight = _article_weight(timestamp, current_utc)
        weighted_sum += score * weight
        weight_sum += weight
    if weight_sum == Decimal("0"):
        return Decimal("0")
    return weighted_sum / weight_sum


def _article_weight(article_utc: datetime, current_utc: datetime) -> Decimal:
    if article_utc.tzinfo != UTC:
        msg = "article timestamp must be UTC"
        raise ConfigError(msg)
    elapsed = Decimal(
        str((current_utc - article_utc).total_seconds()),
    )
    if elapsed < Decimal("0"):
        return Decimal("0")
    hours = elapsed / _SECONDS_PER_HOUR
    # API boundary: math.exp requires float; convert to Decimal.
    exponent = -(_LAMBDA * hours)
    # Clamp exponent to avoid overflow in math.exp.
    clamped = max(Decimal("-500"), exponent)
    raw = Decimal(str(math.exp(float(clamped))))  # float required: math.exp API
    return max(Decimal("0"), min(Decimal("1"), raw))
