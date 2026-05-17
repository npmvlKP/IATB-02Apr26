"""Tests for sentiment/base.py — base sentiment analyzer."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import (
    SentimentAnalyzer,
    SentimentScore,
    _as_decimal,
    sentiment_label_from_score,
)


class TestSentimentLabelFromScore:
    def test_positive(self) -> None:
        assert sentiment_label_from_score(Decimal("0.1")) == "POSITIVE"

    def test_negative(self) -> None:
        assert sentiment_label_from_score(Decimal("-0.1")) == "NEGATIVE"

    def test_neutral(self) -> None:
        assert sentiment_label_from_score(Decimal("0")) == "NEUTRAL"

    def test_boundary_positive(self) -> None:
        assert sentiment_label_from_score(Decimal("0.05")) == "POSITIVE"

    def test_boundary_negative(self) -> None:
        assert sentiment_label_from_score(Decimal("-0.05")) == "NEGATIVE"


class TestAsDecimal:
    def test_valid_integer(self) -> None:
        assert _as_decimal(5, "field") == Decimal("5")

    def test_valid_string(self) -> None:
        assert _as_decimal("3.14", "field") == Decimal("3.14")

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ConfigError, match="decimal-compatible"):
            _as_decimal("abc", "field")

    def test_infinity_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal("Infinity", "field")

    def test_nan_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be finite"):
            _as_decimal("NaN", "field")


class TestSentimentScore:
    def test_valid_score(self) -> None:
        s = SentimentScore(
            source="test",
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
        assert s.source == "test"
        assert s.score == Decimal("0.5")

    def test_empty_source_raises(self) -> None:
        with pytest.raises(ConfigError, match="source cannot be empty"):
            SentimentScore(
                source="  ",
                score=Decimal("0"),
                confidence=Decimal("0.5"),
                label="NEUTRAL",
            )

    def test_empty_label_raises(self) -> None:
        with pytest.raises(ConfigError, match="label cannot be empty"):
            SentimentScore(
                source="test", score=Decimal("0"), confidence=Decimal("0.5"), label=""
            )

    def test_score_out_of_range_raises(self) -> None:
        with pytest.raises(ConfigError, match="score must be between"):
            SentimentScore(
                source="test",
                score=Decimal("2"),
                confidence=Decimal("0.5"),
                label="POS",
            )

    def test_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ConfigError, match="confidence must be between"):
            SentimentScore(
                source="test",
                score=Decimal("0"),
                confidence=Decimal("1.5"),
                label="NEUTRAL",
            )

    def test_metadata_converted_to_strings(self) -> None:
        s = SentimentScore(
            source="test",
            score=Decimal("0"),
            confidence=Decimal("0.5"),
            label="NEUTRAL",
            metadata={1: 2},
        )
        assert all(isinstance(k, str) for k in s.metadata)

    def test_boundary_score_positive(self) -> None:
        s = SentimentScore(
            source="t", score=Decimal("1"), confidence=Decimal("0.5"), label="P"
        )
        assert s.score == Decimal("1")

    def test_boundary_score_negative(self) -> None:
        s = SentimentScore(
            source="t", score=Decimal("-1"), confidence=Decimal("0.5"), label="N"
        )
        assert s.score == Decimal("-1")

    def test_boundary_confidence_zero(self) -> None:
        s = SentimentScore(
            source="t", score=Decimal("0"), confidence=Decimal("0"), label="N"
        )
        assert s.confidence == Decimal("0")

    def test_default_text_excerpt(self) -> None:
        s = SentimentScore(
            source="t", score=Decimal("0"), confidence=Decimal("0.5"), label="N"
        )
        assert s.text_excerpt == ""

    def test_default_metadata(self) -> None:
        s = SentimentScore(
            source="t", score=Decimal("0"), confidence=Decimal("0.5"), label="N"
        )
        assert s.metadata == {}


class TestSentimentAnalyzerProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        class FakeAnalyzer:
            def analyze(self, _text: str) -> SentimentScore:
                return SentimentScore(
                    source="fake",
                    score=Decimal("0"),
                    confidence=Decimal("0.5"),
                    label="NEUTRAL",
                )

        assert isinstance(FakeAnalyzer(), SentimentAnalyzer)
