"""
Normalize sentiment aggregator output to [0, 1] selection signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.selection._util import DirectionalIntent, clamp_01
from iatb.selection.decay import temporal_decay

if TYPE_CHECKING:
    from iatb.sentiment.aggregator import SentimentAggregator


@dataclass(frozen=True)
class SentimentSignalInput:
    text: str
    volume_ratio: Decimal
    instrument_symbol: str
    exchange: Exchange
    timestamp_utc: datetime


@dataclass(frozen=True)
class SentimentSignalOutput:
    score: Decimal
    confidence: Decimal
    directional_bias: str
    metadata: dict[str, str]


def compute_sentiment_signal(
    aggregator: SentimentAggregator,
    inputs: SentimentSignalInput,
    current_utc: datetime,
    intent: DirectionalIntent = DirectionalIntent.NEUTRAL,
) -> SentimentSignalOutput:
    """Produce a [0, 1] sentiment score from the aggregator."""
    _validate_input(inputs, current_utc)
    gate = aggregator.evaluate_instrument(inputs.text, inputs.volume_ratio)
    raw_score = _normalize_score(gate.composite.score, intent)
    decay = temporal_decay(inputs.timestamp_utc, current_utc, "sentiment")
    decayed_score = clamp_01(raw_score * decay)
    confidence = clamp_01(gate.composite.confidence * decay)
    bias = _directional_bias(gate.composite.score)
    return SentimentSignalOutput(
        score=decayed_score,
        confidence=confidence,
        directional_bias=bias,
        metadata={
            "very_strong": "1" if gate.very_strong else "0",
            "volume_confirmed": "1" if gate.volume_confirmed else "0",
            "tradable": "1" if gate.tradable else "0",
            "raw_composite": str(gate.composite.score),
            "intent": intent.value,
        },
    )


def _normalize_score(composite: Decimal, intent: DirectionalIntent) -> Decimal:
    """Map [-1, 1] -> [0, 1], inverted for SHORT intent."""
    if intent == DirectionalIntent.SHORT:
        return (Decimal("1") - composite) / Decimal("2")
    return (composite + Decimal("1")) / Decimal("2")


def _directional_bias(score: Decimal) -> str:
    if score > Decimal("0.05"):
        return "BULLISH"
    if score < Decimal("-0.05"):
        return "BEARISH"
    return "NEUTRAL"


def _validate_input(inputs: SentimentSignalInput, current: datetime) -> None:
    if inputs.timestamp_utc.tzinfo != UTC:
        msg = "timestamp_utc must be UTC"
        raise ConfigError(msg)
    if current.tzinfo != UTC:
        msg = "current_utc must be UTC"
        raise ConfigError(msg)
    if not inputs.instrument_symbol.strip():
        msg = "instrument_symbol cannot be empty"
        raise ConfigError(msg)
