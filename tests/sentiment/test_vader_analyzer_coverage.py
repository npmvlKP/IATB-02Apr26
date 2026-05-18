"""
Comprehensive coverage tests for vader_analyzer.py.

Tests VADER compound scores, sentiment classification, and error paths.
"""

from decimal import Decimal

from iatb.sentiment.vader_analyzer import (
    VADERAnalyzer,
    classify_sentiment,
)


class TestClassifySentiment:
    """Test classify_sentiment function."""

    def test_classify_positive(self) -> None:
        """Test positive sentiment classification."""
        score = Decimal("0.7")
        classification = classify_sentiment(score)
        assert classification == "positive"

    def test_classify_negative(self) -> None:
        """Test negative sentiment classification."""
        score = Decimal("-0.5")
        classification = classify_sentiment(score)
        assert classification == "negative"

    def test_classify_neutral_high(self) -> None:
        """Test neutral sentiment (upper boundary)."""
        score = Decimal("0.05")
        classification = classify_sentiment(score)
        assert classification == "neutral"

    def test_classify_neutral_low(self) -> None:
        """Test neutral sentiment (lower boundary)."""
        score = Decimal("-0.05")
        classification = classify_sentiment(score)
        assert classification == "neutral"

    def test_classify_boundary_positive(self) -> None:
        """Test at positive boundary."""
        score = Decimal("0.051")
        classification = classify_sentiment(score)
        assert classification == "positive"

    def test_classify_boundary_negative(self) -> None:
        """Test at negative boundary."""
        score = Decimal("-0.051")
        classification = classify_sentiment(score)
        assert classification == "negative"


class TestVADERAnalyzer:
    """Test VADERAnalyzer class."""

    def test_analyzer_initialization(self) -> None:
        """Test analyzer initialization."""
        analyzer = VADERAnalyzer()
        assert analyzer is not None

    def test_analyze_positive_text(self) -> None:
        """Test positive text analysis."""
        analyzer = VADERAnalyzer()
        text = "This is amazing! Great work, excellent results!"
        result = analyzer.analyze(text)
        # Compound score should be positive
        assert result > Decimal("0")

    def test_analyze_negative_text(self) -> None:
        """Test negative text analysis."""
        analyzer = VADERAnalyzer()
        text = "This is terrible! Very bad, awful results!"
        result = analyzer.analyze(text)
        # Compound score should be negative
        assert result < Decimal("0")

    def test_analyze_neutral_text(self) -> None:
        """Test neutral text analysis."""
        analyzer = VADERAnalyzer()
        text = "This is a statement about the company."
        result = analyzer.analyze(text)
        # Should be close to 0
        assert Decimal("-0.1") < result < Decimal("0.1")

    def test_analyze_empty_text(self) -> None:
        """Test with empty text."""
        analyzer = VADERAnalyzer()
        text = ""
        result = analyzer.analyze(text)
        assert result == Decimal("0")

    def test_analyze_with_capitals(self) -> None:
        """Test with capital letters (VADER feature)."""
        analyzer = VADERAnalyzer()
        text = "This is AMAZING!"
        result = analyzer.analyze(text)
        # Caps should increase intensity
        assert result > Decimal("0")

    def test_analyze_with_emoticons(self) -> None:
        """Test with emoticons."""
        analyzer = VADERAnalyzer()
        text = "Great results! :) :) :)"
        result = analyzer.analyze(text)
        # Emoticons should increase positive sentiment
        assert result > Decimal("0")

    def test_get_components(self) -> None:
        """Test getting sentiment components."""
        analyzer = VADERAnalyzer()
        text = "This is great, not bad!"
        components = analyzer.get_components(text)
        assert "compound" in components
        assert "pos" in components
        assert "neg" in components
        assert "neu" in components

    def test_analyze_batch(self) -> None:
        """Test batch analysis."""
        analyzer = VADERAnalyzer()
        texts = [
            "Great results!",
            "Terrible outcome",
            "Neutral statement",
        ]
        results = analyzer.analyze_batch(texts)
        assert len(results) == 3
        # First positive, second negative, third neutral
        assert results[0] > results[1]
        assert Decimal("-0.1") < results[2] < Decimal("0.1")

    def test_normalize_score(self) -> None:
        """Test score normalization to [0, 1]."""
        analyzer = VADERAnalyzer()
        text = "Great!"
        compound = analyzer.analyze(text)
        normalized = analyzer.normalize_score(compound)
        # Should be in [0, 1]
        assert Decimal("0") <= normalized <= Decimal("1")
