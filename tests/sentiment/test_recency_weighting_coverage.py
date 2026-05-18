"""
Comprehensive coverage tests for recency_weighting.py.

Tests time decay, recency weighting, and error paths.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.recency_weighting import (
    _article_weight,
    recency_weighted_score,
)


class TestArticleWeight:
    """Test _article_weight function."""

    def test_recent_weight(self) -> None:
        """Test weight for recent timestamp."""
        now = datetime.now(UTC)
        weight = _article_weight(now, now)
        # Recent should have weight of 1
        assert weight == Decimal("1")

    def test_old_weight(self) -> None:
        """Test weight for old timestamp."""
        old_time = datetime.now(UTC) - timedelta(days=10)
        now = datetime.now(UTC)
        weight = _article_weight(old_time, now)
        # Old should have low weight
        assert weight < Decimal("0.2")

    def test_half_life_weight(self) -> None:
        """Test weight after 2 hours (half-life with lambda=0.5)."""
        half_life_time = datetime.now(UTC) - timedelta(hours=2)
        now = datetime.now(UTC)
        weight = _article_weight(half_life_time, now)
        # Should be approximately 0.37 (e^-1.0 with lambda=0.5 and hours=2)
        assert Decimal("0.35") < weight < Decimal("0.40")

    def test_future_timestamp(self) -> None:
        """Test with future timestamp."""
        future_time = datetime.now(UTC) + timedelta(hours=1)
        now = datetime.now(UTC)
        weight = _article_weight(future_time, now)
        # Future should have weight of 0
        assert weight == Decimal("0")

    def test_weight_bounds(self) -> None:
        """Test weight is always in [0, 1]."""
        now = datetime.now(UTC)
        for days in range(0, 30, 5):
            past_time = now - timedelta(days=days)
            weight = _article_weight(past_time, now)
            assert Decimal("0") <= weight <= Decimal("1")

    def test_non_utc_article_timestamp(self) -> None:
        """Test with non-UTC article timestamp raises ConfigError."""
        now = datetime.now(UTC)
        non_utc_time = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        with pytest.raises(ConfigError, match="article timestamp must be UTC"):
            _article_weight(non_utc_time, now)

    def test_non_utc_current_timestamp_raises_type_error(self) -> None:
        """Test with non-UTC current timestamp raises TypeError (before ConfigError)."""
        article_time = datetime.now(UTC)
        non_utc_time = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        # This will raise TypeError due to naive/aware datetime subtraction
        # before it can check the UTC condition
        with pytest.raises(TypeError):
            _article_weight(article_time, non_utc_time)


class TestRecencyWeightedScore:
    """Test recency_weighted_score function."""

    def test_single_article(self) -> None:
        """Test with single article."""
        now = datetime.now(UTC)
        article_time = now - timedelta(hours=1)
        scores = [(Decimal("0.5"), article_time)]
        result = recency_weighted_score(scores, now)
        assert result == Decimal("0.5")

    def test_multiple_articles(self) -> None:
        """Test with multiple articles."""
        now = datetime.now(UTC)
        article1_time = now - timedelta(hours=1)
        article2_time = now - timedelta(hours=12)
        scores = [
            (Decimal("0.8"), article1_time),
            (Decimal("0.2"), article2_time),
        ]
        result = recency_weighted_score(scores, now)
        # Recent article should have higher weight
        assert result > Decimal("0.4")
        assert result < Decimal("0.8")

    def test_equal_scores_different_times(self) -> None:
        """Test with equal scores but different times."""
        now = datetime.now(UTC)
        recent_time = now - timedelta(hours=1)
        old_time = now - timedelta(hours=24)
        scores = [
            (Decimal("0.5"), recent_time),
            (Decimal("0.5"), old_time),
        ]
        result = recency_weighted_score(scores, now)
        # Should be weighted toward recent
        assert result > Decimal("0.25")

    def test_mixed_scores(self) -> None:
        """Test with mixed positive and negative scores."""
        now = datetime.now(UTC)
        article1_time = now - timedelta(hours=1)
        article2_time = now - timedelta(hours=1)
        scores = [
            (Decimal("0.8"), article1_time),
            (Decimal("-0.4"), article2_time),
        ]
        result = recency_weighted_score(scores, now)
        # Should be average: (0.8 - 0.4) / 2 = 0.2
        assert result == Decimal("0.2")

    def test_empty_scores_raises_error(self) -> None:
        """Test with empty scores raises ConfigError."""
        now = datetime.now(UTC)
        scores: list[tuple[Decimal, datetime]] = []
        with pytest.raises(ConfigError, match="article_scores cannot be empty"):
            recency_weighted_score(scores, now)

    def test_non_utc_current_timestamp_raises_error(self) -> None:
        """Test with non-UTC current timestamp raises ConfigError."""
        now = datetime.now(UTC)
        non_utc_time = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        scores = [(Decimal("0.5"), now)]
        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            recency_weighted_score(scores, non_utc_time)

    def test_non_utc_article_timestamp_in_list_raises_error(self) -> None:
        """Test with non-UTC article timestamp in list raises ConfigError."""
        now = datetime.now(UTC)
        non_utc_time = datetime(2024, 1, 1, 12, 0, 0)  # No timezone
        scores = [(Decimal("0.5"), non_utc_time)]
        with pytest.raises(ConfigError, match="article timestamp must be UTC"):
            recency_weighted_score(scores, now)

    def test_future_articles_only(self) -> None:
        """Test when all articles are in the future (weight=0)."""
        now = datetime.now(UTC)
        future_time = now + timedelta(hours=1)
        scores = [(Decimal("0.8"), future_time)]
        result = recency_weighted_score(scores, now)
        # All weights are 0, so result is 0
        assert result == Decimal("0")

    def test_boundary_values(self) -> None:
        """Test with boundary score values."""
        now = datetime.now(UTC)
        recent_time = now - timedelta(hours=1)
        scores = [
            (Decimal("1.0"), recent_time),
            (Decimal("-1.0"), recent_time),
        ]
        result = recency_weighted_score(scores, now)
        # Should be average: (1.0 - 1.0) / 2 = 0
        assert result == Decimal("0")

    def test_very_old_articles_mixed_with_recent(self) -> None:
        """Test with very old articles mixed with recent ones."""
        now = datetime.now(UTC)
        old_time = now - timedelta(days=100)
        recent_time = now - timedelta(hours=1)
        scores = [
            (Decimal("0.8"), recent_time),
            (Decimal("0.2"), old_time),
        ]
        result = recency_weighted_score(scores, now)
        # Recent article should dominate (old article weight near 0)
        assert result >= Decimal("0.6")
        assert result <= Decimal("0.8")
