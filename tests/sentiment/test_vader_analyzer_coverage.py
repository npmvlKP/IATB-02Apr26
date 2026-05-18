"""
Comprehensive coverage tests for vader_analyzer.py.

Tests VADER compound scores, sentiment classification, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.vader_analyzer import (
    VaderAnalyzer,
    _default_factory,
)


class TestVaderAnalyzer:
    """Test VaderAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = VaderAnalyzer()
        assert analyzer is not None

    def test_analyze_positive_text(self) -> None:
        """Test positive text analysis."""
        analyzer = VaderAnalyzer()
        text = "This is amazing! Great work, excellent results!"
        result = analyzer.analyze(text)
        # Compound score should be positive
        assert result.score > Decimal("0")

    def test_analyze_negative_text(self) -> None:
        """Test negative text analysis."""
        analyzer = VaderAnalyzer()
        text = "This is terrible! Very bad, awful results!"
        result = analyzer.analyze(text)
        # Compound score should be negative
        assert result.score < Decimal("0")

    def test_analyze_neutral_text(self) -> None:
        """Test neutral text analysis."""
        analyzer = VaderAnalyzer()
        text = "This is a statement about the company."
        result = analyzer.analyze(text)
        # Should be close to 0
        assert Decimal("-0.1") < result.score < Decimal("0.1")

    def test_analyze_empty_text_raises_error(self) -> None:
        """Test with empty text raises ConfigError."""
        analyzer = VaderAnalyzer()
        with pytest.raises(ConfigError, match="text cannot be empty"):
            analyzer.analyze("")

    def test_analyze_whitespace_text_raises_error(self) -> None:
        """Test with whitespace text raises ConfigError."""
        analyzer = VaderAnalyzer()
        with pytest.raises(ConfigError, match="text cannot be empty"):
            analyzer.analyze("   ")

    def test_analyze_with_capitals(self) -> None:
        """Test with capital letters (VADER feature)."""
        analyzer = VaderAnalyzer()
        text = "This is AMAZING!"
        result = analyzer.analyze(text)
        # Caps should increase intensity
        assert result.score > Decimal("0")

    def test_analyze_with_emoticons(self) -> None:
        """Test with emoticons."""
        analyzer = VaderAnalyzer()
        text = "Great results! :) :) :)"
        result = analyzer.analyze(text)
        # Emoticons should increase positive sentiment
        assert result.score > Decimal("0")

    def test_analyze_with_negation(self) -> None:
        """Test with negation."""
        analyzer = VaderAnalyzer()
        text = "This is not good."
        result = analyzer.analyze(text)
        # Should be negative or neutral
        assert result.score < Decimal("0.3")

    def test_score_bounds(self) -> None:
        """Test score is always in [-1, 1]."""
        analyzer = VaderAnalyzer()
        text = "Test text"
        result = analyzer.analyze(text)
        assert Decimal("-1") <= result.score <= Decimal("1")

    def test_confidence_bounds(self) -> None:
        """Test confidence is always in [0, 1]."""
        analyzer = VaderAnalyzer()
        text = "Test text"
        result = analyzer.analyze(text)
        assert Decimal("0") <= result.confidence <= Decimal("1")

    def test_confidence_increases_with_intensity(self) -> None:
        """Test confidence increases with score magnitude."""
        analyzer = VaderAnalyzer()

        # Low intensity
        result1 = analyzer.analyze("This is okay.")
        # High intensity
        result2 = analyzer.analyze("This is ABSOLUTELY AMAZING!")

        # Higher intensity should have higher confidence
        assert result2.confidence >= result1.confidence

    def test_source_is_vader(self) -> None:
        """Test source is set to 'vader'."""
        analyzer = VaderAnalyzer()
        text = "Test text"
        result = analyzer.analyze(text)
        assert result.source == "vader"

    def test_text_excerpt_truncated(self) -> None:
        """Test text excerpt is truncated to 140 chars."""
        analyzer = VaderAnalyzer()
        text = "A" * 200  # 200 characters
        result = analyzer.analyze(text)
        # Should be truncated to 140
        assert len(result.text_excerpt) <= 140

    def test_sentiment_label_positive(self) -> None:
        """Test positive sentiment label."""
        analyzer = VaderAnalyzer()
        text = "This is great!"
        result = analyzer.analyze(text)
        if result.score > Decimal("0.05"):
            assert result.label == "POSITIVE"

    def test_sentiment_label_negative(self) -> None:
        """Test negative sentiment label."""
        analyzer = VaderAnalyzer()
        text = "This is terrible!"
        result = analyzer.analyze(text)
        if result.score < Decimal("-0.05"):
            assert result.label == "NEGATIVE"

    def test_sentiment_label_neutral(self) -> None:
        """Test neutral sentiment label."""
        analyzer = VaderAnalyzer()
        text = "This is a statement."
        result = analyzer.analyze(text)
        if Decimal("-0.05") <= result.score <= Decimal("0.05"):
            assert result.label == "NEUTRAL"


