"""
Comprehensive coverage tests for base.py.

Tests base sentiment analyzer, abstract methods, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import (
    SentimentAnalyzer,
    SentimentScore,
    _as_decimal,
    sentiment_label_from_score,
)


class TestAsDecimal:
    """Test _as_decimal helper function."""

    def test_string_to_decimal(self) -> None:
        """Test converting string to decimal."""
        result = _as_decimal("0.5", "test_field")
        assert result == Decimal("0.5")

    def test_float_to_decimal(self) -> None:
        """Test converting float to decimal."""
        result = _as_decimal(0.5, "test_field")
        assert result == Decimal("0.5")

    def test_decimal_to_decimal(self) -> None:
        """Test passing decimal returns same."""
        result = _as_decimal(Decimal("0.5"), "test_field")
        assert result == Decimal("0.5")

    def test_integer_to_decimal(self) -> None:
        """Test converting integer to decimal."""
        result = _as_decimal(5, "test_field")
        assert result == Decimal("5")

    def test_negative_value(self) -> None:
        """Test negative value."""
        result = _as_decimal("-0.5", "test_field")
        assert result == Decimal("-0.5")

    def test_invalid_string_raises_error(self) -> None:
        """Test invalid string raises ConfigError."""
        with pytest.raises(ConfigError, match="must be decimal-compatible"):
            _as_decimal("invalid", "test_field")

    def test_none_raises_error(self) -> None:
        """Test None raises ConfigError."""
        with pytest.raises(ConfigError, match="must be decimal-compatible"):
            _as_decimal(None, "test_field")

    def test_infinity_raises_error(self) -> None:
        """Test infinity raises ConfigError."""
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal(Decimal("inf"), "test_field")

    def test_nan_raises_error(self) -> None:
        """Test NaN raises ConfigError."""
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal(Decimal("nan"), "test_field")

    def test_negative_infinity_raises_error(self) -> None:
        """Test negative infinity raises ConfigError."""
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal(Decimal("-inf"), "test_field")


class TestSentimentLabelFromScore:
    """Test sentiment_label_from_score function."""

    def test_positive_sentiment(self) -> None:
        """Test positive sentiment."""
        result = sentiment_label_from_score(Decimal("0.1"))
        assert result == "POSITIVE"

    def test_negative_sentiment(self) -> None:
        """Test negative sentiment."""
        result = sentiment_label_from_score(Decimal("-0.1"))
        assert result == "NEGATIVE"

    def test_neutral_sentiment_upper_boundary(self) -> None:
        """Test neutral sentiment at upper boundary."""
        result = sentiment_label_from_score(Decimal("0.04"))
        assert result == "NEUTRAL"

    def test_neutral_sentiment_lower_boundary(self) -> None:
        """Test neutral at lower boundary."""
        result = sentiment_label_from_score(Decimal("-0.04"))
        assert result == "NEUTRAL"

    def test_neutral_sentiment_zero(self) -> None:
        """Test neutral at zero."""
        result = sentiment_label_from_score(Decimal("0"))
        assert result == "NEUTRAL"

    def test_strongly_positive(self) -> None:
        """Test strongly positive."""
        result = sentiment_label_from_score(Decimal("0.9"))
        assert result == "POSITIVE"

    def test_strongly_negative(self) -> None:
        """Test strongly negative."""
        result = sentiment_label_from_score(Decimal("-0.9"))
        assert result == "NEGATIVE"

    def test_boundary_positive(self) -> None:
        """Test at positive boundary (0.051)."""
        result = sentiment_label_from_score(Decimal("0.051"))
        assert result == "POSITIVE"

    def test_boundary_negative(self) -> None:
        """Test at negative boundary (-0.051)."""
        result = sentiment_label_from_score(Decimal("-0.051"))
        assert result == "NEGATIVE"


class TestSentimentScore:
    """Test SentimentScore dataclass."""

    def test_valid_sentiment_score(self) -> None:
        """Test creating valid sentiment score."""
        score = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
        assert score.source == "test"
        assert score.score == Decimal("0.5")
        assert score.confidence == Decimal("0.8")
        assert score.label == "POSITIVE"

    def test_empty_source_raises_error(self) -> None:
        """Test empty source raises ConfigError."""
        with pytest.raises(ConfigError, match="source cannot be empty"):
            SentimentScore(
                source="",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_whitespace_source_raises_error(self) -> None:
        """Test whitespace-only source raises ConfigError."""
        with pytest.raises(ConfigError, match="source cannot be empty"):
            SentimentScore(
                source="   ",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_empty_label_raises_error(self) -> None:
        """Test empty label raises ConfigError."""
        with pytest.raises(ConfigError, match="label cannot be empty"):
            SentimentScore(
                source="test",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="",
            )

    def test_whitespace_label_raises_error(self) -> None:
        """Test whitespace-only label raises ConfigError."""
        with pytest.raises(ConfigError, match="label cannot be empty"):
            SentimentScore(
                source="test",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="   ",
            )

    def test_score_above_max_raises_error(self) -> None:
        """Test score above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="score must be between -1 and 1"):
            SentimentScore(
                source="test",
                score=Decimal("1.1"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_score_below_min_raises_error(self) -> None:
        """Test score below -1 raises ConfigError."""
        with pytest.raises(ConfigError, match="score must be between -1 and 1"):
            SentimentScore(
                source="test",
                score=Decimal("-1.1"),
                confidence=Decimal("0.8"),
                label="NEGATIVE",
            )

    def test_confidence_above_max_raises_error(self) -> None:
        """Test confidence above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            SentimentScore(
                source="test",
                score=Decimal("0.5"),
                confidence=Decimal("1.1"),
                label="POSITIVE",
            )

    def test_confidence_below_min_raises_error(self) -> None:
        """Test confidence below 0 raises ConfigError."""
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            SentimentScore(
                source="test",
                score=Decimal("0.5"),
                confidence=Decimal("-0.1"),
                label="POSITIVE",
            )

    def test_boundary_score_values(self) -> None:
        """Test boundary score values."""
        # Test score = 1
        score1 = SentimentScore(
            source="test",
            score=Decimal("1"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
        assert score1.score == Decimal("1")

        # Test score = -1
        score2 = SentimentScore(
            source="test",
            score=Decimal("-1"),
            confidence=Decimal("0.8"),
            label="NEGATIVE",
        )
        assert score2.score == Decimal("-1")

    def test_boundary_confidence_values(self) -> None:
        """Test boundary confidence values."""
        # Test confidence = 0
        score1 = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0"),
            label="POSITIVE",
        )
        assert score1.confidence == Decimal("0")

        # Test confidence = 1
        score2 = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("1"),
            label="POSITIVE",
        )
        assert score2.confidence == Decimal("1")

    def test_with_text_excerpt(self) -> None:
        """Test with text excerpt."""
        score = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            text_excerpt="Great earnings!",
        )
        assert score.text_excerpt == "Great earnings!"

    def test_with_metadata(self) -> None:
        """Test with metadata."""
        metadata = {"author": "John", "timestamp": "2024-01-01"}
        score = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            metadata=metadata,
        )
        assert score.metadata == {"author": "John", "timestamp": "2024-01-01"}

    def test_metadata_keys_converted_to_strings(self) -> None:
        """Test metadata keys are converted to strings."""
        metadata = {123: "value", "key": 456}
        score = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            metadata=metadata,
        )
        # Keys should be strings
        assert "123" in score.metadata
        assert "key" in score.metadata
        assert score.metadata["123"] == "value"
        assert score.metadata["key"] == "456"

    def test_score_auto_conversion(self) -> None:
        """Test score is auto-converted to decimal."""
        score = SentimentScore(
            source="test",
            score="0.5",  # String
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
        assert isinstance(score.score, Decimal)
        assert score.score == Decimal("0.5")

    def test_confidence_auto_conversion(self) -> None:
        """Test confidence is auto-converted to decimal."""
        score = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=0.8,  # Float
            label="POSITIVE",
        )
        assert isinstance(score.confidence, Decimal)
        assert score.confidence == Decimal("0.8")

    def test_invalid_score_type_raises_error(self) -> None:
        """Test invalid score type raises ConfigError."""
        with pytest.raises(ConfigError, match="must be decimal-compatible"):
            SentimentScore(
                source="test",
                score=[],
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_invalid_confidence_type_raises_error(self) -> None:
        """Test invalid confidence type raises ConfigError."""
        with pytest.raises(ConfigError, match="must be decimal-compatible"):
            SentimentScore(
                source="test",
                score=Decimal("0.5"),
                confidence={},
                label="POSITIVE",
            )


class TestSentimentAnalyzer:
    """Test SentimentAnalyzer Protocol."""

    def test_protocol_compliance(self) -> None:
        """Test that protocol is properly defined."""
        # Protocol should have analyze method
        assert hasattr(SentimentAnalyzer, "analyze")
