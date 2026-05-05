"""Integration tests for News & Social Sentiment -> Aggregator bridges.

Validates that NewsScraper headlines can be converted to NewsArticle
objects and fed into NewsAnalyzer, and that SocialSentimentAnalyzer
output can be weighted into the SentimentAggregator ensemble.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from iatb.sentiment.aggregator import SentimentAggregator
from iatb.sentiment.base import SentimentScore
from iatb.sentiment.news_analyzer import NewsAnalyzer, NewsArticle, NewsSentimentResult
from iatb.sentiment.news_scraper import NewsHeadline, headlines_to_articles
from iatb.sentiment.social_sentiment import (
    MockSocialSource,
    SocialPost,
    SocialSentimentAnalyzer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Tests for NewsSource -> NewsAnalyzer bridge
# ---------------------------------------------------------------------------


def test_headlines_to_articles_conversion() -> None:
    """NewsHeadline objects are correctly converted to NewsArticles."""
    headlines = [
        NewsHeadline(
            source="moneycontrol",
            title="Nifty rallies on strong GDP data",
            url="https://example.com/1",
            published="Mon, 05 May 2026 10:00:00 GMT",
            article_text="Nifty surged 2% after GDP data...",
        ),
        NewsHeadline(
            source="et_markets",
            title="SBIN posts record profit",
            url="https://example.com/2",
            published="2026-05-05T09:30:00Z",
            article_text="SBIN Q4 profit up 25% YoY...",
        ),
    ]
    articles = headlines_to_articles(headlines)

    assert len(articles) == 2
    assert all(isinstance(a, NewsArticle) for a in articles)
    assert articles[0].title == "Nifty rallies on strong GDP data"
    assert articles[0].source == "moneycontrol"
    assert articles[0].published_at.tzinfo == UTC
    assert articles[1].source == "et_markets"
    assert articles[1].published_at.tzinfo == UTC


def test_headlines_to_articles_with_empty_published() -> None:
    """Handle empty published strings gracefully."""
    headlines = [
        NewsHeadline(
            source="test",
            title="Test headline",
            url="",
            published="",
            article_text="",
        ),
    ]
    articles = headlines_to_articles(headlines)
    assert len(articles) == 1
    assert articles[0].published_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# Tests for NewsAnalyzer -> Aggregator bridge
# ---------------------------------------------------------------------------


def test_news_analyzer_analyze_headlines_bridge() -> None:
    """NewsAnalyzer.analyze_headlines() bridges NewsScraper to Aggregator."""
    analyzer = NewsAnalyzer()
    headlines = [
        NewsHeadline(
            source="mc",
            title="Nifty strong growth rally",
            url="",
            published="",
            article_text="Nifty shows strong growth and rally...",
        ),
    ]
    result = analyzer.analyze_headlines(headlines, "Nifty")

    assert isinstance(result, NewsSentimentResult)
    assert result.symbol == "Nifty"
    assert result.article_count == 1
    assert Decimal("0") <= result.overall_score <= Decimal("1")
    assert Decimal("0") <= result.overall_confidence <= Decimal("1")


# ---------------------------------------------------------------------------
# Tests for SocialSentimentAnalyzer -> Aggregator bridge
# ---------------------------------------------------------------------------


def test_social_analyzer_to_sentiment_score_bridge() -> None:
    """SocialSentimentAnalyzer.analyze_to_sentiment_score returns SentimentScore."""
    analyzer = SocialSentimentAnalyzer()
    posts = [
        SocialPost(
            content="buying more SBIN, strong rally expected",
            platform="twitter",
            author="trader1",
            published_at=_now(),
            likes=100,
            shares=20,
            comments=15,
            followers=5000,
            symbols=["SBIN"],
        ),
        SocialPost(
            content="SBIN bullish breakout confirmed",
            platform="twitter",
            author="trader2",
            published_at=_now(),
            likes=50,
            shares=10,
            comments=5,
            followers=2000,
            symbols=["SBIN"],
        ),
    ]
    score = analyzer.analyze_to_sentiment_score(posts, "SBIN")

    assert isinstance(score, SentimentScore)
    assert score.source == "social"
    assert Decimal("0") <= score.confidence <= Decimal("1")
    assert -Decimal("1") <= score.score <= Decimal("1")


# ---------------------------------------------------------------------------
# Tests for SentimentAggregator with News & Social
# ---------------------------------------------------------------------------


def test_aggregator_default_weights_are_correct() -> None:
    """Aggregator default weights match spec: 0.35, 0.25, 0.10, 0.15, 0.15."""
    agg = SentimentAggregator()
    expected = {
        "finbert": Decimal("0.35"),
        "aion": Decimal("0.25"),
        "vader": Decimal("0.10"),
        "news": Decimal("0.15"),
        "social": Decimal("0.15"),
    }
    for name, expected_weight in expected.items():
        assert agg._get_weight(name) == expected_weight, name


def test_aggregator_analyze_full_ensemble_with_news_and_social() -> None:
    """Full ensemble includes text, news, and social components."""
    # Create a mock text analyzer to avoid loading heavy models
    mock_finbert = MagicMock()
    mock_finbert.analyze.return_value = SentimentScore(
        source="finbert",
        score=Decimal("0.8"),
        confidence=Decimal("0.9"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_aion = MagicMock()
    mock_aion.analyze.return_value = SentimentScore(
        source="aion",
        score=Decimal("0.7"),
        confidence=Decimal("0.85"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_vader = MagicMock()
    mock_vader.analyze.return_value = SentimentScore(
        source="vader",
        score=Decimal("0.6"),
        confidence=Decimal("0.8"),
        label="POSITIVE",
        text_excerpt="test",
    )

    agg = SentimentAggregator(
        finbert=mock_finbert,
        aion=mock_aion,
        vader=mock_vader,
        enable_graceful_fallback=False,
    )

    # News articles
    news_articles = [
        NewsArticle(
            title="Nifty strong growth rally",
            content="Nifty shows strong growth and rally...",
            source="mc",
            published_at=_now(),
            symbols=["Nifty"],
        ),
    ]

    # Social posts
    social_posts = [
        SocialPost(
            content="bullish on Nifty, strong rally",
            platform="twitter",
            author="trader",
            published_at=_now(),
            likes=100,
            shares=20,
            comments=15,
            followers=5000,
            symbols=["Nifty"],
        ),
    ]

    composite, components = agg.analyze_full_ensemble(
        "Nifty bullish sentiment today",
        news_articles=news_articles,
        social_posts=social_posts,
        symbol="Nifty",
    )

    assert isinstance(composite, SentimentScore)
    assert composite.source == "full_ensemble"
    assert "finbert" in components
    assert "aion" in components
    assert "vader" in components
    assert "news" in components
    assert "social" in components
    assert composite.confidence > Decimal("0")


def test_aggregator_analyze_full_ensemble_no_news_social() -> None:
    """Full ensemble works even when news and social are not provided."""
    mock_finbert = MagicMock()
    mock_finbert.analyze.return_value = SentimentScore(
        source="finbert",
        score=Decimal("0.5"),
        confidence=Decimal("0.9"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_aion = MagicMock()
    mock_aion.analyze.return_value = SentimentScore(
        source="aion",
        score=Decimal("0.4"),
        confidence=Decimal("0.85"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_vader = MagicMock()
    mock_vader.analyze.return_value = SentimentScore(
        source="vader",
        score=Decimal("0.3"),
        confidence=Decimal("0.8"),
        label="POSITIVE",
        text_excerpt="test",
    )

    agg = SentimentAggregator(
        finbert=mock_finbert,
        aion=mock_aion,
        vader=mock_vader,
        enable_graceful_fallback=False,
    )

    composite, components = agg.analyze_full_ensemble("Some text", symbol="TEST")

    assert isinstance(composite, SentimentScore)
    assert "finbert" in components
    assert "news" not in components
    assert "social" not in components


# ---------------------------------------------------------------------------
# Tests for recency weighting integration
# ---------------------------------------------------------------------------


def test_aggregator_applies_recency_weighting_to_news() -> None:
    """News analysis applies recency weighting in the aggregator."""
    # Provide mock analyzers to avoid heavy model loading (transformers/PyTorch)
    mock_finbert = MagicMock()
    mock_finbert.analyze.return_value = SentimentScore(
        source="finbert",
        score=Decimal("0.5"),
        confidence=Decimal("0.9"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_aion = MagicMock()
    mock_aion.analyze.return_value = SentimentScore(
        source="aion",
        score=Decimal("0.4"),
        confidence=Decimal("0.85"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_vader = MagicMock()
    mock_vader.analyze.return_value = SentimentScore(
        source="vader",
        score=Decimal("0.3"),
        confidence=Decimal("0.8"),
        label="POSITIVE",
        text_excerpt="test",
    )
    agg = SentimentAggregator(
        finbert=mock_finbert,
        aion=mock_aion,
        vader=mock_vader,
        enable_graceful_fallback=False,
    )
    now = _now()
    articles = [
        NewsArticle(
            title="Old news",
            content="old content",
            source="mc",
            published_at=now - timedelta(hours=5),
            symbols=["TEST"],
        ),
        NewsArticle(
            title="Recent news strong",
            content="recent content strong growth",
            source="et",
            published_at=now - timedelta(minutes=15),
            symbols=["TEST"],
        ),
    ]
    result = agg.analyze_news(articles, "TEST")

    assert isinstance(result, NewsSentimentResult)
    assert result.article_count == 2
    # Recency weighting should have been attempted (may or may not change score)
    assert Decimal("0") <= result.overall_confidence <= Decimal("1")


# ---------------------------------------------------------------------------
# Tests with Mock sources
# ---------------------------------------------------------------------------


def test_mock_social_source_fetch_posts() -> None:
    """MockSocialSource returns posts matching symbol."""
    posts = [
        SocialPost(
            content="SBIN looks bullish",
            platform="twitter",
            author="t1",
            published_at=_now(),
            symbols=["SBIN"],
        ),
        SocialPost(
            content="INFY going strong",
            platform="twitter",
            author="t2",
            published_at=_now(),
            symbols=["INFY"],
        ),
    ]
    source = MockSocialSource(posts)
    sbin_posts = source.fetch_posts("SBIN")
    assert len(sbin_posts) == 1
    assert sbin_posts[0].symbols == ["SBIN"]


def test_aggregator_evaluate_instrument_full_with_all_sources() -> None:
    """evaluate_instrument_full includes all sources and correct volume gate."""
    mock_finbert = MagicMock()
    mock_finbert.analyze.return_value = SentimentScore(
        source="finbert",
        score=Decimal("0.85"),
        confidence=Decimal("0.9"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_aion = MagicMock()
    mock_aion.analyze.return_value = SentimentScore(
        source="aion",
        score=Decimal("0.75"),
        confidence=Decimal("0.85"),
        label="POSITIVE",
        text_excerpt="test",
    )
    mock_vader = MagicMock()
    mock_vader.analyze.return_value = SentimentScore(
        source="vader",
        score=Decimal("0.65"),
        confidence=Decimal("0.8"),
        label="POSITIVE",
        text_excerpt="test",
    )

    agg = SentimentAggregator(
        finbert=mock_finbert,
        aion=mock_aion,
        vader=mock_vader,
        very_strong_threshold=Decimal("0.50"),
        enable_graceful_fallback=False,
    )

    news_articles = [
        NewsArticle(
            title="Strong growth in tech",
            content="Tech sector shows strong growth...",
            source="mc",
            published_at=_now(),
            symbols=["INFY"],
        ),
    ]
    social_posts = [
        SocialPost(
            content="INFY bullish breakout",
            platform="twitter",
            author="trader",
            published_at=_now(),
            likes=100,
            shares=20,
            comments=15,
            followers=5000,
            symbols=["INFY"],
        ),
    ]

    result = agg.evaluate_instrument_full(
        "INFY showing positive momentum",
        volume_ratio=Decimal("2.0"),
        news_articles=news_articles,
        social_posts=social_posts,
        symbol="INFY",
    )

    assert result.very_strong is True
    assert result.volume_confirmed is True
    assert result.tradable is True
    assert "news" in result.component_scores
    assert "social" in result.component_scores
