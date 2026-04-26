"""Tests for selection.ic_monitor module."""

from __future__ import annotations

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.ic_monitor import (
    ICResult,
    _assign_ranks,
    _spearman_rank_correlation,
    _validate_sequences,
    check_alpha_decay,
    compute_information_coefficient,
)


def test_validate_sequences_mismatched() -> None:
    with pytest.raises(ConfigError, match="equal length"):
        _validate_sequences([Decimal("1")], [Decimal("1"), Decimal("2")])


def test_validate_sequences_too_few() -> None:
    with pytest.raises(ConfigError, match="at least 3"):
        _validate_sequences([Decimal("1"), Decimal("2")], [Decimal("1"), Decimal("2")])


def test_spearman_rank_correlation_perfect() -> None:
    xs = [Decimal("1"), Decimal("2"), Decimal("3")]
    ys = [Decimal("4"), Decimal("5"), Decimal("6")]
    result = _spearman_rank_correlation(xs, ys)
    assert result == Decimal("1")


def test_spearman_rank_correlation_anti() -> None:
    xs = [Decimal("1"), Decimal("2"), Decimal("3")]
    ys = [Decimal("6"), Decimal("5"), Decimal("4")]
    result = _spearman_rank_correlation(xs, ys)
    assert result == Decimal("-1")


def test_spearman_rank_correlation_clamped() -> None:
    xs = [Decimal("1"), Decimal("2"), Decimal("3")]
    ys = [Decimal("1"), Decimal("2"), Decimal("3")]
    result = _spearman_rank_correlation(xs, ys)
    assert Decimal("-1") <= result <= Decimal("1")


def test_assign_ranks_basic() -> None:
    result = _assign_ranks([Decimal("3"), Decimal("1"), Decimal("2")])
    assert result[0] == Decimal("3")
    assert result[1] == Decimal("1")
    assert result[2] == Decimal("2")


def test_assign_ranks_ties() -> None:
    result = _assign_ranks([Decimal("1"), Decimal("1"), Decimal("2")])
    assert result[0] == result[1]


def test_compute_ic_basic() -> None:
    scores = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
    returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4"), Decimal("0.5")]
    result = compute_information_coefficient(scores, returns)
    assert isinstance(result, ICResult)
    assert result.sample_size == 5


def test_check_alpha_decay_below_threshold() -> None:
    scores = [Decimal("1"), Decimal("2"), Decimal("3")]
    returns = [Decimal("0.5"), Decimal("-0.5"), Decimal("0.1")]
    result = check_alpha_decay(scores, returns)
    assert result is True


def test_check_alpha_decay_above_threshold() -> None:
    scores = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
    returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4"), Decimal("0.5")]
    result = check_alpha_decay(scores, returns)
    assert result is False
