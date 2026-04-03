"""
Shared contracts and data models for sentiment analysis.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol, runtime_checkable

from iatb.core.exceptions import ConfigError


def _as_decimal(value: object, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"{field_name} must be decimal-compatible"
        raise ConfigError(msg) from exc
    if not decimal_value.is_finite():
        msg = f"{field_name} must be finite"
        raise ConfigError(msg)
    return decimal_value


def sentiment_label_from_score(score: Decimal) -> str:
    """Return POSITIVE/NEGATIVE/NEUTRAL from normalized score."""
    if score >= Decimal("0.05"):
        return "POSITIVE"
    if score <= Decimal("-0.05"):
        return "NEGATIVE"
    return "NEUTRAL"


@dataclass(frozen=True)
class SentimentScore:
    source: str
    score: Decimal
    confidence: Decimal
    label: str
    text_excerpt: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            msg = "source cannot be empty"
            raise ConfigError(msg)
        if not self.label.strip():
            msg = "label cannot be empty"
            raise ConfigError(msg)
        object.__setattr__(self, "score", _as_decimal(self.score, "score"))
        object.__setattr__(self, "confidence", _as_decimal(self.confidence, "confidence"))
        if self.score < Decimal("-1") or self.score > Decimal("1"):
            msg = "score must be between -1 and 1"
            raise ConfigError(msg)
        if self.confidence < Decimal("0") or self.confidence > Decimal("1"):
            msg = "confidence must be between 0 and 1"
            raise ConfigError(msg)
        object.__setattr__(
            self,
            "metadata",
            {str(key): str(value) for key, value in self.metadata.items()},
        )


@runtime_checkable
class SentimentAnalyzer(Protocol):
    """Contract for sentiment analyzers."""

    def analyze(self, text: str) -> SentimentScore:
        ...
