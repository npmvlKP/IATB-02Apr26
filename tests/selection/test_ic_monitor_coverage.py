"""Tests for selection/ic_monitor.py — information coefficient tracking."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.ic_monitor import (
    ICResult,
    check_alpha_decay,
    compute_information_coefficient,
)


def _aligned_scores(n: int) -> tuple[list[Decimal], list[Decimal]]:
    scores = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
    returns = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
    return scores, returns


def _inverse_scores(n: int) -> tuple[list[Decimal], list[Decimal]]:
    scores = [Decimal(str(i)) / Decimal(str(n)) for i in range(n)]
    returns = [Decimal(str(n - 1 - i)) / Decimal(str(n)) for i in range(n)]
    return scores, returns


class TestComputeInformationCoefficient:
    def test_perfect_positive_correlation(self) -> None:
        scores, returns = _aligned_scores(10)
        result = compute_information_coefficient(scores, returns)
        assert isinstance(result, ICResult)
        assert result.ic > Decimal("0.9")
        assert result.sample_size == 10

    def test_perfect_negative_correlation(self) -> None:
        scores, returns = _inverse_scores(10)
        result = compute_information_coefficient(scores, returns)
        assert result.ic < Decimal("-0.9")

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            compute_information_coefficient(
                [Decimal("0.1"), Decimal("0.2")],
                [Decimal("0.3")],
            )

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least 3"):
            compute_information_coefficient(
                [Decimal("0.1"), Decimal("0.2")],
                [Decimal("0.1"), Decimal("0.2")],
            )

    def test_above_threshold_flag(self) -> None:
        scores, returns = _aligned_scores(10)
        result = compute_information_coefficient(scores, returns)
        assert result.above_threshold is True

    def test_below_threshold_flag(self) -> None:
        scores, returns = _inverse_scores(10)
        result = compute_information_coefficient(scores, returns)
        assert result.above_threshold is False

    def test_threshold_value(self) -> None:
        scores, returns = _aligned_scores(5)
        result = compute_information_coefficient(scores, returns)
        assert result.threshold == Decimal("0.03")

    def test_ic_bounded(self) -> None:
        scores = [Decimal("1"), Decimal("2"), Decimal("3")]
        returns = [Decimal("10"), Decimal("20"), Decimal("30")]
        result = compute_information_coefficient(scores, returns)
        assert Decimal("-1") <= result.ic <= Decimal("1")

    def test_identical_values(self) -> None:
        scores = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]
        returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
        result = compute_information_coefficient(scores, returns)
        assert Decimal("-1") <= result.ic <= Decimal("1")


class TestCheckAlphaDecay:
    def test_no_decay_with_correlation(self) -> None:
        scores, returns = _aligned_scores(10)
        decayed = check_alpha_decay(scores, returns)
        assert decayed is False

    def test_decay_with_inverse(self) -> None:
        scores, returns = _inverse_scores(10)
        decayed = check_alpha_decay(scores, returns)
        assert decayed is True

    def test_custom_threshold(self) -> None:
        scores, returns = _aligned_scores(5)
        decayed = check_alpha_decay(scores, returns, threshold=Decimal("1.5"))
        assert decayed is True
