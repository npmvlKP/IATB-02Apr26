"""
Comprehensive coverage tests for ic_monitor.py.

Tests information coefficient computation and alpha decay detection.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.ic_monitor import (
    ICResult,
    check_alpha_decay,
    compute_information_coefficient,
)


class TestComputeInformationCoefficient:
    """Test IC computation."""

    def test_compute_ic_positive_correlation(self):
        """Test IC computation with positive correlation."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 11)]

        result = compute_information_coefficient(scores, returns)

        assert isinstance(result, ICResult)
        assert result.ic > Decimal("0")
        assert result.ic <= Decimal("1")
        assert result.sample_size == 10

    def test_compute_ic_negative_correlation(self):
        """Test IC computation with negative correlation."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(-i * 0.5)) for i in range(1, 11)]

        result = compute_information_coefficient(scores, returns)

        assert result.ic < Decimal("0")
        assert result.ic >= Decimal("-1")
        assert result.above_threshold is False

    def test_compute_ic_perfect_correlation(self):
        """Test IC computation with perfect correlation."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i)) for i in range(1, 11)]

        result = compute_information_coefficient(scores, returns)

        assert result.ic == Decimal("1")
        assert result.above_threshold is True

    def test_compute_ic_insufficient_samples(self):
        """Test that insufficient samples raise ConfigError."""
        scores = [Decimal("0.5"), Decimal("0.6")]
        returns = [Decimal("0.1"), Decimal("0.2")]

        with pytest.raises(ConfigError, match="at least 3 observations required"):
            compute_information_coefficient(scores, returns)

    def test_compute_ic_mismatched_lengths(self):
        """Test that mismatched lengths raise ConfigError."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 6)]  # Different length

        with pytest.raises(ConfigError, match="must have equal length"):
            compute_information_coefficient(scores, returns)

    def test_compute_ic_returns_correct_result_structure(self):
        """Test that IC result has correct structure."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 11)]

        result = compute_information_coefficient(scores, returns)

        assert hasattr(result, "ic")
        assert hasattr(result, "sample_size")
        assert hasattr(result, "above_threshold")
        assert hasattr(result, "threshold")
        assert result.threshold == Decimal("0.03")

    def test_compute_ic_with_constant_values(self):
        """Test IC computation with constant values (ties)."""
        scores = [Decimal("0.5") for _ in range(10)]
        returns = [Decimal("0.1") for _ in range(10)]

        result = compute_information_coefficient(scores, returns)

        # When both are constant, they have perfect rank correlation (all ties)
        assert result.ic == Decimal("1")
        assert result.above_threshold is True

    def test_compute_ic_threshold_detection(self):
        """Test threshold detection for alpha decay."""
        # High IC
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i)) for i in range(1, 11)]
        result = compute_information_coefficient(scores, returns)
        assert result.above_threshold is True

        # Low IC (unrelated data)
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(10 - i)) for i in range(1, 11)]
        result = compute_information_coefficient(scores, returns)
        assert result.above_threshold is False


class TestCheckAlphaDecay:
    """Test alpha decay detection."""

    def test_alpha_decay_not_detected_high_ic(self):
        """Test that high IC returns False (no decay)."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i)) for i in range(1, 11)]

        decay_detected = check_alpha_decay(scores, returns)

        assert decay_detected is False

    def test_alpha_decay_detected_low_ic(self):
        """Test that low IC returns True (decay detected)."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(10 - i)) for i in range(1, 11)]

        decay_detected = check_alpha_decay(scores, returns)

        assert decay_detected is True

    def test_alpha_decay_custom_threshold(self):
        """Test alpha decay with custom threshold."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 11)]

        # Should not detect decay with high threshold
        decay_detected = check_alpha_decay(scores, returns, threshold=Decimal("1.5"))
        assert decay_detected is True

        # Should not detect decay with low threshold
        decay_detected = check_alpha_decay(scores, returns, threshold=Decimal("0.01"))
        assert decay_detected is False

    def test_alpha_decay_insufficient_samples(self):
        """Test that insufficient samples raise ConfigError."""
        scores = [Decimal("0.5"), Decimal("0.6")]
        returns = [Decimal("0.1"), Decimal("0.2")]

        with pytest.raises(ConfigError, match="at least 3 observations required"):
            check_alpha_decay(scores, returns)

    def test_alpha_decay_mismatched_lengths(self):
        """Test that mismatched lengths raise ConfigError."""
        scores = [Decimal(str(i)) for i in range(1, 11)]
        returns = [Decimal(str(i * 0.5)) for i in range(1, 6)]

        with pytest.raises(ConfigError, match="must have equal length"):
            check_alpha_decay(scores, returns)


class TestICResult:
    """Test ICResult dataclass."""

    def test_ic_result_creation(self):
        """Test creating ICResult."""
        result = ICResult(
            ic=Decimal("0.5"),
            sample_size=10,
            above_threshold=True,
            threshold=Decimal("0.03"),
        )

        assert result.ic == Decimal("0.5")
        assert result.sample_size == 10
        assert result.above_threshold is True
        assert result.threshold == Decimal("0.03")

    def test_ic_result_immutable(self):
        """Test that ICResult is frozen (immutable)."""
        result = ICResult(
            ic=Decimal("0.5"),
            sample_size=10,
            above_threshold=True,
            threshold=Decimal("0.03"),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            result.ic = Decimal("0.6")


class TestSpearmanRankCorrelation:
    """Test Spearman rank correlation implementation."""

    def test_rank_correlation_positive(self):
        """Test positive rank correlation."""
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        returns = [
            Decimal("2"),
            Decimal("4"),
            Decimal("6"),
            Decimal("8"),
            Decimal("10"),
        ]

        result = compute_information_coefficient(scores, returns)

        assert result.ic > Decimal("0.9")  # Should be very high

    def test_rank_correlation_negative(self):
        """Test negative rank correlation."""
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        returns = [
            Decimal("10"),
            Decimal("8"),
            Decimal("6"),
            Decimal("4"),
            Decimal("2"),
        ]

        result = compute_information_coefficient(scores, returns)

        assert result.ic < Decimal("-0.9")  # Should be very negative

    def test_rank_correlation_with_ties(self):
        """Test rank correlation with tied values."""
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores = [Decimal("1"), Decimal("1"), Decimal("3"), Decimal("4"), Decimal("5")]
        returns = [
            Decimal("2"),
            Decimal("2"),
            Decimal("6"),
            Decimal("8"),
            Decimal("10"),
        ]

        result = compute_information_coefficient(scores, returns)

        assert result.ic > Decimal("0")  # Should still be positive

    def test_rank_correlation_empty_lists(self):
        """Test rank correlation with empty lists."""
        from iatb.selection.ic_monitor import compute_information_coefficient

        scores: list[Decimal] = []
        returns: list[Decimal] = []

        with pytest.raises(ConfigError, match="at least 3 observations required"):
            compute_information_coefficient(scores, returns)
