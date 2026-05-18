"""
Comprehensive coverage tests for news_analyzer.py.

Tests news sentiment analyzer for financial instruments.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.sentiment.news_analyzer import (
    MockNewsSource,
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
    NewsSentimentResult,
)


class TestNewsArticle:
    """Test news article dataclass."""

    def test_create_article(self):
        """Test creating news article."""
        article = NewsArticle(
            title="Test Title",
            content="Test content",
            source="Test Source",
            published_at=datetime.now(UTC),
            url="https://example.com",
            symbols=["TEST"],
        )

        assert article.title == "Test Title"
        assert article.symbols == ["TEST"]


class TestNewsAnalyzerConfig:
    """Test news analyzer configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = NewsAnalyzerConfig()
        assert config.min_relevance == Decimal("0.5")
        assert config.max_age_hours == 24

    def test_custom_config(self):
        """Test custom configuration values."""
        config = NewsAnalyzerConfig(
            min_relevance=Decimal("0.7"),
            max_age_hours=12,
        )
        assert config.min_relevance == Decimal("0.7")

    def test_invalid_relevance_raises_error(self):
        """Test that invalid relevance raises ConfigError."""
        with pytest.raises(Exception):  # ConfigError
            NewsAnalyzerConfig(min_relevance=Decimal("1.5"))

    def test_negative_max_age_raises_error(self):
        """Test that negative max_age_hours raises ConfigError."""
        with pytest.raises(Exception):  # ConfigError
            NewsAnalyzerConfig(max_age_hours=-1)


class TestNewsAnalyzer:
    """Test news sentiment analyzer."""

    def test_analyze_single_article(self):
        """Test analyzing single article."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Great earnings report",
            content="Company reports strong growth and profit",
            source="Test Source",
            published_at=datetime.now(UTC),
            symbols=["TEST"],
        )

        result = analyzer.analyze([article], "TEST")

        assert isinstance(result, NewsSentimentResult)
        assert result.symbol == "TEST"
        assert result.article_count == 1

    def test_analyze_multiple_articles(self):
        """Test analyzing multiple articles."""
        analyzer = NewsAnalyzer()
        articles = [
            NewsArticle(
                title="Great news",
                content="Strong growth",
                source="Source1",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            ),
            NewsArticle(
                title="Bad news",
                content="Losses reported",
                source="Source2",
                published_at=datetime.now(UTC),
                symbols=["TEST"],
            ),
        ]

        result = analyzer.analyze(articles, "TEST")

        assert result.article_count == 2
        assert result.symbol == "TEST"

    def test_analyze_empty_articles_returns_empty(self):
        """Test that empty articles list returns empty result."""
        analyzer = NewsAnalyzer()
        result = analyzer.analyze([], "TEST")

        assert result.article_count == 0
        assert result.overall_score == Decimal("0")

    def test_analyze_with_config(self):
        """Test analyzing with custom config."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("0.8"))
        analyzer = NewsAnalyzer(config)
        article = NewsArticle(
            title="Test",
            content="Test content",
            source="Test Source",
            published_at=datetime.now(UTC),
            relevance_score=Decimal("0.7"),
            symbols=["TEST"],
        )

        result = analyzer.analyze([article], "TEST")

        # Article filtered out due to low relevance
        assert result.article_count == 0

    def test_analyze_batch(self):
        """Test analyzing multiple symbols."""
        analyzer = NewsAnalyzer()
        articles_by_symbol = {
            "TEST1": [
                NewsArticle(
                    title="Good",
                    content="Growth",
                    source="S1",
                    published_at=datetime.now(UTC),
                    symbols=["TEST1"],
                )
            ],
            "TEST2": [
                NewsArticle(
                    title="Bad",
                    content="Loss",
                    source="S2",
                    published_at=datetime.now(UTC),
                    symbols=["TEST2"],
                )
            ],
        }

        results = analyzer.analyze_batch(articles_by_symbol)

        assert len(results) == 2
        assert "TEST1" in results
        assert "TEST2" in results


class TestNewsSentimentResult:
    """Test news sentiment result dataclass."""

    def test_create_result(self):
        """Test creating sentiment result."""
        result = NewsSentimentResult(
            symbol="TEST",
            overall_score=Decimal("0.5"),
            overall_confidence=Decimal("0.8"),
            article_count=5,
            sentiment_label="POSITIVE",
            articles=[],
            timestamp=datetime.now(UTC),
        )

        assert result.symbol == "TEST"
        assert result.overall_score == Decimal("0.5")


class TestMockNewsSource:
    """Test mock news source."""

    def test_fetch_articles(self):
        """Test fetching articles from mock source."""
        article = NewsArticle(
            title="Test",
            content="Content",
            source="Test",
            published_at=datetime.now(UTC),
            symbols=["TEST"],
        )
        source = MockNewsSource([article])

        articles = source.fetch_articles("TEST")

        assert len(articles) == 1
        assert articles[0].title == "Test"

    def test_add_article(self):
        """Test adding article to mock source."""
        source = MockNewsSource()
        article = NewsArticle(
            title="New",
            content="Content",
            source="Test",
            published_at=datetime.now(UTC),
            symbols=["TEST"],
        )

        source.add_article(article)
        articles = source.fetch_articles("TEST")

        assert len(articles) == 1
