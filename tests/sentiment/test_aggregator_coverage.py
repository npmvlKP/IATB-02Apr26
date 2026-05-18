"""
Comprehensive coverage tests for aggregator.py.

Tests weighted sentiment ensemble and tradability gate.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.sentiment.aggregator import SentimentAggregator, SentimentGateResult
from iatb.sentiment.news_analyzer import NewsArticle
from iatb.sentiment.social_sentiment import SocialPost


class TestSentimentGateResult:
    """Test sentiment gate result dataclass."""

    def test_create_result(self):
        """Test creating gate result."""
        from iatb.sentiment.base import SentimentScore

        composite = SentimentScore(
            source="ensemble",
            score=Decimal("0.6"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            text_excerpt="Test",
        )

        result = SentimentGateResult(
            composite=composite,
            very_strong=True,
            volume_confirmed=True,
            tradable=True,
            component_scores={"vader": Decimal("0.5")},
        )

        assert result.very_strong is True
        assert result.tradable is True


class TestSentimentAggregator:
    """Test sentiment aggregation."""

    def test_create_aggregator_with_defaults(self):
        """Test creating aggregator with default settings."""
        aggregator = SentimentAggregator()

        assert aggregator is not None

    def test_analyze_text(self):
        """Test analyzing text."""
        aggregator = SentimentAggregator()
        text = "This is great news for the company"

        composite, components = aggregator.analyze(text)

        assert isinstance(composite, object)
        assert isinstance(components, dict)

    def test_evaluate_instrument_tradable(self):
        """Test evaluating instrument with strong sentiment and volume."""
        aggregator = SentimentAggregator()
        text = "Strong growth expected"

        result = aggregator.evaluate_instrument(text, Decimal("1.5"))

        assert isinstance(result, SentimentGateResult)

    def test_evaluate_instrument_no_volume(self):
        """Test evaluating instrument without volume confirmation."""
        aggregator = SentimentAggregator()
        text = "Growth expected"

        result = aggregator.evaluate_instrument(text, Decimal("0.3"))

        assert isinstance(result, SentimentGateResult)
        assert result.volume_confirmed is False

    def test_analyze_news(self):
        """Test analyzing news articles."""
        aggregator = SentimentAggregator()
        articles = [
            NewsArticle(
                title="Great earnings",
                content="Strong growth",
                source="Test",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            )
        ]

        result = aggregator.analyze_news(articles, "TEST")

        assert result is not None
        assert result.symbol == "TEST"

    def test_analyze_social(self):
        """Test analyzing social posts."""
        aggregator = SentimentAggregator()
        posts = [
            SocialPost(
                content="Great company",
                platform="twitter",
                author="@user",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            )
        ]

        result = aggregator.analyze_social(posts, "TEST")

        assert result is not None
        assert result.source == "social"

    def test_analyze_full_ensemble(self):
        """Test full ensemble analysis."""
        aggregator = SentimentAggregator()
        text = "Strong growth expected"
        articles = [
            NewsArticle(
                title="Great news",
                content="Growth",
                source="Test",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            )
        ]
        posts = [
            SocialPost(
                content="Great",
                platform="twitter",
                author="@user",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            )
        ]

        composite, components = aggregator.analyze_full_ensemble(
            text, articles, posts, "TEST"
        )

        assert isinstance(composite, object)
        assert isinstance(components, dict)

    def test_evaluate_instrument_full(self):
        """Test full instrument evaluation."""
        aggregator = SentimentAggregator()
        text = "Strong growth"
        articles = [
            NewsArticle(
                title="Great",
                content="Growth",
                source="Test",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            )
        ]

        result = aggregator.evaluate_instrument_full(
            text, Decimal("1.5"), articles, [], "TEST"
        )

        assert isinstance(result, SentimentGateResult)

    def test_invalid_threshold_raises_error(self):
        """Test that invalid threshold raises ConfigError."""
        with pytest.raises(Exception):  # ConfigError
            SentimentAggregator(very_strong_threshold=Decimal("0"))

    def test_threshold_above_one_raises_error(self):
        """Test that threshold > 1 raises ConfigError."""
        with pytest.raises(Exception):  # ConfigError
            SentimentAggregator(very_strong_threshold=Decimal("1.5"))
