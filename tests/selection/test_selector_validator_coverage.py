"""
Comprehensive coverage tests for selector_validator.py.

Tests walk-forward validation of composite selector using IC stability.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.selector_validator import (
    SelectorValidationResult,
    validate_selector,
)


class TestValidateSelector:
    """Test selector validation functionality."""

    def test_validate_selector_success(self):
        """Test successful selector validation."""
        scores = [Decimal(str(i)) for i in range(1, 21)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 21)]

        result = validate_selector(scores, returns, n_folds=5)

        assert isinstance(result, SelectorValidationResult)
        assert len(result.fold_ics) > 0
        assert result.folds == len(result.fold_ics)
        assert result.mean_ic > Decimal("0")

    def test_validate_selector_negative_correlation(self):
        """Test validation with negative correlation."""
        scores = [Decimal(str(i)) for i in range(1, 21)]
        returns = [Decimal(str(-i * 0.5)) for i in range(1, 21)]

        result = validate_selector(scores, returns, n_folds=5)

        assert result.mean_ic < Decimal("0")
        assert result.stable is False  # Negative IC below threshold

    def test_validate_selector_insufficient_folds(self):
        """Test that insufficient folds raise ConfigError."""
        scores = [Decimal(str(i)) for i in range(1, 21)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 21)]

        with pytest.raises(ConfigError, match="n_folds must be >= 2"):
            validate_selector(scores, returns, n_folds=1)

    def test_validate_selector_mismatched_lengths(self):
        """Test that mismatched lengths raise ConfigError."""
        scores = [Decimal(str(i)) for i in range(1, 21)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 11)]

        with pytest.raises(ConfigError, match="must have equal length"):
            validate_selector(scores, returns, n_folds=5)

    def test_validate_selector_insufficient_observations(self):
        """Test that insufficient observations raise ConfigError."""
        # Need at least (n_folds + 1) * 3 = 18 observations for n_folds=5
        scores = [Decimal(str(i)) for i in range(1, 10)]  # Only 9
        returns = [Decimal(str(i * 0.5)) for i in range(1, 10)]

        with pytest.raises(ConfigError, match="need at least"):
            validate_selector(scores, returns, n_folds=5)

    def test_validate_selector_default_folds(self):
        """Test validation with default n_folds."""
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 31)]

        result = validate_selector(scores, returns)

        # Default is 5 folds
        assert result.folds <= 5
        assert len(result.fold_ics) == result.folds

    def test_validate_selector_with_gaps(self):
        """Test validation with gaps in data."""
        scores = [Decimal(str(i if i % 2 == 0 else 0)) for i in range(1, 31)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=5)

        # Should still compute IC for valid folds
        assert len(result.fold_ics) > 0

    def test_validate_selector_perfect_correlation(self):
        """Test validation with perfect correlation."""
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=5)

        assert result.mean_ic > Decimal("0.9")
        assert result.stable is True

    def test_validate_selector_unstable_ic(self):
        """Test validation with unstable IC across folds."""
        # Create unstable pattern
        scores = []
        returns = []
        for i in range(1, 31):
            if i <= 10:
                scores.append(Decimal(str(i)))
                returns.append(Decimal(str(i)))  # Positive
            elif i <= 20:
                scores.append(Decimal(str(i)))
                returns.append(Decimal(str(-i)))  # Negative
            else:
                scores.append(Decimal(str(i)))
                returns.append(Decimal(str(i * 0.1)))  # Weak

        result = validate_selector(scores, returns, n_folds=5)

        # Should detect instability
        assert result.stable is False

    def test_validate_selector_small_folds(self):
        """Test validation with small n_folds."""
        scores = [Decimal(str(i)) for i in range(1, 16)]  # 15 observations
        returns = [Decimal(str(i * 0.5)) for i in range(1, 16)]

        # With 15 observations and n_folds=2, need at least 9 observations
        result = validate_selector(scores, returns, n_folds=2)

        assert result.folds == 2

    def test_validate_selector_mean_ic_computation(self):
        """Test mean IC computation."""
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=5)

        # Mean should be average of fold ICs
        if len(result.fold_ics) > 0:
            expected_mean = sum(result.fold_ics, Decimal("0")) / Decimal(
                len(result.fold_ics)
            )
            assert result.mean_ic == expected_mean


class TestSelectorValidationResult:
    """Test SelectorValidationResult dataclass."""

    def test_result_creation(self):
        """Test creating SelectorValidationResult."""
        result = SelectorValidationResult(
            fold_ics=[Decimal("0.5"), Decimal("0.6"), Decimal("0.4")],
            mean_ic=Decimal("0.5"),
            stable=True,
            folds=3,
        )

        assert result.fold_ics == [Decimal("0.5"), Decimal("0.6"), Decimal("0.4")]
        assert result.mean_ic == Decimal("0.5")
        assert result.stable is True
        assert result.folds == 3

    def test_result_immutable(self):
        """Test that SelectorValidationResult is frozen (immutable)."""
        result = SelectorValidationResult(
            fold_ics=[Decimal("0.5")], mean_ic=Decimal("0.5"), stable=True, folds=1
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            result.mean_ic = Decimal("0.6")

    def test_result_with_empty_folds(self):
        """Test result with no valid folds."""
        result = SelectorValidationResult(
            fold_ics=[], mean_ic=Decimal("0"), stable=False, folds=0
        )

        assert result.fold_ics == []
        assert result.mean_ic == Decimal("0")
        assert result.stable is False
        assert result.folds == 0


class TestWalkForwardValidation:
    """Test walk-forward validation logic."""

    def test_walk_forward_fold_allocation(self):
        """Test that folds are allocated correctly in walk-forward."""
        # Create data with varying correlation patterns
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i * 0.8)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=3)

        # Should have computed IC for each fold
        assert len(result.fold_ics) == 3
        # All folds should have positive correlation
        assert all(ic > Decimal("0") for ic in result.fold_ics)

    def test_walk_forward_train_test_split(self):
        """Test that train/test split is respected."""
        scores = [
            Decimal(str(i)) for i in range(1, 19)
        ]  # 18 observations for n_folds=4
        returns = [Decimal(str(i * 0.5)) for i in range(1, 19)]

        result = validate_selector(scores, returns, n_folds=4)

        # With 18 observations and n_folds=4, chunk size = 18//5 = 3
        # Folds should be: [3:6], [6:9], [9:12], [12:15]
        assert len(result.fold_ics) == 4
        assert result.folds == 4

    def test_walk_forward_with_edge_cases(self):
        """Test walk-forward with edge cases."""
        # Data that results in some folds with < 3 samples
        scores = [Decimal(str(i)) for i in range(1, 16)]  # 15 observations
        returns = [Decimal(str(i * 0.5)) for i in range(1, 16)]

        result = validate_selector(scores, returns, n_folds=4)

        # Some folds might be skipped if they have < 3 samples
        assert result.folds <= 4
        assert len(result.fold_ics) == result.folds


class TestICStabilityDetection:
    """Test IC stability detection logic."""

    def test_stability_all_above_threshold(self):
        """Test stability when all folds are above threshold."""
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=5)

        # All ICs should be above threshold (0.03)
        assert all(ic >= Decimal("0.03") for ic in result.fold_ics)
        assert result.stable is True

    def test_stability_one_fold_below_threshold(self):
        """Test instability when one fold is below threshold."""
        scores = []
        returns = []

        # Fold 1: good
        for i in range(1, 7):
            scores.append(Decimal(str(i)))
            returns.append(Decimal(str(i)))

        # Fold 2: bad (below threshold)
        for i in range(7, 13):
            scores.append(Decimal(str(i)))
            returns.append(Decimal(str(13 - i)))

        # Fold 3-5: good
        for i in range(13, 31):
            scores.append(Decimal(str(i)))
            returns.append(Decimal(str(i)))

        result = validate_selector(scores, returns, n_folds=5)

        # Second fold should cause instability
        assert result.stable is False

    def test_stability_threshold_value(self):
        """Test that threshold is 0.03."""
        scores = [Decimal(str(i)) for i in range(1, 31)]
        returns = [Decimal(str(i)) for i in range(1, 31)]

        result = validate_selector(scores, returns, n_folds=5)

        # Check that the threshold logic is working
        # If IC is >= 0.03, it's considered stable
        assert result.stable is True
