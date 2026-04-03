"""
Shared contracts and data models for ML predictors.
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


@dataclass(frozen=True)
class PredictionResult:
    symbol: str
    score: Decimal
    confidence: Decimal
    regime_label: str
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            msg = "symbol cannot be empty"
            raise ConfigError(msg)
        if not self.regime_label.strip():
            msg = "regime_label cannot be empty"
            raise ConfigError(msg)
        object.__setattr__(self, "score", _as_decimal(self.score, "score"))
        object.__setattr__(self, "confidence", _as_decimal(self.confidence, "confidence"))
        if self.confidence < Decimal("0") or self.confidence > Decimal("1"):
            msg = "confidence must be between 0 and 1"
            raise ConfigError(msg)
        normalized = {str(key): str(value) for key, value in self.metadata.items()}
        object.__setattr__(self, "metadata", normalized)


@runtime_checkable
class Predictor(Protocol):
    def predict(self, features: list[Decimal]) -> PredictionResult:
        ...
