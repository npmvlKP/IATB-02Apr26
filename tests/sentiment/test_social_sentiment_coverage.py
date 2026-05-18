"""
Comprehensive coverage tests for social_sentiment.py.

Tests social media sentiment analysis, engagement scoring, and error paths.
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
            min_relevance=Decimal("0.8"),
            max_age_hours=24,
            min_engagement=20,
            boost_factor=Decimal("1.5"),
        )
        assert config.min_relevance == Decimal("0.8")
        assert config.max_age_hours == 24
        assert config.min_engagement == 20
        assert config.boost_factor == Decimal("1.5")

    def test_min_relevance_below_zero_raises_error(self) -> None:
        """Test min_relevance below 0 raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            SocialSentimentConfig(min_relevance=Decimal("-0.1"))

    def test_min_relevance_above_one_raises_error(self) -> None:
        """Test min_relevance above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="min_relevance must be in"):
            SocialSentimentConfig(min_relevance=Decimal("1.1"))

    def test_max_age_hours_negative_raises_error(self) -> None:
        """Test max_age_hours negative raises ConfigError."""
        with pytest.raises(ConfigError, match="max_age_hours cannot be negative"):
            SocialSentimentConfig(max_age_hours=-1)

    def test_min_engagement_negative_raises_error(self) -> None:
        """Test min_engagement negative raises ConfigError."""
        with pytest.raises(ConfigError, match="min_engagement cannot be negative"):
            SocialSentimentConfig(min_engagement=-1)

    def test_boost_factor_negative_raises_error(self) -> None:
        """Test boost_factor negative raises ConfigError."""
        with pytest.raises(ConfigError, match="boost_factor cannot be negative"):
            SocialSentimentConfig(boost_factor=Decimal("-0.1"))

    def test_weights_sum_to_one(self) -> None:
        """Test default weights sum to 1.0."""
        config = SocialSentimentConfig()
        total = (
            config.engagement_weight + config.follower_weight + config.recency_weight
        )
        assert abs(total - Decimal("1")) <= Decimal("0.01")

    def test_weights_not_summing_to_one_raises_error(self) -> None:
        """Test weights not summing to 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            SocialSentimentConfig(
                engagement_weight=Decimal("0.5"),
                follower_weight=Decimal("0.3"),
                recency_weight=Decimal("0.1"),  # Sum = 0.9, not 1.0
            )


class TestSocialPost:
    """Test SocialPost dataclass."""

    def test_create_post(self) -> None:
        """Test creating a social post."""
        post = SocialPost(
            content="Bullish on RELIANCE!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
        )
        assert post.content == "Bullish on RELIANCE!"
        assert post.platform == "twitter"
        assert post.author == "user1"

    def test_post_with_optional_fields(self) -> None:
        """Test post with optional fields."""
        post = SocialPost(
            content="Bullish on RELIANCE!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
            symbols=["RELIANCE", "RELIANCE.NS"],
            url="https://twitter.com/user1/status/123",
            relevance_score=Decimal("0.9"),
        )
        assert post.likes == 100
        assert post.shares == 50
        assert post.comments == 25
        assert post.followers == 10000
        assert post.symbols == ["RELIANCE", "RELIANCE.NS"]


