"""
Ensemble predictor with weighted aggregation across model outputs.
"""

from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor


class EnsemblePredictor(Predictor):
    """Weighted-voting ensemble across multiple predictor models."""

    def __init__(self, predictors: list[Predictor], weights: list[Decimal] | None = None) -> None:
        if not predictors:
            msg = "predictors cannot be empty"
            raise ConfigError(msg)
        self._predictors = predictors
        self._weights = _normalize_weights(weights, len(predictors))

    def predict(self, features: list[Decimal]) -> PredictionResult:
        predictions = [predictor.predict(features) for predictor in self._predictors]
        weighted_score = _weighted_average([item.score for item in predictions], self._weights)
        weighted_confidence = _weighted_average(
            [item.confidence for item in predictions], self._weights
        )
        regime = _regime_vote(predictions, self._weights)
        symbol = predictions[0].symbol
        metadata = {"model_count": str(len(self._predictors))}
        return PredictionResult(
            symbol, weighted_score, _clamp_01(weighted_confidence), regime, metadata
        )


def _normalize_weights(weights: list[Decimal] | None, size: int) -> list[Decimal]:
    if weights is None:
        return [Decimal("1") for _ in range(size)]
    if len(weights) != size:
        msg = "weights must match number of predictors"
        raise ConfigError(msg)
    if any(weight <= Decimal("0") for weight in weights):
        msg = "weights must be positive"
        raise ConfigError(msg)
    return weights


def _weighted_average(values: list[Decimal], weights: list[Decimal]) -> Decimal:
    numerator = sum([values[idx] * weights[idx] for idx in range(len(values))], Decimal("0"))
    denominator = sum(weights, Decimal("0"))
    return numerator / denominator


def _regime_vote(predictions: list[PredictionResult], weights: list[Decimal]) -> str:
    votes: dict[str, Decimal] = {}
    for idx, prediction in enumerate(predictions):
        current = votes.get(prediction.regime_label, Decimal("0"))
        votes[prediction.regime_label] = current + weights[idx]
    return max(votes.items(), key=lambda item: item[1])[0]


def _clamp_01(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))
