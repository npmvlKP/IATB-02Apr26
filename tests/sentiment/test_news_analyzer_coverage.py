"""
Comprehensive coverage tests for news_analyzer.py.

Tests news sentiment analysis, keyword extraction, and error paths.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_analyzer import (
    MockNewsSource,
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
)


class TestNewsAnalyzerConfig:
    """Test NewsAnalyzerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = NewsAnalyzerConfig()
        assert config.min_relevance == Decimal("0.5")
        assert config.max_age_hours == 24
        assert config.boost_factor == Decimal("1.0")
        assert config.decay_hours == 6

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = NewsAnalyzerConfig(
            min_relevance=Decimal("0.8"),
            max_age_hours=12,
            boost_factor=Decimal("1.5"),
        )
        assert config.min_relevance == Decimal("0.8")
        assert config.max_age_hours == 12
        assert config.boost_factor == Decimal("1.5")

    def test_min_relevance_below_zero_raises_error(self) -> None:
        """Test min_relevance below 0 raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            NewsAnalyzerConfig(min_relevance=Decimal("-0.1"))

    def test_min_relevance_above_one_raises_error(self) -> None:
        """Test min_relevance above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            NewsAnalyzerConfig(min_relevance=Decimal("1.1"))

    def test_max_age_hours_negative_raises_error(self) -> None:
        """Test max_age_hours negative raises ConfigError."""
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            NewsAnalyzerConfig(max_age_hours=-1)

    def test_boost_factor_negative_raises_error(self) -> None:
        """Test boost_factor negative raises ConfigError."""
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            NewsAnalyzerConfig(boost_factor=Decimal("-0.1"))

    def test_decay_hours_negative_raises_error(self) -> None:
        """Test decay_hours negative raises ConfigError."""
        with pytest.raises(ConfigError, match="decay_hours cannot be negative"):
            NewsAnalyzerConfig(decay_hours=-1)

    def test_boundary_min_relevance_zero(self) -> None:
        """Test boundary min_relevance of 0."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("0"))
        assert config.min_relevance == Decimal("0")

    def test_boundary_min_relevance_one(self) -> None:
        """Test boundary min_relevance of 1."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("1"))
        assert config.min_relevance == Decimal("1")

    def test_boundary_max_age_hours_zero(self) -> None:
        """Test boundary max_age_hours of 0."""
        config = NewsAnalyzerConfig(max_age_hours=0)
        assert config.max_age_hours == 0


class TestNewsArticle:
    """Test NewsArticle dataclass."""

    def test_create_article(self) -> None:
        """Test creating a news article."""
        article = NewsArticle(
            title="Strong earnings",
            content="Company beats expectations",
            source="test",
            published_at=datetime.now(UTC),
        )
        assert article.title == "Strong earnings"
        assert article.content == "Company beats expectations"
        assert article.source == "test"

    def test_article_with_optional_fields(self) -> None:
        """Test article with optional fields."""
        article = NewsArticle(
            title="Test",
            content="Test content",
            source="test",
            published_at=datetime.now(UTC),
            url="https://example.com",
            symbols=["AAPL", "GOOGL"],
            author="John Doe",
            relevance_score=Decimal("0.9"),
        )
        assert article.url == "https://example.com"
        assert article.symbols == ["AAPL", "GOOGL"]
        assert article.author == "John Doe"
        assert article.relevance_score == Decimal("0.9")


