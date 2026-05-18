"""
Comprehensive coverage tests for social_sentiment.py.

Tests social media sentiment analyzer for financial instruments.
"""

from datetime import UTC, datetime
from decimal import Decimal

from iatb.sentiment.social_sentiment import (
    MockSocialSource,
    SocialPost,
    SocialSentimentAnalyzer,
    SocialSentimentConfig,
    SocialSentimentResult,
)


class TestSocialPost:
    """Test social post dataclass."""

    def test_create_post(self):
        """Test creating social post."""
        post = SocialPost(
            content="Great company",
            platform="twitter",
            author="@testuser",
            published_at=datetime.now(UTC),
            likes=100,
            shares=10,
            symbols=["TEST"],
        )

        assert post.platform == "twitter"
        assert post.symbols == ["TEST"]


class TestSocialSentimentConfig:
    """Test social sentiment configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SocialSentimentConfig()
        assert config.min_relevance == Decimal("0.5")
        assert config.max_age_hours == 12
        assert config.min_engagement == 10

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SocialSentimentConfig(
            min_relevance=Decimal("0.7"),
            max_age_hours=6,
            min_engagement=50,
        )
        assert config.min_relevance == Decimal("0.7")

    def test_weights_sum_to_one(self):
        """Test that weights sum to 1.0."""
        config = SocialSentimentConfig()
        total = (
            config.engagement_weight + config.follower_weight + config.recency_weight
        )
        assert total == Decimal("1")


class TestSocialSentimentAnalyzer:
    """Test social sentiment analyzer."""

    def test_analyze_single_post(self):
        """Test analyzing single post."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Amazing growth! Strong buy signal",
            platform="twitter",
            author="@testuser",
            published_at=datetime.now(UTC),
            likes=100,
            shares=10,
            symbols=["TEST"],
        )

        result = analyzer.analyze([post], "TEST")

        assert isinstance(result, SocialSentimentResult)
        assert result.symbol == "TEST"
        assert result.post_count == 1

    def test_analyze_multiple_posts(self):
        """Test analyzing multiple posts."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            SocialPost(
                content="Great news",
                platform="twitter",
                author="@user1",
                published_at=datetime.now(UTC),
                likes=100,
                shares=10,
                symbols=["TEST"],
            ),
            SocialPost(
                content="Bad news",
                platform="twitter",
                author="@user2",
                published_at=datetime.now(UTC),
                likes=50,
                shares=5,
                symbols=["TEST"],
            ),
        ]

        result = analyzer.analyze(posts, "TEST")

        assert result.post_count == 2
        assert result.symbol == "TEST"

    def test_analyze_empty_posts_returns_empty(self):
        """Test that empty posts list returns empty result."""
        analyzer = SocialSentimentAnalyzer()
        result = analyzer.analyze([], "TEST")

        assert result.post_count == 0
        assert result.overall_score == Decimal("0")

    def test_analyze_to_sentiment_score(self):
        """Test analyzing and returning SentimentScore."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Great company",
            platform="twitter",
            author="@user",
            published_at=datetime.now(UTC),
            likes=100,
            shares=10,
            symbols=["TEST"],
        )

        result = analyzer.analyze_to_sentiment_score([post], "TEST")

        assert result.source == "social"
        assert "social sentiment" in result.text_excerpt.lower()

    def test_analyze_batch(self):
        """Test analyzing multiple symbols."""
        analyzer = SocialSentimentAnalyzer()
        posts_by_symbol = {
            "TEST1": [
                SocialPost(
                    content="Good",
                    platform="twitter",
                    author="@u1",
                    published_at=datetime.now(UTC),
                    likes=100,
                    symbols=["TEST1"],
                )
            ],
            "TEST2": [
                SocialPost(
                    content="Bad",
                    platform="twitter",
                    author="@u2",
                    published_at=datetime.now(UTC),
                    likes=50,
                    symbols=["TEST2"],
                )
            ],
        }

        results = analyzer.analyze_batch(posts_by_symbol)

        assert len(results) == 2
        assert "TEST1" in results
        assert "TEST2" in results


class TestSocialSentimentResult:
    """Test social sentiment result dataclass."""

    def test_create_result(self):
        """Test creating sentiment result."""
        result = SocialSentimentResult(
            symbol="TEST",
            overall_score=Decimal("0.5"),
            overall_confidence=Decimal("0.8"),
            post_count=10,
            total_engagement=500,
            sentiment_label="POSITIVE",
            posts=[],
            timestamp=datetime.now(UTC),
        )

        assert result.symbol == "TEST"
        assert result.total_engagement == 500


class TestMockSocialSource:
    """Test mock social source."""

    def test_fetch_posts(self):
        """Test fetching posts from mock source."""
        post = SocialPost(
            content="Test",
            platform="twitter",
            author="@user",
            published_at=datetime.now(UTC),
            symbols=["TEST"],
        )
        source = MockSocialSource([post])

        posts = source.fetch_posts("TEST")

        assert len(posts) == 1
        assert posts[0].content == "Test"

    def test_add_post(self):
        """Test adding post to mock source."""
        source = MockSocialSource()
        post = SocialPost(
            content="New",
            platform="twitter",
            author="@user",
            published_at=datetime.now(UTC),
            symbols=["TEST"],
        )

        source.add_post(post)
        posts = source.fetch_posts("TEST")

        assert len(posts) == 1