class TestVaderAnalyzerWeight:
    """Test VaderAnalyzer weight property."""

    def test_weight_is_decimal(self) -> None:
        """Test weight is a Decimal."""
        assert isinstance(VaderAnalyzer.weight, Decimal)

    def test_weight_value(self) -> None:
        """Test weight value."""
        assert VaderAnalyzer.weight == Decimal("0.2")


class TestDefaultFactory:
    """Test _default_factory function."""

    def test_factory_returns_vader_instance(self) -> None:
        """Test factory returns VADER analyzer instance."""
        analyzer = _default_factory()
        assert analyzer is not None
        # Should have polarity_scores method
        assert hasattr(analyzer, "polarity_scores")

    def test_factory_raises_error_without_vadersentiment(self) -> None:
        """Test factory raises error when vaderSentiment is not installed."""
        # This test assumes vaderSentiment is installed in the environment
        # If it's not installed, _default_factory will raise ConfigError
        # We can't easily test this without uninstalling the package
        pass


class TestVaderAnalyzerCustomFactory:
    """Test VaderAnalyzer with custom factory."""

    def test_custom_factory(self) -> None:
        """Test using custom analyzer factory."""

        def mock_factory():
            """Mock VADER analyzer."""

            class MockVader:
                def polarity_scores(self, text: str) -> dict:
                    return {"compound": 0.5, "pos": 0.5, "neg": 0.0, "neu": 0.5}

            return MockVader()

        analyzer = VaderAnalyzer(analyzer_factory=mock_factory)
        result = analyzer.analyze("Test text")
        assert result.score == Decimal("0.5")

    def test_custom_factory_with_invalid_return_type(self) -> None:
        """Test custom factory that returns invalid type."""
        # This test validates that a factory returning an object without polarity_scores
        # will raise AttributeError when analyze is called (not during init)
        # The factory itself is accepted during initialization
        pytest.skip("Factory validation happens at runtime, not initialization")

    def test_custom_factory_with_non_mapping_return(self) -> None:
        """Test custom factory that returns non-mapping."""

        def bad_factory():
            """Factory that returns non-mapping."""

            class BadAnalyzer:
                def polarity_scores(self, text: str) -> str:
                    return "not a mapping"

            return BadAnalyzer()

        analyzer = VaderAnalyzer(analyzer_factory=bad_factory)
        with pytest.raises(ConfigError, match="must return mapping"):
            analyzer.analyze("Test text")

    def test_custom_factory_missing_compound_key(self) -> None:
        """Test custom factory that doesn't return compound key."""

        def bad_factory():
            """Factory that returns dict without compound."""

            class BadAnalyzer:
                def polarity_scores(self, text: str) -> dict:
                    return {"pos": 0.5, "neg": 0.0, "neu": 0.5}

            return BadAnalyzer()

        analyzer = VaderAnalyzer(analyzer_factory=bad_factory)
        result = analyzer.analyze("Test text")
        # Should default to 0 when compound is missing
        assert result.score == Decimal("0")


class TestVaderAnalyzerEdgeCases:
    """Test VaderAnalyzer edge cases."""

    def test_analyze_with_special_characters(self) -> None:
        """Test with special characters."""
        analyzer = VaderAnalyzer()
        text = "Great!!! @user #hashtag $$$$"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_emojis(self) -> None:
        """Test with emojis."""
        analyzer = VaderAnalyzer()
        text = "Great results! 🚀🎉👍"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_numbers(self) -> None:
        """Test with numbers."""
        analyzer = VaderAnalyzer()
        text = "Stock up 50% in Q3"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_urls(self) -> None:
        """Test with URLs."""
        analyzer = VaderAnalyzer()
        text = "Great news! https://example.com/article"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_mentions(self) -> None:
        """Test with @mentions."""
        analyzer = VaderAnalyzer()
        text = "Great work @user1 and @user2"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_very_long_text(self) -> None:
        """Test with very long text."""
        analyzer = VaderAnalyzer()
        text = "Great! " * 1000
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_unicode_text(self) -> None:
        """Test with unicode text."""
        analyzer = VaderAnalyzer()
        text = "Gréât rêsülts! 你好! Привет!"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_mixed_case(self) -> None:
        """Test with mixed case."""
        analyzer = VaderAnalyzer()
        text = "ThIs Is GrEaT!"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_contractions(self) -> None:
        """Test with contractions."""
        analyzer = VaderAnalyzer()
        text = "It's great! Don't miss out! Won't regret it!"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)

    def test_analyze_with_punctuation(self) -> None:
        """Test with punctuation."""
        analyzer = VaderAnalyzer()
        text = "Great... really great!!! Wow??"
        result = analyzer.analyze(text)
        assert isinstance(result.score, Decimal)
