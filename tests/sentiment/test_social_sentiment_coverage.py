"""Tests for sentiment/social_sentiment.py — social media sentiment."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore
from iatb.sentiment.social_sentiment import (
    MockSocialSource,
    SocialPost,
    SocialSentimentAnalyzer,
    SocialSentimentConfig,
    SocialSentimentResult,
)


def _post(
    content: str = "This stock is bullish",
    platform: str = "twitter",
    author: str = "trader1",
    hours_ago: int = 1,
    symbol: str = "RELIANCE",
    likes: int = 50,
    shares: int = 10,
    comments: int = 5,
    followers: int = 5000,
    relevance: Decimal = Decimal("1.0"),
) -> SocialPost:
    now = datetime.now(UTC)
    return SocialPost(
        content=content,
        platform=platform,
        author=author,
        published_at=now - timedelta(hours=hours_ago),
        likes=likes,
        shares=shares,
        comments=comments,
        followers=followers,
        symbols=[symbol],
        relevance_score=relevance,
    )


class TestSocialSentimentConfig:
    def test_defaults(self) -> None:
        cfg = SocialSentimentConfig()
        assert cfg.min_relevance == Decimal("0.5")

    def test_negative_relevance_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            SocialSentimentConfig(min_relevance=Decimal("-0.1"))

    def test_negative_max_age_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            SocialSentimentConfig(max_age_hours=-1)

    def test_negative_engagement_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_engagement cannot be negative"):
            SocialSentimentConfig(min_engagement=-1)

    def test_invalid_weights_sum_raises(self) -> None:
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            SocialSentimentConfig(
                engagement_weight=Decimal("0.5"),
                follower_weight=Decimal("0.5"),
                recency_weight=Decimal("0.5"),
            )

    def test_negative_boost_raises(self) -> None:
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            SocialSentimentConfig(boost_factor=Decimal("-1"))


class TestSocialSentimentAnalyzer:
    def test_bullish_post(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts = [_post(content="This stock is bullish and growing")]
        result = analyzer.analyze(posts, "RELIANCE")
        assert isinstance(result, SocialSentimentResult)
        assert result.post_count > 0

    def test_bearish_post(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts = [_post(content="This stock is bearish and falling")]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.overall_score < Decimal("0")

    def test_empty_posts(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        result = analyzer.analyze([], "RELIANCE")
        assert result.overall_score == Decimal("0")
        assert result.post_count == 0

    def test_no_relevant_posts(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts = [_post(content="Random text", symbol="OTHER", relevance=Decimal("0.1"))]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 0

    def test_low_engagement_filtered(self) -> None:
        cfg = SocialSentimentConfig(min_engagement=100)
        analyzer = SocialSentimentAnalyzer(cfg)
        posts = [_post(content="bullish", likes=1, shares=0, comments=0)]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 0

    def test_old_posts_filtered(self) -> None:
        cfg = SocialSentimentConfig(max_age_hours=1)
        analyzer = SocialSentimentAnalyzer(cfg)
        posts = [_post(content="bullish rally", hours_ago=5)]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 0

    def test_batch_analysis(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts_by_symbol = {
            "A": [_post(content="bullish", symbol="A")],
            "B": [_post(content="bearish decline", symbol="B")],
        }
        results = analyzer.analyze_batch(posts_by_symbol)
        assert len(results) == 2

    def test_analyze_to_sentiment_score(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts = [_post(content="bullish")]
        result = analyzer.analyze_to_sentiment_score(posts, "RELIANCE")
        assert isinstance(result, SentimentScore)
        assert result.source == "social"

    def test_total_engagement(self) -> None:
        analyzer = SocialSentimentAnalyzer()
        posts = [_post(content="bullish", likes=100, shares=20, comments=10)]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.total_engagement == 130


class TestMockSocialSource:
    def test_fetch_posts(self) -> None:
        post = _post(symbol="RELIANCE")
        source = MockSocialSource([post])
        result = source.fetch_posts("RELIANCE")
        assert len(result) == 1

    def test_add_post(self) -> None:
        source = MockSocialSource()
        source.add_post(_post(symbol="TCS"))
        assert len(source.fetch_posts("TCS")) == 1

    def test_limit(self) -> None:
        source = MockSocialSource([_post(symbol="X") for _ in range(10)])
        result = source.fetch_posts("X", limit=3)
        assert len(result) == 3


class TestSocialPost:
    def test_defaults(self) -> None:
        p = SocialPost(
            content="test",
            platform="twitter",
            author="a",
            published_at=datetime.now(UTC),
        )
        assert p.likes == 0
        assert p.shares == 0
        assert p.url == ""
        assert p.relevance_score == Decimal("1.0")
