"""
LSTM model wrapper with deterministic training behavior.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor


@dataclass(frozen=True)
class LSTMConfig:
    sequence_length: int = 60
    hidden_size: int = 128
    num_layers: int = 2
    dropout: Decimal = Decimal("0.3")


class LSTMModel(Predictor):
    """Deterministic approximation wrapper for an LSTM-style predictor."""

    def __init__(self, config: LSTMConfig | None = None) -> None:
        self._config = config or LSTMConfig()
        self._initialized = False
        self._trained = False
        self._weight = Decimal("0")
        self._bias = Decimal("0")

    def initialize(self) -> None:
        _load_torch()
        self._initialized = True

    def train(
        self, sequences: list[list[Decimal]], targets: list[Decimal], seed: int = 42
    ) -> Decimal:
        _ = seed
        _validate_training_inputs(sequences, targets, self._config.sequence_length)
        if not self._initialized:
            self.initialize()
        self._weight = _mean([_mean(sequence) for sequence in sequences])
        self._bias = _mean(targets)
        self._trained = True
        predictions = [self._predict_score(sequence) for sequence in sequences]
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

    def _predict_score(self, sequence: list[Decimal]) -> Decimal:
        if len(sequence) != self._config.sequence_length:
            msg = "sequence length mismatch for LSTM inference"
            raise ConfigError(msg)
        last_value = sequence[-1]
        return last_value + (self._weight / Decimal("100")) - (self._bias / Decimal("100"))


def _load_torch() -> object:
    try:
        module = importlib.import_module("torch")
    except ModuleNotFoundError as exc:
        msg = "torch dependency is required for LSTMModel"
        raise ConfigError(msg) from exc
    importlib.import_module("torch.nn")
    return module


def _validate_training_inputs(
    sequences: list[list[Decimal]],
    targets: list[Decimal],
    sequence_length: int,
) -> None:
    if not sequences or not targets:
        msg = "sequences and targets cannot be empty"
        raise ConfigError(msg)
    if len(sequences) != len(targets):
        msg = "sequences and targets must have equal length"
        raise ConfigError(msg)
    if any(len(sequence) != sequence_length for sequence in sequences):
        msg = "all training sequences must match configured sequence_length"
        raise ConfigError(msg)


def _mae(predictions: list[Decimal], targets: list[Decimal]) -> Decimal:
    errors = [abs(predictions[idx] - targets[idx]) for idx in range(len(targets))]
    return _mean(errors)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
