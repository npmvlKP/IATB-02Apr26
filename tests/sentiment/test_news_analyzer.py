"""
Tests for news_analyzer module.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import sentiment_label_from_score
from iatb.sentiment.news_analyzer import (
    MockNewsSource,
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
    NewsSentimentResult,
)


class TestNewsAnalyzerConfig:
    """Test NewsAnalyzerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = NewsAnalyzerConfig()
        assert config.min_relevance == Decimal("0.5")
        assert config.max_age_hours == 24
        assert config.boost_factor == Decimal("1.0")

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = NewsAnalyzerConfig(
            min_relevance=Decimal("0.7"),
            max_age_hours=12,
            boost_factor=Decimal("1.5"),
        )
        assert config.min_relevance == Decimal("0.7")
        assert config.max_age_hours == 12
        assert config.boost_factor == Decimal("1.5")

    def test_invalid_min_relevance_raises_error(self) -> None:
        """Test that invalid min_relevance raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in \\[0, 1\\]"):
            NewsAnalyzerConfig(min_relevance=Decimal("1.5"))

    def test_negative_max_age_hours_raises_error(self) -> None:
        """Test that negative max_age_hours raises ConfigError."""
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            NewsAnalyzerConfig(max_age_hours=-1)

    def test_negative_boost_factor_raises_error(self) -> None:
        """Test that negative boost_factor raises ConfigError."""
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            NewsAnalyzerConfig(boost_factor=Decimal("-0.5"))


class TestNewsArticle:
    """Test NewsArticle dataclass."""

    def test_create_article(self) -> None:
        """Test creating a news article."""
        now = datetime.now(UTC)
        article = NewsArticle(
            title="Test Title",
            content="Test content",
            source="Test Source",
            published_at=now,
        )
        assert article.title == "Test Title"
        assert article.source == "Test Source"
        assert article.published_at == now

    def test_article_with_all_fields(self) -> None:
        """Test article with all fields."""
        now = datetime.now(UTC)
        article = NewsArticle(
            title="Test Title",
            content="Test content",
            source="Test Source",
            published_at=now,
            url="https://test.com",
            symbols=["TEST"],
            author="Test Author",
            relevance_score=Decimal("0.8"),
        )
        assert article.url == "https://test.com"
        assert article.symbols == ["TEST"]
        assert article.author == "Test Author"
        assert article.relevance_score == Decimal("0.8")


class TestNewsAnalyzer:
    """Test NewsAnalyzer class."""

    def test_analyze_with_empty_articles(self) -> None:
        """Test analyzing with empty articles list."""
        analyzer = NewsAnalyzer()
        result = analyzer.analyze([], "TEST")
        assert isinstance(result, NewsSentimentResult)
        assert result.symbol == "TEST"
        assert result.article_count == 0
        assert result.overall_score == Decimal("0")
        assert result.sentiment_label == "NEUTRAL"

    def test_analyze_with_positive_article(self) -> None:
        """Test analyzing with positive article."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Strong growth and profit for TEST",
                content="TEST company shows strong growth and profit",
                source="Test Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 1
        assert result.overall_score > Decimal("0")
        assert result.sentiment_label in ["POSITIVE", "NEUTRAL"]

    def test_analyze_with_negative_article(self) -> None:
        """Test analyzing with negative article."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Weak performance and loss for TEST",
                content="TEST company shows weak performance and loss",
                source="Test Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 1
        assert result.overall_score < Decimal("0")
        assert result.sentiment_label == "NEGATIVE"

    def test_analyze_with_mixed_articles(self) -> None:
        """Test analyzing with mixed positive and negative articles."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Strong growth for TEST",
                content="TEST shows strong growth",
                source="Source1",
                published_at=now,
                symbols=["TEST"],
            ),
            NewsArticle(
                title="Weak performance for TEST",
                content="TEST shows weak performance",
                source="Source2",
                published_at=now,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 2
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_analyze_filters_by_relevance(self) -> None:
        """Test that articles are filtered by relevance."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("0.8"))
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Test article",
                content="Test content",
                source="Source1",
                published_at=now,
                symbols=["TEST"],
                relevance_score=Decimal("0.9"),
            ),
            NewsArticle(
                title="Low relevance",
                content="Low relevance content",
                source="Source2",
                published_at=now,
                symbols=["TEST"],
                relevance_score=Decimal("0.3"),
            ),
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 1

    def test_analyze_filters_by_age(self) -> None:
        """Test that articles are filtered by age."""
        config = NewsAnalyzerConfig(max_age_hours=12)
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        old_time = now - timedelta(hours=24)
        articles = [
            NewsArticle(
                title="Recent article",
                content="Recent content",
                source="Source1",
                published_at=now,
                symbols=["TEST"],
            ),
            NewsArticle(
                title="Old article",
                content="Old content",
                source="Source2",
                published_at=old_time,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 1

    def test_analyze_filters_by_symbol(self) -> None:
        """Test that articles are filtered by symbol."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="TEST news",
                content="News about TEST",
                source="Source1",
                published_at=now,
                symbols=["TEST"],
            ),
            NewsArticle(
                title="OTHER news",
                content="News about OTHER",
                source="Source2",
                published_at=now,
                symbols=["OTHER"],
            ),
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 1

    def test_analyze_with_boost_factor(self) -> None:
        """Test analyzing with boost factor."""
        config = NewsAnalyzerConfig(boost_factor=Decimal("2.0"))
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Strong growth for TEST",
                content="TEST shows strong growth",
                source="Test Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.overall_score > Decimal("0")

    def test_analyze_batch_empty(self) -> None:
        """Test batch analyzing with empty dict."""
        analyzer = NewsAnalyzer()
        results = analyzer.analyze_batch({})
        assert results == {}

    def test_analyze_batch_multiple_symbols(self) -> None:
        """Test batch analyzing with multiple symbols."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles_by_symbol = {
            "TEST1": [
                NewsArticle(
                    title="Strong growth for TEST1",
                    content="TEST1 shows strong growth",
                    source="Source1",
                    published_at=now,
                    symbols=["TEST1"],
                )
            ],
            "TEST2": [
                NewsArticle(
                    title="Weak performance for TEST2",
                    content="TEST2 shows weak performance",
                    source="Source2",
                    published_at=now,
                    symbols=["TEST2"],
                )
            ],
        }
        results = analyzer.analyze_batch(articles_by_symbol)
        assert len(results) == 2
        assert "TEST1" in results
        assert "TEST2" in results

    def test_confidence_computation(self) -> None:
        """Test confidence computation."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Strong growth for TEST",
                content="TEST shows strong growth",
                source="Test Source",
                published_at=now,
                symbols=["TEST"],
                relevance_score=Decimal("1.0"),
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert Decimal("0") <= result.overall_confidence <= Decimal("1")
        assert result.overall_confidence > Decimal("0.5")

    def test_aggregation_of_multiple_articles(self) -> None:
        """Test aggregation of multiple articles."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title=f"Article {i}",
                content="TEST shows strong growth" if i % 2 == 0 else "TEST shows weak performance",
                source=f"Source{i}",
                published_at=now,
                symbols=["TEST"],
            )
            for i in range(4)
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.article_count == 4
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_sentiment_label_from_score(self) -> None:
        """Test sentiment label determination."""
        assert sentiment_label_from_score(Decimal("0.1")) == "POSITIVE"
        assert sentiment_label_from_score(Decimal("-0.1")) == "NEGATIVE"
        assert sentiment_label_from_score(Decimal("0.0")) == "NEUTRAL"
        assert sentiment_label_from_score(Decimal("0.05")) == "POSITIVE"
        assert sentiment_label_from_score(Decimal("-0.05")) == "NEGATIVE"

    def test_text_excerpt_truncation(self) -> None:
        """Test that text excerpt is truncated."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        long_text = "A" * 300
        articles = [
            NewsArticle(
                title="Test",
                content=long_text,
                source="Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert len(result.articles[0].text_excerpt) <= 203

    def test_metadata_in_sentiment_score(self) -> None:
        """Test that metadata is included in sentiment score."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Test article",
                content="Test content",
                source="Test Source",
                published_at=now,
                symbols=["TEST"],
                url="https://test.com/article",
                author="Test Author",
                relevance_score=Decimal("0.9"),
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.articles[0].metadata["url"] == "https://test.com/article"
        assert result.articles[0].metadata["author"] == "Test Author"
        assert result.articles[0].metadata["relevance"] == "0.9"

    def test_score_clamping(self) -> None:
        """Test that scores are clamped to [-1, 1]."""
        config = NewsAnalyzerConfig(boost_factor=Decimal("10.0"))
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Strong strong strong growth",
                content="Strong growth profit success",
                source="Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_no_keywords_returns_neutral(self) -> None:
        """Test that text with no keywords returns neutral score."""
        analyzer = NewsAnalyzer()
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Test article with no sentiment words",
                content="This is a regular article about TEST",
                source="Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.overall_score == Decimal("0")

    def test_custom_keywords(self) -> None:
        """Test with custom positive and negative keywords."""
        config = NewsAnalyzerConfig(
            positive_keywords=["custom_positive"],
            negative_keywords=["custom_negative"],
        )
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="custom_positive article",
                content="TEST is custom_positive",
                source="Source",
                published_at=now,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(articles, "TEST")
        assert result.overall_score > Decimal("0")


class TestMockNewsSource:
    """Test MockNewsSource."""

    def test_fetch_articles_by_symbol(self) -> None:
        """Test fetching articles by symbol."""
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="TEST1 news",
                content="News about TEST1",
                source="Source1",
                published_at=now,
                symbols=["TEST1"],
            ),
            NewsArticle(
                title="TEST2 news",
                content="News about TEST2",
                source="Source2",
                published_at=now,
                symbols=["TEST2"],
            ),
        ]
        source = MockNewsSource(articles)
        test1_articles = source.fetch_articles("TEST1")
        assert len(test1_articles) == 1
        assert "TEST1" in test1_articles[0].symbols

    def test_fetch_articles_with_limit(self) -> None:
        """Test fetching articles with limit."""
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title=f"Article {i}",
                content=f"Content {i}",
                source="Source",
                published_at=now,
                symbols=["TEST"],
            )
            for i in range(10)
        ]
        source = MockNewsSource(articles)
        limited_articles = source.fetch_articles("TEST", limit=3)
        assert len(limited_articles) == 3

    def test_add_article(self) -> None:
        """Test adding an article to the source."""
        now = datetime.now(UTC)
        source = MockNewsSource()
        article = NewsArticle(
            title="New article",
            content="New content",
            source="Source",
            published_at=now,
            symbols=["TEST"],
        )
        source.add_article(article)
        articles = source.fetch_articles("TEST")
        assert len(articles) == 1

    def test_fetch_empty_source(self) -> None:
        """Test fetching from empty source."""
        source = MockNewsSource()
        articles = source.fetch_articles("TEST")
        assert articles == []
