"""
Comprehensive coverage tests for social_sentiment.py.

Tests social media sentiment analysis, post parsing, and error paths.
"""

from decimal import Decimal

from iatb.sentiment.social_sentiment import (
    SocialSentimentAnalyzer,
    parse_post,
)


class TestParsePost:
    """Test parse_post function."""

    def test_parse_basic_post(self) -> None:
        """Test basic post parsing."""
        post = "Great earnings! 🚀 $AAPL up 10%"
        result = parse_post(post)
        assert result is not None
        assert "earnings" in result.lower() or "up" in result.lower()

    def test_parse_post_with_hashtags(self) -> None:
        """Test post with hashtags."""
        post = "Stock soaring! #earnings #growth #trading"
        result = parse_post(post)
        # Should extract meaningful content
        assert len(result) > 0

    def test_parse_post_with_mentions(self) -> None:
        """Test post with user mentions."""
        post = "@user1 agrees with the bullish outlook for $AAPL"
        result = parse_post(post)
        assert len(result) > 0

    def test_parse_post_empty(self) -> None:
        """Test with empty post."""
        post = ""
        result = parse_post(post)
        assert result == ""

    def test_parse_post_special_chars(self) -> None:
        """Test post with special characters."""
        post = "🚀📈 Great news! Earnings beat by 20% 💰"
        result = parse_post(post)
        assert len(result) > 0


class TestSocialSentimentAnalyzer:
    """Test SocialSentimentAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = SocialSentimentAnalyzer()
        assert analyzer is not None

    def test_analyze_positive_post(self) -> None:
        """Test positive social sentiment."""
        analyzer = SocialSentimentAnalyzer()
        post = "Bullish! Strong earnings, great growth ahead! 🚀"
        result = analyzer.analyze(post)
        assert result > Decimal("0.5")

    def test_analyze_negative_post(self) -> None:
        """Test negative social sentiment."""
        analyzer = SocialSentimentAnalyzer()
        post = "Bearish! Earnings miss, weak guidance expected 😞"
        result = analyzer.analyze(post)
        assert result < Decimal("0.5")

    def test_analyze_neutral_post(self) -> None:
        """Test neutral social sentiment."""
        analyzer = SocialSentimentAnalyzer()
        post = "Company reports earnings today."
        result = analyzer.analyze(post)
        assert Decimal("0.4") < result < Decimal("0.6")

    def test_analyze_empty_post(self) -> None:
        """Test with empty post."""
        analyzer = SocialSentimentAnalyzer()
        post = ""
        result = analyzer.analyze(post)
        # Should return neutral
        assert result == Decimal("0.5")

    def test_analyze_with_emoji_weighting(self) -> None:
        """Test analysis with emoji weighting."""
        analyzer = SocialSentimentAnalyzer(weight_emojis=True)
        post = "Great news! 🚀🚀🚀"
        result = analyzer.analyze(post)
        assert result > Decimal("0.5")

    def test_analyze_batch_posts(self) -> None:
        """Test batch post analysis."""
        analyzer = SocialSentimentAnalyzer()
        posts = [
            "Bullish on $AAPL! 🚀",
            "Bearish outlook, weak demand",
            "Neutral, waiting for earnings",
        ]
        results = analyzer.analyze_batch(posts)
        assert len(results) == 3
        # First should be positive, second negative
        assert results[0] > results[1]

    def test_analyze_with_cashtag(self) -> None:
        """Test analysis with stock ticker."""
        analyzer = SocialSentimentAnalyzer()
        post = "$TSLA up 5% on strong delivery numbers"
        result = analyzer.analyze(post)
        assert result > Decimal("0.5")