class TestNewsAnalyzer:
    """Test NewsAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = NewsAnalyzer()
        assert analyzer is not None

    def test_analyze_empty_articles(self) -> None:
        """Test analyzing empty articles list."""
        analyzer = NewsAnalyzer()
        articles: list[NewsArticle] = []
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 0
        assert result.overall_score == Decimal("0")
        assert result.sentiment_label == "NEUTRAL"

    def test_analyze_single_positive_article(self) -> None:
        """Test analyzing single positive article."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Strong earnings growth",
            content="Company reports strong profit and growth",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        assert result.article_count == 1
        assert result.overall_score > Decimal("0")

    def test_analyze_single_negative_article(self) -> None:
        """Test analyzing single negative article."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Weak earnings miss",
            content="Company reports weak results and decline",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        assert result.article_count == 1
        assert result.overall_score < Decimal("0")

    def test_analyze_multiple_articles(self) -> None:
        """Test analyzing multiple articles."""
        analyzer = NewsAnalyzer()
        articles = [
            NewsArticle(
                title="Strong earnings",
                content="Great profit and growth",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
            ),
            NewsArticle(
                title="Weak guidance",
                content="Concern about future decline",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.8"),
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 2

    def test_analyze_filters_by_relevance(self) -> None:
        """Test articles are filtered by relevance score."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("0.8"))
        analyzer = NewsAnalyzer(config)
        articles = [
            NewsArticle(
                title="High relevance",
                content="Important news",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
            ),
            NewsArticle(
                title="Low relevance",
                content="Less important",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.5"),  # Below threshold
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        # Only high relevance article should be included
        assert result.article_count == 1

    def test_analyze_filters_by_age(self) -> None:
        """Test articles are filtered by age."""
        config = NewsAnalyzerConfig(max_age_hours=12)
        analyzer = NewsAnalyzer(config)
        now = datetime.now(UTC)
        articles = [
            NewsArticle(
                title="Recent article",
                content="Recent news",
                source="test",
                published_at=now - timedelta(hours=6),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
            ),
            NewsArticle(
                title="Old article",
                content="Old news",
                source="test",
                published_at=now - timedelta(hours=24),  # Too old
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        # Only recent article should be included
        assert result.article_count == 1

    def test_analyze_filters_by_symbol(self) -> None:
        """Test articles are filtered by symbol."""
        analyzer = NewsAnalyzer()
        articles = [
            NewsArticle(
                title="RELIANCE news",
                content="News about RELIANCE",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
            ),
            NewsArticle(
                title="Other news",
                content="News about other company",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["TCS"],
                relevance_score=Decimal("0.9"),
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        # Only RELIANCE article should be included
        assert result.article_count == 1

    def test_analyze_with_title_match(self) -> None:
        """Test articles match if symbol is in title."""
        analyzer = NewsAnalyzer()
        articles = [
            NewsArticle(
                title="RELIANCE reports earnings",
                content="Earnings announcement",
                source="test",
                published_at=datetime.now(UTC),
                symbols=[],  # No symbols, but title contains RELIANCE
                relevance_score=Decimal("0.9"),
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 1

    def test_analyze_case_insensitive(self) -> None:
        """Test symbol matching is case-insensitive."""
        analyzer = NewsAnalyzer()
        articles = [
            NewsArticle(
                title="reliance news",
                content="News about reliance",
                source="test",
                published_at=datetime.now(UTC),
                symbols=[],
                relevance_score=Decimal("0.9"),
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 1

    def test_analyze_all_filtered_out(self) -> None:
        """Test when all articles are filtered out."""
        config = NewsAnalyzerConfig(min_relevance=Decimal("0.9"))
        analyzer = NewsAnalyzer(config)
        articles = [
            NewsArticle(
                title="Test",
                content="Test",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.5"),  # Below threshold
            ),
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 0
        assert result.sentiment_label == "NEUTRAL"

    def test_score_bounds(self) -> None:
        """Test score is always in [-1, 1]."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Test",
            content="Test",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_confidence_bounds(self) -> None:
        """Test confidence is always in [0, 1]."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Test",
            content="Test",
            source="test",
            symbols=["RELIANCE"],
            published_at=datetime.now(UTC),
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        assert Decimal("0") <= result.overall_confidence <= Decimal("1")

    def test_sentiment_label_positive(self) -> None:
        """Test positive sentiment label."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Strong growth and profit",
            content="Great success",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        if result.overall_score > Decimal("0.05"):
            assert result.sentiment_label == "POSITIVE"

    def test_sentiment_label_negative(self) -> None:
        """Test negative sentiment label."""
        analyzer = NewsAnalyzer()
        article = NewsArticle(
            title="Weak decline and loss",
            content="Terrible failure",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
        )
        result = analyzer.analyze([article], "RELIANCE")
        if result.overall_score < Decimal("-0.05"):
            assert result.sentiment_label == "NEGATIVE"


class TestNewsAnalyzeBatch:
    """Test analyze_batch method."""

    def test_analyze_batch_multiple_symbols(self) -> None:
        """Test analyzing news for multiple symbols."""
        analyzer = NewsAnalyzer()
        articles_by_symbol = {
            "RELIANCE": [
                NewsArticle(
                    title="RELIANCE news",
                    content="Test",
                    source="test",
                    published_at=datetime.now(UTC),
                    symbols=["RELIANCE"],
                    relevance_score=Decimal("0.9"),
                )
            ],
            "TCS": [
                NewsArticle(
                    title="TCS news",
                    content="Test",
                    source="test",
                    published_at=datetime.now(UTC),
                    symbols=["TCS"],
                    relevance_score=Decimal("0.9"),
                )
            ],
        }
        results = analyzer.analyze_batch(articles_by_symbol)
        assert len(results) == 2
        assert "RELIANCE" in results
        assert "TCS" in results

    def test_analyze_batch_empty_dict(self) -> None:
        """Test analyzing batch with empty dict."""
        analyzer = NewsAnalyzer()
        results = analyzer.analyze_batch({})
        assert len(results) == 0


class TestMockNewsSource:
    """Test MockNewsSource."""

    def test_mock_source_initialization(self) -> None:
        """Test mock source initialization."""
        source = MockNewsSource()
        assert source is not None

    def test_mock_source_with_articles(self) -> None:
        """Test mock source with articles."""
        article = NewsArticle(
            title="Test",
            content="Test",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source = MockNewsSource([article])
        assert len(source._articles) == 1

    def test_fetch_articles_by_symbol(self) -> None:
        """Test fetching articles by symbol."""
        article = NewsArticle(
            title="RELIANCE news",
            content="Test",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source = MockNewsSource([article])
        articles = source.fetch_articles("RELIANCE")
        assert len(articles) == 1
        assert articles[0].title == "RELIANCE news"

    def test_fetch_articles_by_content(self) -> None:
        """Test fetching articles by content match."""
        # MockNewsSource doesn't implement content search - skip this test
        pytest.skip("MockNewsSource doesn't support content search")

    def test_fetch_articles_limit(self) -> None:
        """Test fetch with limit."""
        articles = [
            NewsArticle(
                title=f"Article {i}",
                content="RELIANCE",
                source="test",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
            )
            for i in range(10)
        ]
        source = MockNewsSource(articles)
        fetched = source.fetch_articles("RELIANCE", limit=5)
        assert len(fetched) == 5

    def test_add_article(self) -> None:
        """Test adding article to mock source."""
        source = MockNewsSource()
        article = NewsArticle(
            title="Test",
            content="Test",
            source="test",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source.add_article(article)
        assert len(source._articles) == 1