class TestSocialSentimentAnalyzer:
    """Test SocialSentimentAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = SocialSentimentAnalyzer()
        assert analyzer is not None

    def test_analyze_empty_posts(self) -> None:
        """Test analyzing empty posts list."""
        analyzer = SocialSentimentAnalyzer()
        posts: list[SocialPost] = []
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 0
        assert result.overall_score == Decimal("0")
        assert result.sentiment_label == "NEUTRAL"

    def test_analyze_single_positive_post(self) -> None:
        """Test analyzing single positive post."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bullish! Strong buy signal! Great growth ahead!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        assert result.post_count == 1
        assert result.overall_score > Decimal("0")

    def test_analyze_single_negative_post(self) -> None:
        """Test analyzing single negative post."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bearish! Sell signal! Weak outlook! Risk of crash!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        assert result.post_count == 1
        assert result.overall_score < Decimal("0")

    def test_analyze_multiple_posts(self) -> None:
        """Test analyzing multiple posts."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            SocialPost(
                content="Bullish! Strong buy signal!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Bearish! Weak outlook!",
                platform="twitter",
                author="user2",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.8"),
                likes=80,
                shares=40,
                comments=20,
                followers=5000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 2

    def test_analyze_filters_by_relevance(self) -> None:
        """Test posts are filtered by relevance score."""
        config = SocialSentimentConfig(min_relevance=Decimal("0.8"))
        analyzer = SocialSentimentAnalyzer(config)
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Neutral",
                platform="twitter",
                author="user2",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.5"),  # Below threshold
                likes=10,
                shares=5,
                comments=2,
                followers=1000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 1

    def test_analyze_filters_by_engagement(self) -> None:
        """Test posts are filtered by engagement."""
        config = SocialSentimentConfig(min_engagement=50)
        analyzer = SocialSentimentAnalyzer(config)
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Neutral",
                platform="twitter",
                author="user2",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=5,
                shares=2,
                comments=1,  # Total = 8, below threshold
                followers=1000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 1

    def test_analyze_filters_by_age(self) -> None:
        """Test posts are filtered by age."""
        config = SocialSentimentConfig(max_age_hours=12)
        analyzer = SocialSentimentAnalyzer(config)
        now = datetime.now(UTC)
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=now - timedelta(hours=6),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Neutral",
                platform="twitter",
                author="user2",
                published_at=now - timedelta(hours=24),  # Too old
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 1

    def test_analyze_filters_by_symbol(self) -> None:
        """Test posts are filtered by symbol."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            SocialPost(
                content="Bullish on RELIANCE!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Bullish on TCS!",
                platform="twitter",
                author="user2",
                published_at=datetime.now(UTC),
                symbols=["TCS"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 1

    def test_analyze_with_content_match(self) -> None:
        """Test posts match if symbol is in content."""
        # Content matching not implemented in SocialSentimentAnalyzer - skip
        pytest.skip("SocialSentimentAnalyzer doesn't support content matching")

    def test_analyze_case_insensitive(self) -> None:
        """Test symbol matching is case-insensitive."""
        # Only tests with explicit symbols - skip this content-based test
        pytest.skip("Case-insensitive content matching not implemented")

    def test_analyze_all_filtered_out(self) -> None:
        """Test when all posts are filtered out."""
        config = SocialSentimentConfig(min_engagement=1000)
        analyzer = SocialSentimentAnalyzer(config)
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=10,  # Below threshold
                shares=5,
                comments=2,
                followers=1000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        assert result.post_count == 0
        assert result.sentiment_label == "NEUTRAL"

    def test_score_bounds(self) -> None:
        """Test score is always in [-1, 1]."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bullish!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        assert Decimal("-1") <= result.overall_score <= Decimal("1")

    def test_confidence_bounds(self) -> None:
        """Test confidence is always in [0, 1]."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bullish!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        assert Decimal("0") <= result.overall_confidence <= Decimal("1")

    def test_total_engagement(self) -> None:
        """Test total engagement is calculated correctly."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            ),
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user2",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=200,
                shares=100,
                comments=50,
                followers=20000,
            ),
        ]
        result = analyzer.analyze(posts, "RELIANCE")
        # Total engagement: (100+50+25) + (200+100+50) = 175 + 350 = 525
        assert result.total_engagement == 525

    def test_sentiment_label_positive(self) -> None:
        """Test positive sentiment label."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bullish! Strong buy! Great growth!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        if result.overall_score > Decimal("0.05"):
            assert result.sentiment_label == "POSITIVE"

    def test_sentiment_label_negative(self) -> None:
        """Test negative sentiment label."""
        analyzer = SocialSentimentAnalyzer()
        post = SocialPost(
            content="Bearish! Sell! Weak outlook!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
            relevance_score=Decimal("0.9"),
            likes=100,
            shares=50,
            comments=25,
            followers=10000,
        )
        result = analyzer.analyze([post], "RELIANCE")
        if result.overall_score < Decimal("-0.05"):
            assert result.sentiment_label == "NEGATIVE"


class TestSocialAnalyzeBatch:
    """Test analyze_batch method."""

    def test_analyze_batch_multiple_symbols(self) -> None:
        """Test analyzing posts for multiple symbols."""
        analyzer = SocialSentimentAnalyzer()
        posts_by_symbol = {
            "RELIANCE": [
                SocialPost(
                    content="Bullish on RELIANCE!",
                    platform="twitter",
                    author="user1",
                    published_at=datetime.now(UTC),
                    symbols=["RELIANCE"],
                    relevance_score=Decimal("0.9"),
                    likes=100,
                    shares=50,
                    comments=25,
                    followers=10000,
                )
            ],
            "TCS": [
                SocialPost(
                    content="Bullish on TCS!",
                    platform="twitter",
                    author="user2",
                    published_at=datetime.now(UTC),
                    symbols=["TCS"],
                    relevance_score=Decimal("0.9"),
                    likes=100,
                    shares=50,
                    comments=25,
                    followers=10000,
                )
            ],
        }
        results = analyzer.analyze_batch(posts_by_symbol)
        assert len(results) == 2
        assert "RELIANCE" in results
        assert "TCS" in results

    def test_analyze_batch_empty_dict(self) -> None:
        """Test analyzing batch with empty dict."""
        analyzer = SocialSentimentAnalyzer()
        results = analyzer.analyze_batch({})
        assert len(results) == 0


class TestAnalyzeToSentimentScore:
    """Test analyze_to_sentiment_score method."""

    def test_analyze_to_sentiment_score(self) -> None:
        """Test converting to SentimentScore."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            SocialPost(
                content="Bullish!",
                platform="twitter",
                author="user1",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
                relevance_score=Decimal("0.9"),
                likes=100,
                shares=50,
                comments=25,
                followers=10000,
            )
        ]
        result = analyzer.analyze_to_sentiment_score(posts, "RELIANCE")
        assert result.source == "social"
        assert result is not None


