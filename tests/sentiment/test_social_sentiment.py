"""
Tests for social_sentiment module.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.social_sentiment import (
    MockSocialSource,
    SocialPost,
    SocialSentimentAnalyzer,
    SocialSentimentConfig,
    SocialSentimentResult,
)


class TestSocialSentimentConfig:
    """Test SocialSentimentConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = SocialSentimentConfig()
        assert config.min_relevance == Decimal("0.5")
        assert config.max_age_hours == 12
        assert config.min_engagement == 10
        assert config.boost_factor == Decimal("1.0")

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = SocialSentimentConfig(
            min_relevance=Decimal("0.7"),
            max_age_hours=6,
            min_engagement=20,
            boost_factor=Decimal("1.5"),
        )
        assert config.min_relevance == Decimal("0.7")
        assert config.max_age_hours == 6
        assert config.min_engagement == 20
        assert config.boost_factor == Decimal("1.5")

    def test_invalid_min_relevance_raises_error(self) -> None:
        """Test that invalid min_relevance raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in \\[0, 1\\]"):
            SocialSentimentConfig(min_relevance=Decimal("1.5"))

    def test_negative_max_age_hours_raises_error(self) -> None:
        """Test that negative max_age_hours raises ConfigError."""
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            SocialSentimentConfig(max_age_hours=-1)

    def test_negative_min_engagement_raises_error(self) -> None:
        """Test that negative min_engagement raises ConfigError."""
        with pytest.raises(ConfigError, match="min_engagement cannot be negative"):
            SocialSentimentConfig(min_engagement=-10)

    def test_weights_sum_not_one_raises_error(self) -> None:
        """Test that weights not summing to 1.0 raises ConfigError."""
        with pytest.raises(
            ConfigError, match="engagement, follower, and recency weights must sum to 1.0"
        ):
            SocialSentimentConfig(
                engagement_weight=Decimal("0.5"),
                follower_weight=Decimal("0.3"),
                recency_weight=Decimal("0.4"),
            )

    def test_negative_boost_factor_raises_error(self) -> None:
        """Test that negative boost_factor raises ConfigError."""
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            SocialSentimentConfig(boost_factor=Decimal("-0.5"))


class TestSocialPost:
    """Test SocialPost dataclass."""

    def test_create_post(self) -> None:
        """Test creating a social post."""
        now = datetime.now(UTC)
        post = SocialPost(
            content="Test content",
            platform="twitter",
            author="test_user",
            published_at=now,
        )
        assert post.content == "Test content"
        assert post.platform == "twitter"
        assert post.author == "test_user"
        assert post.published_at == now

    def test_post_with_all_fields(self) -> None:
        """Test post with all fields."""
        now = datetime.now(UTC)
        post = SocialPost(
            content="Test content about TEST",
            platform="twitter",
            author="test_user",
            published_at=now,
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
            symbols=["TEST"],
            url="https://twitter.com/test/status/123",
            relevance_score=Decimal("0.9"),
        )
        assert post.likes == 100
        assert post.shares == 50
        assert post.comments == 25
        assert post.followers == 10000
        assert post.symbols == ["TEST"]
        assert post.url == "https://twitter.com/test/status/123"
        assert post.relevance_score == Decimal("0.9")


class TestSocialSentimentAnalyzer:
    """Test SocialSentimentAnalyzer class."""

    def test_analyze_with_empty_posts(self) -> None:
        """Test analyzing with empty posts list."""
        analyzer = SocialSentimentAnalyzer()
        result = analyzer.analyze([], "TEST")
        assert isinstance(result, SocialSentimentResult)
        assert result.symbol == "TEST"
        assert result.post_count == 0
        assert result.overall_score == Decimal("0")
        assert result.sentiment_label == "NEUTRAL"
        assert result.total_engagement == 0

    def test_analyze_with_positive_post(self) -> None:
        """Test analyzing with positive post."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy TEST now! Strong bullish sentiment!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1
        assert result.overall_score > Decimal("0")
        assert result.sentiment_label in ["POSITIVE", "NEUTRAL"]
        assert result.total_engagement == 175

    def test_analyze_with_negative_post(self) -> None:
        """Test analyzing with negative post."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Sell TEST! Weak bearish sentiment!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1
        assert result.overall_score < Decimal("0")
        assert result.sentiment_label == "NEGATIVE"

    def test_analyze_with_mixed_posts(self) -> None:
        """Test analyzing with mixed positive and negative posts."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy TEST now!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            ),
            SocialPost(
                content="Sell TEST now!",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=80,
                shares=40,
                comments=20,
                followers=8000,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 2
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_analyze_filters_by_relevance(self) -> None:
        """Test that posts are filtered by relevance."""
        config = SocialSentimentConfig(min_relevance=Decimal("0.8"))
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST is great",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
                relevance_score=Decimal("0.9"),
            ),
            SocialPost(
                content="Low relevance post",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=50,
                shares=25,
                comments=10,
                followers=5000,
                symbols=["TEST"],
                relevance_score=Decimal("0.3"),
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1

    def test_analyze_filters_by_age(self) -> None:
        """Test that posts are filtered by age."""
        config = SocialSentimentConfig(max_age_hours=6)
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        old_time = now - timedelta(hours=12)
        posts = [
            SocialPost(
                content="Recent post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            ),
            SocialPost(
                content="Old post",
                platform="twitter",
                author="user2",
                published_at=old_time,
                likes=50,
                shares=25,
                comments=10,
                followers=5000,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1

    def test_analyze_filters_by_engagement(self) -> None:
        """Test that posts are filtered by engagement."""
        config = SocialSentimentConfig(min_engagement=50)
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="High engagement post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            ),
            SocialPost(
                content="Low engagement post",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=10,
                shares=5,
                comments=2,
                followers=1000,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1

    def test_analyze_filters_by_symbol(self) -> None:
        """Test that posts are filtered by symbol."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST is great!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            ),
            SocialPost(
                content="OTHER is great!",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=80,
                shares=40,
                comments=20,
                followers=8000,
                symbols=["OTHER"],
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 1

    def test_analyze_with_boost_factor(self) -> None:
        """Test analyzing with boost factor."""
        config = SocialSentimentConfig(boost_factor=Decimal("2.0"))
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy TEST now!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_score > Decimal("0")

    def test_analyze_batch_empty(self) -> None:
        """Test batch analyzing with empty dict."""
        analyzer = SocialSentimentAnalyzer()
        results = analyzer.analyze_batch({})
        assert results == {}

    def test_analyze_batch_multiple_symbols(self) -> None:
        """Test batch analyzing with multiple symbols."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts_by_symbol = {
            "TEST1": [
                SocialPost(
                    content="Buy TEST1 now!",
                    platform="twitter",
                    author="user1",
                    published_at=now,
                    likes=100,
                    shares=50,
                    comments=25,
                    followers=10000,
                    symbols=["TEST1"],
                )
            ],
            "TEST2": [
                SocialPost(
                    content="Sell TEST2 now!",
                    platform="twitter",
                    author="user2",
                    published_at=now,
                    likes=80,
                    shares=40,
                    comments=20,
                    followers=8000,
                    symbols=["TEST2"],
                )
            ],
        }
        results = analyzer.analyze_batch(posts_by_symbol)
        assert len(results) == 2
        assert "TEST1" in results
        assert "TEST2" in results

    def test_confidence_computation(self) -> None:
        """Test confidence computation."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy TEST now!",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
                relevance_score=Decimal("1.0"),
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert Decimal("0") <= result.overall_confidence <= Decimal("1")

    def test_aggregation_of_multiple_posts(self) -> None:
        """Test aggregation of multiple posts."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy TEST!" if i % 2 == 0 else "Sell TEST!",
                platform="twitter",
                author=f"user{i}",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
            for i in range(4)
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 4
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_text_excerpt_truncation(self) -> None:
        """Test that text excerpt is truncated."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        long_text = "A" * 200
        posts = [
            SocialPost(
                content=long_text,
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert len(result.posts[0].text_excerpt) <= 153

    def test_metadata_in_sentiment_score(self) -> None:
        """Test that metadata is included in sentiment score."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST is great",
                platform="twitter",
                author="test_user",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
                url="https://twitter.com/test/status/123",
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.posts[0].metadata["author"] == "test_user"
        assert result.posts[0].metadata["likes"] == "100"
        assert result.posts[0].metadata["shares"] == "50"
        assert result.posts[0].metadata["comments"] == "25"
        assert result.posts[0].metadata["followers"] == "10000"
        assert result.posts[0].metadata["url"] == "https://twitter.com/test/status/123"

    def test_score_clamping(self) -> None:
        """Test that scores are clamped to [-1, 1]."""
        config = SocialSentimentConfig(boost_factor=Decimal("10.0"))
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Buy buy buy strong long bullish rally",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_no_keywords_returns_neutral(self) -> None:
        """Test that text with no keywords returns neutral score."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="This is a regular post about TEST",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_score == Decimal("0")

    def test_custom_keywords(self) -> None:
        """Test with custom positive and negative keywords."""
        config = SocialSentimentConfig(
            positive_keywords=["custom_buy"],
            negative_keywords=["custom_sell"],
        )
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="custom_buy TEST",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_score > Decimal("0")

    def test_engagement_score_computation(self) -> None:
        """Test engagement score computation."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=200,
                shares=100,
                comments=50,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_confidence > Decimal("0.5")

    def test_follower_score_computation(self) -> None:
        """Test follower score computation."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST post",
                platform="twitter",
                author="influencer",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=1000000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_confidence > Decimal("0.5")

    def test_recency_score_computation(self) -> None:
        """Test recency score computation."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_confidence > Decimal("0.5")

    def test_zero_engagement(self) -> None:
        """Test with zero engagement."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=0,
                shares=0,
                comments=0,
                followers=10000,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.post_count == 0

    def test_zero_followers(self) -> None:
        """Test with zero followers."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=0,
                symbols=["TEST"],
            )
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.overall_confidence > Decimal("0")


class TestMockSocialSource:
    """Test MockSocialSource."""

    def test_fetch_posts_by_symbol(self) -> None:
        """Test fetching posts by symbol."""
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="TEST1 post",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST1"],
            ),
            SocialPost(
                content="TEST2 post",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=80,
                shares=40,
                comments=20,
                followers=8000,
                symbols=["TEST2"],
            ),
        ]
        source = MockSocialSource(posts)
        test1_posts = source.fetch_posts("TEST1")
        assert len(test1_posts) == 1
        assert test1_posts[0].symbols[0] == "TEST1"

    def test_fetch_posts_with_limit(self) -> None:
        """Test fetching posts with limit."""
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content=f"Post {i}",
                platform="twitter",
                author=f"user{i}",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            )
            for i in range(10)
        ]
        source = MockSocialSource(posts)
        limited_posts = source.fetch_posts("TEST", limit=3)
        assert len(limited_posts) == 3

    def test_add_post(self) -> None:
        """Test adding a post to the source."""
        now = datetime.now(UTC)
        source = MockSocialSource()
        post = SocialPost(
            content="New post",
            platform="twitter",
            author="user1",
            published_at=now,
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
            symbols=["TEST"],
        )
        source.add_post(post)
        posts = source.fetch_posts("TEST")
        assert len(posts) == 1

    def test_fetch_empty_source(self) -> None:
        """Test fetching from empty source."""
        source = MockSocialSource()
        posts = source.fetch_posts("TEST")
        assert posts == []

    def test_total_engagement_calculation(self) -> None:
        """Test total engagement calculation."""
        analyzer = SocialSentimentAnalyzer()
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Post 1",
                platform="twitter",
                author="user1",
                published_at=now,
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
                symbols=["TEST"],
            ),
            SocialPost(
                content="Post 2",
                platform="twitter",
                author="user2",
                published_at=now,
                likes=80,
                shares=40,
                comments=20,
                followers=8000,
                symbols=["TEST"],
            ),
        ]
        result = analyzer.analyze(posts, "TEST")
        assert result.total_engagement == (100 + 50 + 25) + (80 + 40 + 20) == 315
