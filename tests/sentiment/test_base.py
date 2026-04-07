from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore, sentiment_label_from_score


def test_sentiment_score_accepts_valid_range() -> None:
    score = SentimentScore(
        source="finbert",
        score=Decimal("0.8"),
        confidence=Decimal("0.9"),
        label="POSITIVE",
    )
    assert score.score == Decimal("0.8")


def test_sentiment_score_rejects_invalid_ranges() -> None:
    with pytest.raises(ConfigError, match="between -1 and 1"):
        SentimentScore(
            source="aion",
            score=Decimal("1.1"),
            confidence=Decimal("0.5"),
            label="POSITIVE",
        )
    with pytest.raises(ConfigError, match="between 0 and 1"):
        SentimentScore(
            source="aion",
            score=Decimal("0.4"),
            confidence=Decimal("1.1"),
            label="POSITIVE",
        )


def test_sentiment_label_from_score_thresholds() -> None:
    assert sentiment_label_from_score(Decimal("0.1")) == "POSITIVE"
    assert sentiment_label_from_score(Decimal("-0.1")) == "NEGATIVE"
    assert sentiment_label_from_score(Decimal("0.01")) == "NEUTRAL"


def test_sentiment_score_rejects_empty_source_and_label() -> None:
    with pytest.raises(ConfigError, match="source cannot be empty"):
        SentimentScore(
            source="   ",
            score=Decimal("0.1"),
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
    with pytest.raises(ConfigError, match="label cannot be empty"):
        SentimentScore(
            source="finbert",
            score=Decimal("0.1"),
            confidence=Decimal("0.8"),
            label="  ",
        )


def test_sentiment_score_rejects_non_decimal_and_non_finite_values() -> None:
    with pytest.raises(ConfigError, match="decimal-compatible"):
        SentimentScore(
            source="finbert",
            score="not-a-decimal",
            confidence=Decimal("0.8"),
            label="POSITIVE",
        )
    with pytest.raises(ConfigError, match="must be finite"):
        SentimentScore(
            source="finbert",
            score=Decimal("0.2"),
            confidence=Decimal("NaN"),
            label="POSITIVE",
        )