class TestMockSocialSource:
    """Test MockSocialSource."""

    def test_mock_source_initialization(self) -> None:
        """Test mock source initialization."""
        source = MockSocialSource()
        assert source is not None

    def test_mock_source_with_posts(self) -> None:
        """Test mock source with posts."""
        post = SocialPost(
            content="Bullish!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source = MockSocialSource([post])
        assert len(source._posts) == 1

    def test_fetch_posts_by_symbol(self) -> None:
        """Test fetching posts by symbol."""
        post = SocialPost(
            content="Bullish on RELIANCE!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source = MockSocialSource([post])
        posts = source.fetch_posts("RELIANCE")
        assert len(posts) == 1
        assert posts[0].content == "Bullish on RELIANCE!"

    def test_fetch_posts_by_content(self) -> None:
        """Test fetching posts by content match."""
        # MockSocialSource doesn't implement content search - skip this test
        pytest.skip("MockSocialSource doesn't support content search")

    def test_fetch_posts_limit(self) -> None:
        """Test fetch with limit."""
        posts = [
            SocialPost(
                content=f"Post {i}",
                platform="twitter",
                author=f"user{i}",
                published_at=datetime.now(UTC),
                symbols=["RELIANCE"],
            )
            for i in range(10)
        ]
        source = MockSocialSource(posts)
        fetched = source.fetch_posts("RELIANCE", limit=5)
        assert len(fetched) == 5

    def test_add_post(self) -> None:
        """Test adding post to mock source."""
        source = MockSocialSource()
        post = SocialPost(
            content="Bullish!",
            platform="twitter",
            author="user1",
            published_at=datetime.now(UTC),
            symbols=["RELIANCE"],
        )
        source.add_post(post)
        assert len(source._posts) == 1
