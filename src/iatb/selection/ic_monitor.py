"""
Information Coefficient monitor for composite score validation.

Measures the rank correlation between composite selection scores
and realised forward returns to detect alpha decay.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

_DEFAULT_IC_THRESHOLD = Decimal("0.03")


@dataclass(frozen=True)
class ICResult:
    ic: Decimal
    sample_size: int
    above_threshold: bool
    threshold: Decimal


def compute_information_coefficient(
    composite_scores: Sequence[Decimal],
    forward_returns: Sequence[Decimal],
) -> ICResult:
    """Rank-correlation IC between selection scores and forward returns."""
    _validate_sequences(composite_scores, forward_returns)
    ic = _spearman_rank_correlation(
        list(composite_scores),
        list(forward_returns),
    )
    return ICResult(
        ic=ic,
        sample_size=len(composite_scores),
        above_threshold=ic >= _DEFAULT_IC_THRESHOLD,
        threshold=_DEFAULT_IC_THRESHOLD,
    )


def check_alpha_decay(
    composite_scores: Sequence[Decimal],
    forward_returns: Sequence[Decimal],
    threshold: Decimal = _DEFAULT_IC_THRESHOLD,
) -> bool:
    """Return True if IC is below threshold (alpha has decayed)."""
    result = compute_information_coefficient(composite_scores, forward_returns)
    if not result.above_threshold:
        logger.warning(
            "Alpha decay detected: IC=%.4f below threshold=%.4f (n=%d)",
            result.ic,
            threshold,
            result.sample_size,
        )
    return result.ic < threshold


def _validate_sequences(
    scores: Sequence[Decimal],
    returns: Sequence[Decimal],
) -> None:
    if len(scores) != len(returns):
        msg = "composite_scores and forward_returns must have equal length"
        raise ConfigError(msg)
    if len(scores) < 3:
        msg = "at least 3 observations required for IC computation"
        raise ConfigError(msg)


def _spearman_rank_correlation(
    xs: list[Decimal],
    ys: list[Decimal],
) -> Decimal:
    """Spearman rank correlation via rank differences."""
    n = len(xs)
    x_ranks = _assign_ranks(xs)
    y_ranks = _assign_ranks(ys)
    d_squared_sum = sum((x_ranks[i] - y_ranks[i]) ** 2 for i in range(n))
    n_dec = Decimal(n)
    denom = n_dec * (n_dec**2 - Decimal("1"))
    if denom == Decimal("0"):
        return Decimal("0")
    rho = Decimal("1") - (Decimal("6") * d_squared_sum) / denom
    return max(Decimal("-1"), min(Decimal("1"), rho))


def _assign_ranks(values: list[Decimal]) -> list[Decimal]:
    """Average-rank assignment for tie handling."""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [Decimal("0")] * len(values)
    pos = 0
    while pos < len(indexed):
        end = pos + 1
        while end < len(indexed) and indexed[end][1] == indexed[pos][1]:
            end += 1
        avg_rank = Decimal(pos + end + 1) / Decimal("2")
        for j in range(pos, end):
            ranks[indexed[j][0]] = avg_rank
        pos = end
    return ranks
