"""
Comprehensive coverage tests for recency_weighting.py.

Tests time decay, recency weighting, and error paths.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.sentiment.recency_weighting import (
    apply_recency_weights,
    compute_recency_weight,
)


class TestComputeRecencyWeight:
    """Test compute_recency_weight function."""

    def test_recent_weight(self) -> None:
        """Test weight for recent timestamp."""
        now = datetime.now(UTC)
        weight = compute_recency_weight(now, hours=24)
        # Recent should have high weight
        assert weight > Decimal("0.9")

    def test_old_weight(self) -> None:
        """Test weight for old timestamp."""
        old_time = datetime.now(UTC) - timedelta(days=10)
        weight = compute_recency_weight(old_time, hours=24)
        # Old should have low weight
        assert weight < Decimal("0.2")

    def test_half_life_weight(self) -> None:
        """Test weight at half-life."""
        half_life = datetime.now(UTC) - timedelta(hours=12)
        weight = compute_recency_weight(half_life, hours=24)
        # Should be approximately 0.5
        assert Decimal("0.4") < weight < Decimal("0.6")

    def test_custom_decay_rate(self) -> None:
        """Test custom decay rate."""
        recent_time = datetime.now(UTC) - timedelta(hours=6)

        fast_decay = compute_recency_weight(recent_time, hours=12, decay=1.0)
        slow_decay = compute_recency_weight(recent_time, hours=12, decay=0.5)

        # Fast decay should have lower weight
        assert fast_decay < slow_decay

    def test_future_timestamp(self) -> None:
        """Test with future timestamp."""
        future_time = datetime.now(UTC) + timedelta(hours=1)
        weight = compute_recency_weight(future_time, hours=24)
        # Future should have weight of 1
        assert weight == Decimal("1")

    def test_zero_half_life(self) -> None:
        """Test with zero half-life."""
        now = datetime.now(UTC)
        weight = compute_recency_weight(now, hours=0)
        # Should handle gracefully
        assert isinstance(weight, Decimal)


class TestApplyRecencyWeights:
    """Test apply_recency_weights function."""

    def test_apply_weights_basic(self) -> None:
        """Test basic weight application."""
        sentiments = [
            {
                "timestamp": datetime.now(UTC) - timedelta(hours=1),
                "score": Decimal("0.5"),
            },
            {
                "timestamp": datetime.now(UTC) - timedelta(hours=12),
                "score": Decimal("0.5"),
            },
        ]
        result = apply_recency_weights(sentiments, hours=24)
        assert len(result) == 2
        # More recent should have higher weighted score
        assert result[0]["weighted_score"] > result[1]["weighted_score"]

    def test_apply_weights_empty_list(self) -> None:
        """Test with empty sentiment list."""
        sentiments: list[dict] = []
        result = apply_recency_weights(sentiments)
        assert result == []

    def test_apply_weights_single_item(self) -> None:
        """Test with single sentiment."""
        sentiments = [{"timestamp": datetime.now(UTC), "score": Decimal("0.5")}]
        result = apply_recency_weights(sentiments)
        assert len(result) == 1
        # Weight should be close to 1
        assert result[0]["weighted_score"] > Decimal("0.9")

    def test_apply_weights_missing_timestamp(self) -> None:
        """Test with missing timestamp."""
        sentiments = [
            {"score": Decimal("0.5")}  # Missing timestamp
        ]
        result = apply_recency_weights(sentiments)
        # Should handle gracefully
        assert len(result) == 1

    def test_apply_weights_custom_half_life(self) -> None:
        """Test with custom half-life."""
        sentiments = [
            {
                "timestamp": datetime.now(UTC) - timedelta(hours=6),
                "score": Decimal("0.5"),
            }
        ]
        result = apply_recency_weights(sentiments, hours=12)
        assert len(result) == 1
