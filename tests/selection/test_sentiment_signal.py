"""Tests for sentiment_signal.py module."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.selection._util import DirectionalIntent
from iatb.selection.sentiment_signal import (
    SentimentSignalInput,
    SentimentSignalOutput,
    _directional_bias,
    _normalize_score,
    _validate_input,
    compute_sentiment_signal,
)

_NOW = datetime(2026, 4, 5, 10, 0, 0, tzinfo=UTC)


def _mock_aggregator(
    score: Decimal = Decimal("0.5"),
    confidence: Decimal = Decimal("0.8"),
    very_strong: bool = False,
    volume_confirmed: bool = False,
    tradable: bool = True,
) -> object:
    """Create a mock SentimentAggregator."""
    from unittest.mock import Mock

    mock = Mock()
    mock.evaluate_instrument.return_value = Mock(
        composite=Mock(score=score, confidence=confidence),
        very_strong=very_strong,
        volume_confirmed=volume_confirmed,
        tradable=tradable,
    )
    return mock


def test_compute_sentiment_signal_basic() -> None:
    """Test compute_sentiment_signal with valid inputs."""
    aggregator = _mock_aggregator(
        score=Decimal("0.5"),
        confidence=Decimal("0.8"),
    )
    inputs = SentimentSignalInput(
        text="Positive sentiment",
        volume_ratio=Decimal("1.5"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    result = compute_sentiment_signal(aggregator, inputs, _NOW)

    assert isinstance(result, SentimentSignalOutput)
    assert Decimal("0") <= result.score <= Decimal("1")
    assert result.directional_bias in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert "raw_composite" in result.metadata


def test_compute_sentiment_signal_with_decay() -> None:
    """Test compute_sentiment_signal applies temporal decay."""
    from datetime import timedelta

    old_timestamp = _NOW - timedelta(hours=2)
    aggregator = _mock_aggregator(score=Decimal("0.8"), confidence=Decimal("0.9"))
    inputs = SentimentSignalInput(
        text="Positive sentiment",
        volume_ratio=Decimal("1.5"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=old_timestamp,
    )
    result = compute_sentiment_signal(aggregator, inputs, _NOW)

    # Decay should reduce score slightly
    assert result.score < Decimal("1")
    assert result.confidence < Decimal("1")


def test_compute_sentiment_signal_short_intent() -> None:
    """Test compute_sentiment_signal with SHORT intent inverts score."""
    aggregator = _mock_aggregator(score=Decimal("0.5"), confidence=Decimal("0.8"))
    inputs = SentimentSignalInput(
        text="Positive sentiment",
        volume_ratio=Decimal("1.5"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    long_result = compute_sentiment_signal(
        aggregator,
        inputs,
        _NOW,
        DirectionalIntent.LONG,
    )
    short_result = compute_sentiment_signal(
        aggregator,
        inputs,
        _NOW,
        DirectionalIntent.SHORT,
    )

    # SHORT should invert the score relative to LONG
    assert long_result.score != short_result.score
    assert long_result.score + short_result.score == Decimal("1")


def test_compute_sentiment_signal_metadata_flags() -> None:
    """Test compute_sentiment_signal includes metadata flags."""
    aggregator = _mock_aggregator(
        score=Decimal("0.9"),
        confidence=Decimal("0.9"),
        very_strong=True,
        volume_confirmed=True,
        tradable=True,
    )
    inputs = SentimentSignalInput(
        text="Strong positive",
        volume_ratio=Decimal("2.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    result = compute_sentiment_signal(aggregator, inputs, _NOW)

    assert result.metadata["very_strong"] == "1"
    assert result.metadata["volume_confirmed"] == "1"
    assert result.metadata["tradable"] == "1"


def test_compute_sentiment_signal_empty_symbol_raises() -> None:
    """Test compute_sentiment_signal raises for empty symbol."""
    aggregator = _mock_aggregator()
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="",  # Empty symbol
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        compute_sentiment_signal(aggregator, inputs, _NOW)


def test_compute_sentiment_signal_whitespace_symbol_raises() -> None:
    """Test compute_sentiment_signal raises for whitespace-only symbol."""
    aggregator = _mock_aggregator()
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="   ",  # Whitespace only
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        compute_sentiment_signal(aggregator, inputs, _NOW)


def test_compute_sentiment_signal_non_utc_timestamp_raises() -> None:
    """Test compute_sentiment_signal raises for non-UTC timestamp."""
    aggregator = _mock_aggregator()
    # Force a naive datetime for testing
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=datetime(2026, 4, 5, 10, 0, 0, tzinfo=None),  # noqa: DTZ001
    )

    with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
        compute_sentiment_signal(aggregator, inputs, _NOW)


def test_compute_sentiment_signal_non_utc_current_raises() -> None:
    """Test compute_sentiment_signal raises for non-UTC current time."""
    aggregator = _mock_aggregator()
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    non_utc_current = datetime(2026, 4, 5, 10, 0, 0, tzinfo=None)  # noqa: DTZ001

    with pytest.raises(ConfigError, match="current_utc must be UTC"):
        compute_sentiment_signal(aggregator, inputs, non_utc_current)


def test_normalize_score_long_intent() -> None:
    """Test _normalize_score with LONG intent maps [-1, 1] to [0, 1]."""
    assert _normalize_score(Decimal("1"), DirectionalIntent.LONG) == Decimal("1")
    assert _normalize_score(Decimal("-1"), DirectionalIntent.LONG) == Decimal("0")
    assert _normalize_score(Decimal("0"), DirectionalIntent.LONG) == Decimal("0.5")


def test_normalize_score_short_intent() -> None:
    """Test _normalize_score with SHORT intent inverts the mapping."""
    assert _normalize_score(Decimal("1"), DirectionalIntent.SHORT) == Decimal("0")
    assert _normalize_score(Decimal("-1"), DirectionalIntent.SHORT) == Decimal("1")
    assert _normalize_score(Decimal("0"), DirectionalIntent.SHORT) == Decimal("0.5")


def test_normalize_score_neutral_intent() -> None:
    """Test _normalize_score with NEUTRAL intent uses default mapping."""
    assert _normalize_score(Decimal("1"), DirectionalIntent.NEUTRAL) == Decimal("1")
    assert _normalize_score(Decimal("-1"), DirectionalIntent.NEUTRAL) == Decimal("0")


def test_directional_bias_bullish() -> None:
    """Test _directional_bias returns BULLISH for positive scores."""
    assert _directional_bias(Decimal("0.1")) == "BULLISH"
    assert _directional_bias(Decimal("0.5")) == "BULLISH"
    assert _directional_bias(Decimal("1.0")) == "BULLISH"


def test_directional_bias_bearish() -> None:
    """Test _directional_bias returns BEARISH for negative scores."""
    assert _directional_bias(Decimal("-0.1")) == "BEARISH"
    assert _directional_bias(Decimal("-0.5")) == "BEARISH"
    assert _directional_bias(Decimal("-1.0")) == "BEARISH"


def test_directional_bias_neutral() -> None:
    """Test _directional_bias returns NEUTRAL for scores near zero."""
    assert _directional_bias(Decimal("0")) == "NEUTRAL"
    assert _directional_bias(Decimal("0.04")) == "NEUTRAL"
    assert _directional_bias(Decimal("-0.04")) == "NEUTRAL"


def test_directional_bias_boundary_values() -> None:
    """Test _directional_bias at exact boundary values."""
    # Just above 0.05
    assert _directional_bias(Decimal("0.0501")) == "BULLISH"
    # Just below -0.05
    assert _directional_bias(Decimal("-0.0501")) == "BEARISH"
    # Exactly 0.05
    assert _directional_bias(Decimal("0.05")) == "NEUTRAL"
    # Exactly -0.05
    assert _directional_bias(Decimal("-0.05")) == "NEUTRAL"


def test_validate_input_utc_timestamps() -> None:
    """Test _validate_input passes with UTC timestamps."""
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    # Should not raise
    _validate_input(inputs, _NOW)


def test_validate_input_non_utc_timestamp_raises() -> None:
    """Test _validate_input raises for non-UTC timestamp."""
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=datetime(2026, 4, 5, 10, 0, 0, tzinfo=None),  # noqa: DTZ001
    )

    with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
        _validate_input(inputs, _NOW)


def test_validate_input_non_utc_current_raises() -> None:
    """Test _validate_input raises for non-UTC current time."""
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="NIFTY",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )
    non_utc = datetime(2026, 4, 5, 10, 0, 0, tzinfo=None)  # noqa: DTZ001

    with pytest.raises(ConfigError, match="current_utc must be UTC"):
        _validate_input(inputs, non_utc)


def test_validate_input_empty_symbol_raises() -> None:
    """Test _validate_input raises for empty symbol."""
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        _validate_input(inputs, _NOW)


def test_validate_input_whitespace_symbol_raises() -> None:
    """Test _validate_input raises for whitespace-only symbol."""
    inputs = SentimentSignalInput(
        text="Test",
        volume_ratio=Decimal("1.0"),
        instrument_symbol="  \t  ",
        exchange=Exchange.NSE,
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        _validate_input(inputs, _NOW)
