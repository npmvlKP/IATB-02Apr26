"""
Comprehensive coverage tests for recency_weighting.py.

Tests per-article recency weighting for sentiment aggregation.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.recency_weighting import recency_weighted_score


class TestRecencyWeightedScore:
    """Test recency-weighted score calculation."""

    def test_weighted_score_single_article(self):
        """Test weighted score with single article."""
        now = datetime.now(UTC)
        article_scores = [(Decimal("0.5"), now)]

        result = recency_weighted_score(article_scores, now)

        assert result == Decimal("0.5")

    def test_weighted_score_multiple_articles(self):
        """Test weighted score with multiple articles."""
        now = datetime.now(UTC)
        article_scores = [
            (Decimal("0.8"), now),
            (Decimal("0.4"), now - timedelta(hours=1)),
            (Decimal("0.2"), now - timedelta(hours=2)),
        ]

        result = recency_weighted_score(article_scores, now)

        # Recent articles should have more weight
        assert result > Decimal("0.4")
        assert result < Decimal("0.8")

    def test_weighted_score_very_recent_article(self):
        """Test that very recent articles have high weight."""
        now = datetime.now(UTC)
        article_scores = [
            (Decimal("0.9"), now - timedelta(minutes=10)),
            (Decimal("0.1"), now - timedelta(hours=3)),
        ]

        result = recency_weighted_score(article_scores, now)

        assert result > Decimal("0.7")

    def test_weighted_score_old_articles_low_weight(self):
        """Test that old articles have low weight."""
        now = datetime.now(UTC)
        article_scores = [
            (Decimal("0.9"), now - timedelta(hours=10)),
            (Decimal("0.1"), now - timedelta(hours=12)),
        ]

        result = recency_weighted_score(article_scores, now)

        # Result should be weighted toward higher score but reduced by recency
        assert result >= Decimal("0.1")
        assert result <= Decimal("0.9")

    def test_empty_scores_raises_error(self):
        """Test that empty scores list raises ConfigError."""
        with pytest.raises(ConfigError, match="article_scores cannot be empty"):
            recency_weighted_score([], datetime.now(UTC))

    def test_non_utc_current_raises_error(self):
        """Test that non-UTC current time raises ConfigError."""
        now = datetime.now()  # Naive datetime
        article_scores = [(Decimal("0.5"), datetime.now(UTC))]

        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            recency_weighted_score(article_scores, now)

    def test_non_utc_article_raises_error(self):
        """Test that non-UTC article timestamp raises ConfigError."""
        now = datetime.now(UTC)
        article_scores = [(Decimal("0.5"), datetime.now())]

        with pytest.raises(ConfigError, match="article timestamp must be UTC"):
            recency_weighted_score(article_scores, now)

    def test_future_article_zero_weight(self):
        """Test that future articles have zero weight."""
        now = datetime.now(UTC)
        article_scores = [
            (Decimal("1.0"), now + timedelta(hours=1)),
            (Decimal("0.5"), now),
        ]

        result = recency_weighted_score(article_scores, now)

        assert result < Decimal("0.6")

    def test_weighted_score_negative_sentiment(self):
        """Test weighted score with negative sentiment."""
        now = datetime.now(UTC)
        article_scores = [
            (Decimal("-0.8"), now),
            (Decimal("-0.4"), now - timedelta(hours=1)),
        ]

        result = recency_weighted_score(article_scores, now)

        assert result < Decimal("-0.4")
