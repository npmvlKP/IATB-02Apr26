"""
Transformer model wrapper with deterministic training behavior.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor


@dataclass(frozen=True)
class TransformerConfig:
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2


class TransformerModel(Predictor):
    """Deterministic approximation wrapper for Transformer-style inference."""

    def __init__(self, config: TransformerConfig | None = None) -> None:
        self._config = config or TransformerConfig()
        self._initialized = False
        self._trained = False
        self._scale = Decimal("1")
        self._offset = Decimal("0")

    def initialize(self) -> None:
        _load_torch()
        self._initialized = True

    def train(self, feature_sequences: list[list[Decimal]], targets: list[Decimal]) -> Decimal:
        _validate_inputs(feature_sequences, targets)
        if not self._initialized:
            self.initialize()
        signals = [_attention_proxy(sequence) for sequence in feature_sequences]
        self._scale = max(_mean(signals), Decimal("0.0001"))
        self._offset = _mean(targets)
        self._trained = True
        predictions = [self._predict_score(sequence) for sequence in feature_sequences]
        return _mae(predictions, targets)

    def predict(self, features: list[Decimal]) -> PredictionResult:
        if not self._trained:
            msg = "model must be trained before predict()"
            raise ConfigError(msg)
        score = self._predict_score(features)
        confidence = min(Decimal("1"), max(Decimal("0"), abs(score)))
        return PredictionResult(
            symbol="ENSEMBLE", score=score, confidence=confidence, regime_label="SIDEWAYS"
        )

    def _predict_score(self, features: list[Decimal]) -> Decimal:
        if not features:
            msg = "features cannot be empty"
            raise ConfigError(msg)
        attention = _attention_proxy(features)
        return (attention / self._scale) - (self._offset / Decimal("100"))


def _load_torch() -> object:
    try:
        module = importlib.import_module("torch")
    except ModuleNotFoundError as exc:
        msg = "torch dependency is required for TransformerModel"
        raise ConfigError(msg) from exc
    importlib.import_module("torch.nn")
    return module


def _attention_proxy(features: list[Decimal]) -> Decimal:
    weighted = [value * Decimal(index + 1) for index, value in enumerate(features)]
    return sum(weighted, Decimal("0")) / Decimal(len(weighted))


def _validate_inputs(feature_sequences: list[list[Decimal]], targets: list[Decimal]) -> None:
    if not feature_sequences or not targets:
        msg = "feature_sequences and targets cannot be empty"
        raise ConfigError(msg)
    if len(feature_sequences) != len(targets):
        msg = "feature_sequences and targets must have equal length"
        raise ConfigError(msg)
    if any(not sequence for sequence in feature_sequences):
        msg = "feature sequences cannot contain empty rows"
        raise ConfigError(msg)


def _mae(predictions: list[Decimal], targets: list[Decimal]) -> Decimal:
    errors = [abs(predictions[idx] - targets[idx]) for idx in range(len(targets))]
    return _mean(errors)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
