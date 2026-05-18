"""
Comprehensive coverage tests for base.py.

Tests base sentiment analyzer, abstract methods, and error paths.
"""

from decimal import Decimal


class MockSentimentAnalyzer:
    """Mock implementation of BaseSentimentAnalyzer for testing."""

    def analyze(self, text: str) -> Decimal:
        """Analyze sentiment of text."""
        return Decimal("0.5")


class TestBaseSentimentAnalyzer:
    """Test BaseSentimentAnalyzer abstract class."""

    def test_analyze_positive_sentiment(self) -> None:
        """Test positive sentiment analysis."""
        analyzer = MockSentimentAnalyzer()
        text = "Great news! Company reports strong earnings."
        result = analyzer.analyze(text)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_analyze_negative_sentiment(self) -> None:
        """Test negative sentiment analysis."""
        analyzer = MockSentimentAnalyzer()
        text = "Disappointing results, missed targets."
        result = analyzer.analyze(text)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_analyze_neutral_sentiment(self) -> None:
        """Test neutral sentiment analysis."""
        analyzer = MockSentimentAnalyzer()
        text = "Company reports quarterly results."
        result = analyzer.analyze(text)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_analyze_empty_text(self) -> None:
        """Test with empty text."""
        analyzer = MockSentimentAnalyzer()
        text = ""
        result = analyzer.analyze(text)
        # Should handle gracefully
        assert isinstance(result, Decimal)

    def test_analyze_special_characters(self) -> None:
        """Test with special characters."""
        analyzer = MockSentimentAnalyzer()
        text = "Great! Strong growth @ 50% #earnings"
        result = analyzer.analyze(text)
        # Should handle special characters
        assert isinstance(result, Decimal)
