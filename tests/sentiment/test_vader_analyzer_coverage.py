"""Tests for sentiment/vader_analyzer.py — VADER compound scores."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore
from iatb.sentiment.vader_analyzer import VaderAnalyzer


def _vader_factory(compound: float = 0.5) -> MagicMock:
    analyzer = MagicMock()
    analyzer.polarity_scores.return_value = {
        "compound": compound,
        "neg": 0.0,
        "neu": 0.5,
        "pos": 0.5,
    }
    return analyzer


class TestVaderAnalyzer:
    def test_positive_text(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.85))
        result = va.analyze("This is great and wonderful")
        assert isinstance(result, SentimentScore)
        assert result.source == "vader"
        assert result.score > Decimal("0")

    def test_negative_text(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(-0.75))
        result = va.analyze("This is terrible and awful")
        assert result.score < Decimal("0")

    def test_neutral_text(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.0))
        result = va.analyze("The market opened today")
        assert result.label == "NEUTRAL"

    def test_empty_text_raises(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.0))
        with pytest.raises(ConfigError, match="text cannot be empty"):
            va.analyze("")

    def test_whitespace_text_raises(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.0))
        with pytest.raises(ConfigError, match="text cannot be empty"):
            va.analyze("   ")

    def test_non_mapping_return_raises(self) -> None:
        bad_analyzer = MagicMock()
        bad_analyzer.polarity_scores.return_value = "not_a_mapping"
        va = VaderAnalyzer(analyzer_factory=lambda: bad_analyzer)
        with pytest.raises(ConfigError, match="must return mapping"):
            va.analyze("test")

    def test_score_bounded(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(2.0))
        result = va.analyze("extreme positive")
        assert result.score <= Decimal("1")

    def test_negative_score_bounded(self) -> None:
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(-2.0))
        result = va.analyze("extreme negative")
        assert result.score >= Decimal("-1")

    def test_confidence_increases_with_magnitude(self) -> None:
        va_low = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.1))
        va_high = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.9))
        low = va_low.analyze("mild positive")
        high = va_high.analyze("strong positive")
        assert high.confidence > low.confidence

    def test_text_excerpt_truncated(self) -> None:
        long_text = "x" * 200
        va = VaderAnalyzer(analyzer_factory=lambda: _vader_factory(0.0))
        result = va.analyze(long_text)
        assert len(result.text_excerpt) <= 140

    def test_weight_attribute(self) -> None:
        assert VaderAnalyzer.weight == Decimal("0.2")

    def test_default_compound_zero(self) -> None:
        analyzer = MagicMock()
        analyzer.polarity_scores.return_value = {}
        va = VaderAnalyzer(analyzer_factory=lambda: analyzer)
        result = va.analyze("test")
        assert result.score == Decimal("0")

    def test_missing_compound_key_defaults_zero(self) -> None:
        analyzer = MagicMock()
        analyzer.polarity_scores.return_value = {"neg": 0.1, "pos": 0.9}
        va = VaderAnalyzer(analyzer_factory=lambda: analyzer)
        result = va.analyze("test")
        assert result.score == Decimal("0")
