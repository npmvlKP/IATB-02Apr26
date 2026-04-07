"""
Walk-forward validation of the composite selector.

Splits historical composite scores + forward returns into
train/test windows and measures out-of-sample IC stability.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.selection.ic_monitor import compute_information_coefficient

logger = logging.getLogger(__name__)

_DEFAULT_N_FOLDS = 5
_IC_THRESHOLD = Decimal("0.03")


@dataclass(frozen=True)
class SelectorValidationResult:
    fold_ics: list[Decimal]
    mean_ic: Decimal
    stable: bool
    folds: int


def validate_selector(
    composite_scores: Sequence[Decimal],
    forward_returns: Sequence[Decimal],
    n_folds: int = _DEFAULT_N_FOLDS,
) -> SelectorValidationResult:
    """Walk-forward IC measurement across time-series folds."""
    _validate_inputs(composite_scores, forward_returns, n_folds)
    scores = list(composite_scores)
    returns = list(forward_returns)
    chunk = len(scores) // (n_folds + 1)
    fold_ics: list[Decimal] = []
    for fold in range(1, n_folds + 1):
        train_end = chunk * fold
        test_end = len(scores) if fold == n_folds else chunk * (fold + 1)
        test_scores = scores[train_end:test_end]
        test_returns = returns[train_end:test_end]
        if len(test_scores) < 3:
            continue
        ic = compute_information_coefficient(test_scores, test_returns)
        fold_ics.append(ic.ic)
    mean_ic = _safe_mean(fold_ics)
    stable = all(ic >= _IC_THRESHOLD for ic in fold_ics) if fold_ics else False
    if not stable:
        logger.warning(
            "Selector validation: unstable IC (mean=%.4f, folds=%d)",
            mean_ic,
            len(fold_ics),
        )
    return SelectorValidationResult(
        fold_ics=fold_ics,
        mean_ic=mean_ic,
        stable=stable,
        folds=len(fold_ics),
    )


def _validate_inputs(
    scores: Sequence[Decimal],
    returns: Sequence[Decimal],
    n_folds: int,
) -> None:
    if len(scores) != len(returns):
        msg = "scores and returns must have equal length"
        raise ConfigError(msg)
    if n_folds < 2:
        msg = "n_folds must be >= 2"
        raise ConfigError(msg)
    min_len = (n_folds + 1) * 3
    if len(scores) < min_len:
        msg = f"need at least {min_len} observations for {n_folds} folds"
        raise ConfigError(msg)


def _safe_mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))
