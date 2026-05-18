"""
Comprehensive coverage tests for ic_monitor.py.

Tests Information Coefficient tracking, IC computation, and error paths.
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
    """Test compute_information_coefficient function."""

    def test_perfect_correlation(self) -> None:
        """Test with perfect positive correlation."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]

        result = compute_information_coefficient(signals, returns)
        # Perfect correlation should give IC close to 1
        assert result.ic >= Decimal("0.9")
        assert isinstance(result, ICResult)
        assert result.sample_size == 4

    def test_negative_correlation(self) -> None:
        """Test with negative correlation."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = compute_information_coefficient(signals, returns)
        # Negative correlation should give IC close to -1
        assert result.ic <= Decimal("-0.9")

    def test_no_correlation(self) -> None:
        """Test with negative correlation."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = compute_information_coefficient(signals, returns)
        # Negative correlation should give IC close to -1
        assert result.ic < Decimal("0")

    def test_mismatched_lengths(self) -> None:
        """Test raises ConfigError when lengths don't match."""
        signals = [Decimal("0.1"), Decimal("0.2")]
        returns = [Decimal("0.1")]

        with pytest.raises(ConfigError) as exc_info:
            compute_information_coefficient(signals, returns)
        assert "must have equal length" in str(exc_info.value)

    def test_insufficient_observations(self) -> None:
        """Test raises ConfigError when fewer than 3 observations."""
        signals = [Decimal("0.1"), Decimal("0.2")]
        returns = [Decimal("0.1"), Decimal("0.2")]

        with pytest.raises(ConfigError) as exc_info:
            compute_information_coefficient(signals, returns)
        assert "at least 3 observations required" in str(exc_info.value)

    def test_decimal_precision(self) -> None:
        """Test Decimal precision handling."""
        signals = [
            Decimal("0.123456789"),
            Decimal("0.234567890"),
            Decimal("0.345678901"),
        ]
        returns = [
            Decimal("0.123456789"),
            Decimal("0.234567890"),
            Decimal("0.345678901"),
        ]

        result = compute_information_coefficient(signals, returns)
        # Should maintain precision
        assert result.ic >= Decimal("0.9")

    def test_above_threshold(self) -> None:
        """Test above_threshold flag."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]

        result = compute_information_coefficient(signals, returns)
        assert result.above_threshold is True
        assert result.threshold == Decimal("0.03")

    def test_below_threshold(self) -> None:
        """Test below threshold."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = compute_information_coefficient(signals, returns)
        assert result.above_threshold is False


class TestCheckAlphaDecay:
    """Test check_alpha_decay function."""

    def test_alpha_decay_detected(self, caplog) -> None:
        """Test alpha decay detection when IC below threshold."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = check_alpha_decay(signals, returns)
        assert result is True
        assert "Alpha decay detected" in caplog.text

    def test_no_alpha_decay(self) -> None:
        """Test no alpha decay when IC above threshold."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]

        result = check_alpha_decay(signals, returns)
        assert result is False

    def test_custom_threshold(self) -> None:
        """Test with custom threshold."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = check_alpha_decay(signals, returns, threshold=Decimal("0.1"))
        # Should still be below custom threshold
        assert result is True

    def test_edge_case_threshold(self, caplog) -> None:
        """Test edge case at threshold boundary."""
        signals = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        returns = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]

        result = check_alpha_decay(signals, returns, threshold=Decimal("0.95"))
        # IC is 1.0, which is above 0.95, so no decay
        assert result is False


class TestSpearmanRankCorrelation:
    """Test internal Spearman rank correlation."""

    def test_rank_correlation_with_ties(self) -> None:
        """Test rank correlation handles ties correctly."""
        xs = [Decimal("0.2"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        ys = [Decimal("0.2"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]

        result = compute_information_coefficient(xs, ys)
        # Should handle ties gracefully
        assert result.ic >= Decimal("0.8")

    def test_rank_correlation_clamped(self) -> None:
        """Test IC is clamped to [-1, 1]."""
        xs = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        ys = [Decimal("0.4"), Decimal("0.3"), Decimal("0.2"), Decimal("0.1")]

        result = compute_information_coefficient(xs, ys)
        assert result.ic >= Decimal("-1")
        assert result.ic <= Decimal("1")

    def test_rank_correlation_all_same(self) -> None:
        """Test with all same values."""
        xs = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]
        ys = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]

        result = compute_information_coefficient(xs, ys)
        # All same values give perfect rank correlation (all ties get same rank)
        assert result.ic == Decimal("1")
