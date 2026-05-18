"""
Comprehensive coverage tests for multi_factor_scorer.py.

Tests factor scoring, weighted combination, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.selection.multi_factor_scorer import (
    compute_multi_factor_score,
    normalize_scores,
    weigh_factors,
)


class TestNormalizeScores:
    """Test normalize_scores function."""

    def test_normalize_positive_scores(self) -> None:
        """Test normalization of positive scores."""
        scores = [Decimal("0.5"), Decimal("0.75"), Decimal("1.0")]
        result = normalize_scores(scores)
        assert len(result) == 3
        assert result[0] < result[1] < result[2]
        assert result[-1] == Decimal("1")

    def test_normalize_negative_scores(self) -> None:
        """Test normalization of negative scores."""
        scores = [Decimal("-0.5"), Decimal("-0.25"), Decimal("0.0")]
        result = normalize_scores(scores)
        assert len(result) == 3
        assert result[0] < result[1] < result[2]

    def test_normalize_mixed_scores(self) -> None:
        """Test normalization of mixed positive/negative scores."""
        scores = [Decimal("-0.5"), Decimal("0.0"), Decimal("0.5")]
        result = normalize_scores(scores)
        assert len(result) == 3
        assert result[-1] == Decimal("1")

    def test_normalize_empty_list(self) -> None:
        """Test normalization of empty list."""
        scores: list[Decimal] = []
        result = normalize_scores(scores)
        assert result == []

    def test_normalize_constant_scores(self) -> None:
        """Test normalization of constant scores."""
        scores = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]
        result = normalize_scores(scores)
        # All should be equal
        assert all(s == result[0] for s in result)

    def test_normalize_single_score(self) -> None:
        """Test normalization of single score."""
        scores = [Decimal("0.5")]
        result = normalize_scores(scores)
        assert len(result) == 1
        assert result[0] == Decimal("1")


class TestWeighFactors:
    """Test weigh_factors function."""

    def test_equal_weights(self) -> None:
        """Test with equal weights."""
        factor_scores = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.6"),
            "volume_profile": Decimal("0.7"),
        }
        weights = {
            "sentiment": Decimal("0.33"),
            "strength": Decimal("0.33"),
            "volume_profile": Decimal("0.34"),
        }
        result = weigh_factors(factor_scores, weights)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_dominant_weight(self) -> None:
        """Test with one dominant weight."""
        factor_scores = {
            "sentiment": Decimal("0.9"),
            "strength": Decimal("0.1"),
            "volume_profile": Decimal("0.1"),
        }
        weights = {
            "sentiment": Decimal("0.8"),
            "strength": Decimal("0.1"),
            "volume_profile": Decimal("0.1"),
        }
        result = weigh_factors(factor_scores, weights)
        assert result > Decimal("0.7")

    def test_missing_factor_score(self) -> None:
        """Test with missing factor score."""
        factor_scores = {
            "sentiment": Decimal("0.5"),
            # Missing strength
            "volume_profile": Decimal("0.7"),
        }
        weights = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.25"),
            "volume_profile": Decimal("0.25"),
        }
        result = weigh_factors(factor_scores, weights)
        # Should handle missing gracefully
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_invalid_weight_sum(self) -> None:
        """Test with weights that don't sum to 1."""
        factor_scores = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.6"),
        }
        weights = {
            "sentiment": Decimal("0.8"),
            "strength": Decimal("0.4"),  # Sum = 1.2
        }
        result = weigh_factors(factor_scores, weights)
        # Should still compute but may not be accurate
        assert isinstance(result, Decimal)

    def test_negative_weights(self) -> None:
        """Test with negative weights."""
        factor_scores = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.6"),
        }
        weights = {
            "sentiment": Decimal("-0.2"),
            "strength": Decimal("1.2"),
        }
        result = weigh_factors(factor_scores, weights)
        # Should handle negative weights
        assert isinstance(result, Decimal)


class TestComputeMultiFactorScore:
    """Test compute_multi_factor_score function."""

    def test_basic_scoring(self) -> None:
        """Test basic multi-factor scoring."""
        factor_data = [
            {
                "symbol": "STOCK1",
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.7"),
                "drl": Decimal("0.8"),
            },
            {
                "symbol": "STOCK2",
                "sentiment": Decimal("0.3"),
                "strength": Decimal("0.4"),
                "volume_profile": Decimal("0.5"),
                "drl": Decimal("0.6"),
            },
        ]
        weights = {
            "sentiment": Decimal("0.25"),
            "strength": Decimal("0.25"),
            "volume_profile": Decimal("0.25"),
            "drl": Decimal("0.25"),
        }
        result = compute_multi_factor_score(factor_data, weights)
        assert len(result) == 2
        assert "STOCK1" in result
        assert "STOCK2" in result
        # STOCK1 should have higher score
        assert result["STOCK1"] > result["STOCK2"]

    def test_with_normalization(self) -> None:
        """Test scoring with normalization."""
        factor_data = [
            {
                "symbol": f"STOCK{i}",
                "sentiment": Decimal(str(0.1 * i)),
                "strength": Decimal(str(0.1 * i)),
                "volume_profile": Decimal(str(0.1 * i)),
                "drl": Decimal(str(0.1 * i)),
            }
            for i in range(1, 6)
        ]
        weights = {
            "sentiment": Decimal("0.25"),
            "strength": Decimal("0.25"),
            "volume_profile": Decimal("0.25"),
            "drl": Decimal("0.25"),
        }
        result = compute_multi_factor_score(factor_data, weights, normalize=True)
        assert len(result) == 5
        # Highest score should be close to 1
        assert max(result.values()) == Decimal("1")

    def test_empty_factor_data(self) -> None:
        """Test with empty factor data."""
        factor_data: list[dict] = []
        weights = {
            "sentiment": Decimal("0.25"),
            "strength": Decimal("0.25"),
            "volume_profile": Decimal("0.25"),
            "drl": Decimal("0.25"),
        }
        result = compute_multi_factor_score(factor_data, weights)
        assert result == {}

    def test_incomplete_factor_data(self) -> None:
        """Test with incomplete factor data."""
        factor_data = [
            {
                "symbol": "STOCK1",
                "sentiment": Decimal("0.5"),
                # Missing other factors
            },
        ]
        weights = {
            "sentiment": Decimal("0.25"),
            "strength": Decimal("0.25"),
            "volume_profile": Decimal("0.25"),
            "drl": Decimal("0.25"),
        }
        result = compute_multi_factor_score(factor_data, weights)
        assert "STOCK1" in result
        # Should still compute with available factors
        assert Decimal("0.0") <= result["STOCK1"] <= Decimal("1.0")

    def test_missing_symbol(self) -> None:
        """Test with missing symbol field."""
        factor_data = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
            },
        ]
        weights = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.5"),
        }
        with pytest.raises(KeyError):
            compute_multi_factor_score(factor_data, weights)

    def test_zero_weights(self) -> None:
        """Test with all zero weights."""
        factor_data = [
            {
                "symbol": "STOCK1",
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
            },
        ]
        weights = {
            "sentiment": Decimal("0.0"),
            "strength": Decimal("0.0"),
        }
        result = compute_multi_factor_score(factor_data, weights)
        assert result["STOCK1"] == Decimal("0")
