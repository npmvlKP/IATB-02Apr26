"""Tests for selector_validator.py module."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.selector_validator import (
    SelectorValidationResult,
    validate_selector,
)


def test_validate_selector_basic() -> None:
    """Test validate_selector with basic valid inputs."""
    composite_scores = [
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.4"),
        Decimal("0.5"),
        Decimal("0.6"),
        Decimal("0.7"),
        Decimal("0.8"),
        Decimal("0.9"),
        Decimal("0.5"),
        Decimal("0.4"),
        Decimal("0.3"),
        Decimal("0.2"),
        Decimal("0.1"),
    ]
    forward_returns = [
        Decimal("0.01"),
        Decimal("0.02"),
        Decimal("0.03"),
        Decimal("0.04"),
        Decimal("0.05"),
        Decimal("0.06"),
        Decimal("0.07"),
        Decimal("0.08"),
        Decimal("0.09"),
        Decimal("0.05"),
        Decimal("0.04"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("0.01"),
    ]

    result = validate_selector(composite_scores, forward_returns, n_folds=3)

    assert isinstance(result, SelectorValidationResult)
    assert result.folds == 3
    assert len(result.fold_ics) == 3
    assert isinstance(result.mean_ic, Decimal)
    assert isinstance(result.stable, bool)


def test_validate_selector_with_high_correlation() -> None:
    """Test validate_selector with perfectly correlated data."""
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 16)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 16)]

    result = validate_selector(composite_scores, forward_returns, n_folds=3)

    # With perfect correlation, should be stable
    assert result.mean_ic > Decimal("0.9")
    assert result.stable is True


def test_validate_selector_with_mixed_correlation() -> None:
    """Test validate_selector with mixed correlation data."""
    composite_scores = [
        Decimal("0.9"),
        Decimal("0.7"),
        Decimal("0.5"),
        Decimal("0.3"),
        Decimal("0.1"),
        Decimal("0.8"),
        Decimal("0.6"),
        Decimal("0.4"),
        Decimal("0.2"),
        Decimal("0.0"),
        Decimal("0.9"),
        Decimal("0.7"),
        Decimal("0.5"),
        Decimal("0.3"),
        Decimal("0.1"),
    ]
    forward_returns = [
        Decimal("0.05"),
        Decimal("0.04"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("0.01"),
        Decimal("0.06"),
        Decimal("0.05"),
        Decimal("0.04"),
        Decimal("0.03"),
        Decimal("0.02"),
        Decimal("0.07"),
        Decimal("0.06"),
        Decimal("0.05"),
        Decimal("0.04"),
        Decimal("0.03"),
    ]

    result = validate_selector(composite_scores, forward_returns, n_folds=3)

    # Should complete successfully
    assert isinstance(result, SelectorValidationResult)
    assert result.folds == 3


def test_validate_selector_rejects_mismatched_lengths() -> None:
    """Test validate_selector raises ConfigError for mismatched lengths."""
    composite_scores = [Decimal("0.5")] * 10
    forward_returns = [Decimal("0.01")] * 8

    with pytest.raises(ConfigError, match="scores and returns must have equal length"):
        validate_selector(composite_scores, forward_returns)


def test_validate_selector_rejects_insufficient_folds() -> None:
    """Test validate_selector raises ConfigError for n_folds < 2."""
    composite_scores = [Decimal("0.5")] * 9
    forward_returns = [Decimal("0.01")] * 9

    with pytest.raises(ConfigError, match="n_folds must be >= 2"):
        validate_selector(composite_scores, forward_returns, n_folds=1)

    with pytest.raises(ConfigError, match="n_folds must be >= 2"):
        validate_selector(composite_scores, forward_returns, n_folds=0)


def test_validate_selector_rejects_insufficient_observations() -> None:
    """Test validate_selector raises ConfigError for insufficient observations."""
    # Need at least (n_folds + 1) * 3 = (3 + 1) * 3 = 12 observations
    composite_scores = [Decimal("0.5")] * 10
    forward_returns = [Decimal("0.01")] * 10

    with pytest.raises(ConfigError, match="need at least 12 observations"):
        validate_selector(composite_scores, forward_returns, n_folds=3)


def test_validate_selector_with_default_folds() -> None:
    """Test validate_selector uses default n_folds=5."""
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 19)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 19)]

    result = validate_selector(composite_scores, forward_returns)

    # Default is 5 folds
    assert result.folds == 5
    assert len(result.fold_ics) == 5


def test_validate_selector_frozen_dataclass() -> None:
    """Test SelectorValidationResult is frozen."""
    from dataclasses import FrozenInstanceError

    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 16)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 16)]

    result = validate_selector(composite_scores, forward_returns, n_folds=3)

    # Frozen dataclass raises FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        result.mean_ic = Decimal("0.9")


def test_validate_selector_with_negative_correlation() -> None:
    """Test validate_selector with negatively correlated data."""
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 16)]
    forward_returns = [Decimal(str(0.15 - i * 0.01)) for i in range(1, 16)]

    result = validate_selector(composite_scores, forward_returns, n_folds=3)

    # Negative correlation should result in negative IC
    assert result.mean_ic < Decimal("0")
    assert result.stable is False


def test_validate_selector_minimal_valid_input() -> None:
    """Test validate_selector with minimal valid input size."""
    # Minimum for n_folds=2 is (2+1)*3 = 9 observations
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 10)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 10)]

    result = validate_selector(composite_scores, forward_returns, n_folds=2)

    assert result.folds == 2
    assert len(result.fold_ics) == 2


def test_validate_selector_with_many_folds() -> None:
    """Test validate_selector handles many folds with sufficient data."""
    # Need at least (5+1)*3 = 18 observations for 5 folds
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 20)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 20)]

    result = validate_selector(composite_scores, forward_returns, n_folds=5)

    # Should complete with all folds
    assert isinstance(result, SelectorValidationResult)
    assert result.folds == 5


def test_validate_selector_skips_small_folds() -> None:
    """Test validate_selector skips folds with < 3 observations (line 47)."""
    # Create data where some folds will have < 3 observations
    # Need at least 12 observations for n_folds=2: (2+1)*3 = 9, but we want more
    composite_scores = [Decimal(str(i * 0.1)) for i in range(1, 13)]
    forward_returns = [Decimal(str(i * 0.01)) for i in range(1, 13)]

    result = validate_selector(composite_scores, forward_returns, n_folds=2)

    # Should skip small folds but still complete
    assert isinstance(result, SelectorValidationResult)
    assert result.mean_ic >= Decimal("0")


def test_safe_mean_empty_returns_zero() -> None:
    """Test _safe_mean returns 0 for empty list (line 85)."""
    from iatb.selection.selector_validator import _safe_mean

    result = _safe_mean([])
    assert result == Decimal("0")
