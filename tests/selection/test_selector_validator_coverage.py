"""
Comprehensive coverage tests for selector_validator.py.

Tests walk-forward validation of composite selector, input validation, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.selector_validator import (
    SelectorValidationResult,
    _safe_mean,
    _validate_inputs,
    validate_selector,
)


class TestValidateInputs:
    """Test _validate_inputs function."""

    def test_valid_inputs(self) -> None:
        """Test with valid inputs."""
        scores = [Decimal("0.5"), Decimal("0.6"), Decimal("0.7")] * 4
        returns = [Decimal("0.05"), Decimal("0.06"), Decimal("0.07")] * 4
        _validate_inputs(scores, returns, 3)

    def test_mismatched_lengths(self) -> None:
        """Test raises ConfigError when scores and returns lengths differ."""
        scores = [Decimal("0.5"), Decimal("0.6")]
        returns = [Decimal("0.05")]
        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(scores, returns, 2)
        assert "equal length" in str(exc_info.value)

    def test_n_folds_too_small(self) -> None:
        """Test raises ConfigError when n_folds < 2."""
        scores = [Decimal("0.5")] * 10
        returns = [Decimal("0.05")] * 10
        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(scores, returns, 1)
        assert "n_folds must be >= 2" in str(exc_info.value)

    def test_insufficient_observations(self) -> None:
        """Test raises ConfigError when not enough observations for folds."""
        scores = [Decimal("0.5")] * 5
        returns = [Decimal("0.05")] * 5
        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(scores, returns, 5)
        assert "observations" in str(exc_info.value)


class TestValidateSelector:
    """Test validate_selector function."""

    def test_stable_selector(self) -> None:
        """Test with stable IC across folds."""
        scores = [
            Decimal("0.8"),
            Decimal("0.7"),
            Decimal("0.9"),
            Decimal("0.8"),
            Decimal("0.85"),
        ] * 3
        returns = [
            Decimal("0.05"),
            Decimal("0.04"),
            Decimal("0.06"),
            Decimal("0.05"),
            Decimal("0.05"),
        ] * 3
        result = validate_selector(scores, returns, n_folds=2)
        assert isinstance(result, SelectorValidationResult)
        assert result.folds == len(result.fold_ics)
        assert result.mean_ic >= Decimal("0")

    def test_unstable_selector(self) -> None:
        """Test detection of unstable IC."""
        scores = [
            Decimal("0.1"),
            Decimal("0.9"),
            Decimal("0.2"),
            Decimal("0.8"),
            Decimal("0.3"),
        ] * 3
        returns = [
            Decimal("-0.05"),
            Decimal("0.1"),
            Decimal("-0.04"),
            Decimal("0.09"),
            Decimal("-0.03"),
        ] * 3
        result = validate_selector(scores, returns, n_folds=2)
        assert isinstance(result, SelectorValidationResult)

    def test_empty_input(self) -> None:
        """Test with empty input raises error."""
        with pytest.raises(ConfigError):
            validate_selector([], [], n_folds=2)

    def test_single_fold(self) -> None:
        """Test raises error for single fold."""
        scores = [Decimal("0.5")] * 10
        returns = [Decimal("0.05")] * 10
        with pytest.raises(ConfigError):
            validate_selector(scores, returns, n_folds=1)


class TestSafeMean:
    """Test _safe_mean function."""

    def test_mean_of_decimals(self) -> None:
        """Test mean calculation for decimals."""
        values = [Decimal("1"), Decimal("2"), Decimal("3")]
        result = _safe_mean(values)
        assert result == Decimal("2")

    def test_empty_list(self) -> None:
        """Test mean of empty list."""
        values: list[Decimal] = []
        result = _safe_mean(values)
        assert result == Decimal("0")

    def test_single_value(self) -> None:
        """Test mean of single value."""
        values = [Decimal("5")]
        result = _safe_mean(values)
        assert result == Decimal("5")

    def test_negative_values(self) -> None:
        """Test mean with negative values."""
        values = [Decimal("-1"), Decimal("-2"), Decimal("-3")]
        result = _safe_mean(values)
        assert result == Decimal("-2")


class TestSelectorValidationResult:
    """Test SelectorValidationResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a result object."""
        result = SelectorValidationResult(
            fold_ics=[Decimal("0.05"), Decimal("0.06")],
            mean_ic=Decimal("0.055"),
            stable=True,
            folds=2,
        )
        assert result.fold_ics == [Decimal("0.05"), Decimal("0.06")]
        assert result.mean_ic == Decimal("0.055")
        assert result.stable is True
        assert result.folds == 2

    def test_unstable_result(self) -> None:
        """Test unstable result."""
        result = SelectorValidationResult(
            fold_ics=[Decimal("0.01"), Decimal("0.02")],
            mean_ic=Decimal("0.015"),
            stable=False,
            folds=2,
        )
        assert result.stable is False
        assert result.mean_ic < Decimal("0.03")
