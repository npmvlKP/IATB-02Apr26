"""Tests for selection/selector_validator.py — pre-selection validation."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.selector_validator import (
    SelectorValidationResult,
    _safe_mean,
    validate_selector,
)


def _aligned_data(n: int) -> tuple[list[Decimal], list[Decimal]]:
    scores = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
    returns = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
    return scores, returns


class TestValidateSelector:
    def test_valid_walk_forward(self) -> None:
        scores, returns = _aligned_data(30)
        result = validate_selector(scores, returns, n_folds=5)
        assert isinstance(result, SelectorValidationResult)
        assert result.folds > 0

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            validate_selector([Decimal("0.1")] * 10, [Decimal("0.1")] * 5, n_folds=2)

    def test_too_few_folds_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_folds must be >= 2"):
            validate_selector([Decimal("0.1")] * 10, [Decimal("0.1")] * 10, n_folds=1)

    def test_insufficient_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="need at least"):
            validate_selector([Decimal("0.1")] * 5, [Decimal("0.1")] * 5, n_folds=5)

    def test_stable_when_above_threshold(self) -> None:
        n = 40
        scores = [Decimal("1")] * n
        returns = [Decimal("1")] * n
        result = validate_selector(scores, returns, n_folds=5)
        assert result.stable is True

    def test_mean_ic_computed(self) -> None:
        scores, returns = _aligned_data(30)
        result = validate_selector(scores, returns, n_folds=5)
        assert isinstance(result.mean_ic, Decimal)

    def test_fold_ics_populated(self) -> None:
        scores, returns = _aligned_data(30)
        result = validate_selector(scores, returns, n_folds=5)
        assert len(result.fold_ics) > 0
        assert all(isinstance(ic, Decimal) for ic in result.fold_ics)

    def test_folds_count_matches(self) -> None:
        scores, returns = _aligned_data(30)
        result = validate_selector(scores, returns, n_folds=5)
        assert result.folds == len(result.fold_ics)

    def test_unstable_with_inverse(self) -> None:
        n = 30
        scores = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
        returns = [Decimal(str(n - 1 - i)) / Decimal(str(n)) for i in range(n)]
        result = validate_selector(scores, returns, n_folds=5)
        assert result.stable is False


class TestSafeMean:
    def test_empty_list(self) -> None:
        assert _safe_mean([]) == Decimal("0")

    def test_single_value(self) -> None:
        assert _safe_mean([Decimal("5")]) == Decimal("5")

    def test_multiple_values(self) -> None:
        result = _safe_mean([Decimal("1"), Decimal("2"), Decimal("3")])
        assert result == Decimal("2")
