"""Tests for sentiment/news_analyzer.py — news sentiment."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_analyzer import (
    MockNewsSource,
    NewsAnalyzer,
    NewsAnalyzerConfig,
    NewsArticle,
    NewsSentimentResult,
)


def _article(
    title: str = "Company shows strong growth",
    content: str = "Profits surged 20%",
    symbol: str = "RELIANCE",
    hours_ago: int = 1,
    relevance: Decimal = Decimal("1.0"),
) -> NewsArticle:
    now = datetime.now(UTC)
    return NewsArticle(
        title=title,
        content=content,
        source="test",
        published_at=now - timedelta(hours=hours_ago),
        symbols=[symbol],
        relevance_score=relevance,
    )


class TestNewsAnalyzerConfig:
    def test_defaults(self) -> None:
        cfg = NewsAnalyzerConfig()
        assert cfg.min_relevance == Decimal("0.5")
        assert cfg.max_age_hours == 24

    def test_negative_relevance_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            NewsAnalyzerConfig(min_relevance=Decimal("-0.1"))

    def test_relevance_gt_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            NewsAnalyzerConfig(min_relevance=Decimal("1.5"))

    def test_negative_max_age_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            NewsAnalyzerConfig(max_age_hours=-1)

    def test_negative_boost_factor_raises(self) -> None:
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            NewsAnalyzerConfig(boost_factor=Decimal("-1"))

    def test_negative_decay_hours_raises(self) -> None:
        with pytest.raises(ConfigError, match="decay_hours cannot be negative"):
            NewsAnalyzerConfig(decay_hours=-1)


class TestNewsAnalyzer:
    def test_positive_article(self) -> None:
        analyzer = NewsAnalyzer()
        articles = [_article(title="Strong growth and profit surge")]
        result = analyzer.analyze(articles, "RELIANCE")
        assert isinstance(result, NewsSentimentResult)
        assert result.article_count > 0

    def test_negative_article(self) -> None:
        analyzer = NewsAnalyzer()
        articles = [
            _article(
                title="Company faces decline and loss",
                content="Revenue dropped sharply",
            )
        ]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.overall_score < Decimal("0")

    def test_empty_articles_returns_neutral(self) -> None:
        analyzer = NewsAnalyzer()
        result = analyzer.analyze([], "RELIANCE")
        assert result.overall_score == Decimal("0")
        assert result.sentiment_label == "NEUTRAL"

    def test_no_relevant_articles(self) -> None:
        analyzer = NewsAnalyzer()
        articles = [_article(symbol="OTHER", relevance=Decimal("0.1"))]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 0

    def test_old_articles_filtered(self) -> None:
        cfg = NewsAnalyzerConfig(max_age_hours=1)
        analyzer = NewsAnalyzer(cfg)
        articles = [_article(hours_ago=5)]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.article_count == 0

    def test_batch_analysis(self) -> None:
        analyzer = NewsAnalyzer()
        articles_by_symbol = {
            "A": [_article(title="Strong growth", symbol="A")],
            "B": [_article(title="Weak decline", symbol="B")],
        }
        results = analyzer.analyze_batch(articles_by_symbol)
        assert len(results) == 2
        assert "A" in results
        assert "B" in results

    def test_confidence_is_decimal(self) -> None:
        analyzer = NewsAnalyzer()
        articles = [_article()]
        result = analyzer.analyze(articles, "RELIANCE")
        assert isinstance(result.overall_confidence, Decimal)

    def test_timestamp_is_utc(self) -> None:
        analyzer = NewsAnalyzer()
        articles = [_article()]
        result = analyzer.analyze(articles, "RELIANCE")
        assert result.timestamp.tzinfo == UTC


class TestMockNewsSource:
    def test_fetch_articles(self) -> None:
        art = _article(symbol="RELIANCE")
        source = MockNewsSource([art])
        result = source.fetch_articles("RELIANCE")
        assert len(result) == 1

    def test_add_article(self) -> None:
        source = MockNewsSource()
        source.add_article(_article(symbol="TCS"))
        assert len(source.fetch_articles("TCS")) == 1

    def test_limit(self) -> None:
        source = MockNewsSource([_article(symbol="X") for _ in range(5)])
        result = source.fetch_articles("X", limit=2)
        assert len(result) == 2


class TestNewsArticle:
    def test_defaults(self) -> None:
        a = NewsArticle(
            title="Test",
            content="Body",
            source="src",
            published_at=datetime.now(UTC),
        )
        assert a.url == ""
        assert a.symbols == []
        assert a.author == ""
        assert a.relevance_score == Decimal("1.0")
