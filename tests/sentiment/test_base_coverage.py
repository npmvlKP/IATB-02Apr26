"""
Comprehensive coverage tests for base.py.

Tests shared contracts and data models for sentiment analysis.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore, sentiment_label_from_score


class TestSentimentLabelFromScore:
    """Test sentiment label mapping from score."""

    def test_positive_score(self):
        """Test that positive score maps to POSITIVE."""
        label = sentiment_label_from_score(Decimal("0.5"))
        assert label == "POSITIVE"

    def test_strongly_positive_score(self):
        """Test that strongly positive score maps to POSITIVE."""
        label = sentiment_label_from_score(Decimal("1.0"))
        assert label == "POSITIVE"

    def test_negative_score(self):
        """Test that negative score maps to NEGATIVE."""
        label = sentiment_label_from_score(Decimal("-0.5"))
        assert label == "NEGATIVE"

    def test_strongly_negative_score(self):
        """Test that strongly negative score maps to NEGATIVE."""
        label = sentiment_label_from_score(Decimal("-1.0"))
        assert label == "NEGATIVE"

    def test_neutral_score_positive(self):
        """Test that small positive score maps to NEUTRAL."""
        label = sentiment_label_from_score(Decimal("0.04"))
        assert label == "NEUTRAL"

    def test_neutral_score_negative(self):
        """Test that small negative score maps to NEUTRAL."""
        label = sentiment_label_from_score(Decimal("-0.04"))
        assert label == "NEUTRAL"

    def test_zero_score(self):
        """Test that zero score maps to NEUTRAL."""
        label = sentiment_label_from_score(Decimal("0"))
        assert label == "NEUTRAL"


class TestSentimentScore:
    """Test SentimentScore dataclass."""

    def test_create_score(self):
        """Test creating sentiment score."""
        score = SentimentScore(
            source="vader",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            text_excerpt="Great news",
        )

        assert score.source == "vader"
        assert score.score == Decimal("0.5")
        assert score.label == "POSITIVE"

    def test_empty_source_raises_error(self):
        """Test that empty source raises ConfigError."""
        with pytest.raises(ConfigError, match="source cannot be empty"):
            SentimentScore(
                source="",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_empty_label_raises_error(self):
        """Test that empty label raises ConfigError."""
        with pytest.raises(ConfigError, match="label cannot be empty"):
            SentimentScore(
                source="vader",
                score=Decimal("0.5"),
                confidence=Decimal("0.8"),
                label="",
            )

    def test_score_out_of_range_raises_error(self):
        """Test that score > 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="score must be between -1 and 1"):
            SentimentScore(
                source="vader",
                score=Decimal("1.5"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_score_below_range_raises_error(self):
        """Test that score < -1 raises ConfigError."""
        with pytest.raises(ConfigError, match="score must be between -1 and 1"):
            SentimentScore(
                source="vader",
                score=Decimal("-1.5"),
                confidence=Decimal("0.8"),
                label="NEGATIVE",
            )

    def test_confidence_out_of_range_raises_error(self):
        """Test that confidence > 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            SentimentScore(
                source="vader",
                score=Decimal("0.5"),
                confidence=Decimal("1.5"),
                label="POSITIVE",
            )

    def test_negative_confidence_raises_error(self):
        """Test that negative confidence raises ConfigError."""
        with pytest.raises(ConfigError, match="confidence must be between 0 and 1"):
            SentimentScore(
                source="vader",
                score=Decimal("0.5"),
                confidence=Decimal("-0.1"),
                label="POSITIVE",
            )

    def test_non_finite_score_raises_error(self):
        """Test that non-finite score raises ConfigError."""
        with pytest.raises(ConfigError, match="must be finite"):
            SentimentScore(
                source="vader",
                score=Decimal("NaN"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
            )

    def test_score_with_metadata(self):
        """Test creating score with metadata."""
        score = SentimentScore(
            source="vader",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
            metadata={"key1": "value1", "key2": "value2"},
        )

        assert len(score.metadata) == 2
        assert score.metadata["key1"] == "value1"

    def test_score_with_default_metadata(self):
        """Test creating score with default empty metadata."""
        score = SentimentScore(
            source="vader",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )

        assert score.metadata == {}
