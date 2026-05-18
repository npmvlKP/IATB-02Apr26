"""
Comprehensive coverage tests for aggregator.py.

Tests weighted ensemble, sentiment aggregation, and error paths.
"""

from decimal import Decimal

from iatb.sentiment.aggregator import (
    SentimentAggregator,
    aggregate_sentiments,
)


class TestAggregateSentiments:
    """Test aggregate_sentiments function."""

    def test_aggregate_equal_weights(self) -> None:
        """Test aggregation with equal weights."""
        sentiments = [
            {"source": "news", "score": Decimal("0.6"), "weight": Decimal("0.5")},
            {"source": "social", "score": Decimal("0.8"), "weight": Decimal("0.5")},
        ]
        result = aggregate_sentiments(sentiments)
        # Should be average: (0.6 * 0.5) + (0.8 * 0.5) = 0.7
        assert result == Decimal("0.7")

    def test_aggregate_unequal_weights(self) -> None:
        """Test aggregation with unequal weights."""
        sentiments = [
            {"source": "news", "score": Decimal("0.6"), "weight": Decimal("0.7")},
            {"source": "social", "score": Decimal("0.8"), "weight": Decimal("0.3")},
        ]
        result = aggregate_sentiments(sentiments)
        # (0.6 * 0.7) + (0.8 * 0.3) = 0.42 + 0.24 = 0.66
        assert result == Decimal("0.66")

    def test_aggregate_empty_list(self) -> None:
        """Test aggregation with empty list."""
        sentiments: list[dict] = []
        result = aggregate_sentiments(sentiments)
        # Should return 0
        assert result == Decimal("0")

    def test_aggregate_single_sentiment(self) -> None:
        """Test aggregation with single sentiment."""
        sentiments = [
            {"source": "news", "score": Decimal("0.8"), "weight": Decimal("1.0")}
        ]
        result = aggregate_sentiments(sentiments)
        assert result == Decimal("0.8")

    def test_aggregate_negative_score(self) -> None:
        """Test aggregation with negative score."""
        sentiments = [
            {"source": "news", "score": Decimal("-0.5"), "weight": Decimal("0.5")},
            {"source": "social", "score": Decimal("0.5"), "weight": Decimal("0.5")},
        ]
        result = aggregate_sentiments(sentiments)
        # Should be 0
        assert result == Decimal("0")

    def test_aggregate_weights_sum_not_one(self) -> None:
        """Test aggregation when weights don't sum to 1."""
        sentiments = [
            {"source": "news", "score": Decimal("0.6"), "weight": Decimal("0.8")},
            {"source": "social", "score": Decimal("0.8"), "weight": Decimal("0.4")},
        ]
        result = aggregate_sentiments(sentiments)
        # Should still compute (might normalize or not)
        assert isinstance(result, Decimal)

    def test_aggregate_missing_score(self) -> None:
        """Test aggregation with missing score."""
        sentiments = [
            {"source": "news", "weight": Decimal("0.5")},  # Missing score
            {"source": "social", "score": Decimal("0.8"), "weight": Decimal("0.5")},
        ]
        result = aggregate_sentiments(sentiments)
        # Should handle gracefully
        assert isinstance(result, Decimal)


class TestSentimentAggregator:
    """Test SentimentAggregator class."""

    def test_aggregator_initialization(self) -> None:
        """Test aggregator initialization."""
        aggregator = SentimentAggregator()
        assert aggregator is not None

    def test_aggregator_add_sentiment(self) -> None:
        """Test adding sentiment."""
        aggregator = SentimentAggregator()
        aggregator.add_sentiment("news", Decimal("0.6"), Decimal("0.5"))
        assert len(aggregator.sentiments) == 1

    def test_aggregator_add_multiple_sentiments(self) -> None:
        """Test adding multiple sentiments."""
        aggregator = SentimentAggregator()
        aggregator.add_sentiment("news", Decimal("0.6"), Decimal("0.5"))
        aggregator.add_sentiment("social", Decimal("0.8"), Decimal("0.5"))
        assert len(aggregator.sentiments) == 2

    def test_aggregator_clear(self) -> None:
        """Test clearing sentiments."""
        aggregator = SentimentAggregator()
        aggregator.add_sentiment("news", Decimal("0.6"), Decimal("0.5"))
        aggregator.clear()
        assert len(aggregator.sentiments) == 0

    def test_aggregator_compute(self) -> None:
        """Test computing aggregated sentiment."""
        aggregator = SentimentAggregator()
        aggregator.add_sentiment("news", Decimal("0.6"), Decimal("0.5"))
        aggregator.add_sentiment("social", Decimal("0.8"), Decimal("0.5"))
        result = aggregator.compute()
        assert result == Decimal("0.7")

    def test_aggregator_compute_empty(self) -> None:
        """Test computing with no sentiments."""
        aggregator = SentimentAggregator()
        result = aggregator.compute()
        assert result == Decimal("0")

    def test_aggregator_with_recency_weighting(self) -> None:
        """Test aggregation with recency weighting."""
        aggregator = SentimentAggregator(use_recency_weighting=True)
        # Should initialize with recency weighting enabled
        assert aggregator.use_recency_weighting is True
