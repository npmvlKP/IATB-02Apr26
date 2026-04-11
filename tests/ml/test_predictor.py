import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor
from iatb.ml.predictor import EnsemblePredictor

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _StubPredictor(Predictor):
    def __init__(self, score: Decimal, confidence: Decimal, regime: str) -> None:
        self._score = score
        self._confidence = confidence
        self._regime = regime

    def predict(self, features: list[Decimal]) -> PredictionResult:
        _ = features
        return PredictionResult("NIFTY", self._score, self._confidence, self._regime)


def test_ensemble_predictor_weighted_voting() -> None:
    predictors: list[Predictor] = [
        _StubPredictor(Decimal("0.2"), Decimal("0.7"), "BULL"),
        _StubPredictor(Decimal("0.1"), Decimal("0.6"), "BULL"),
        _StubPredictor(Decimal("-0.4"), Decimal("0.8"), "BEAR"),
    ]
    ensemble = EnsemblePredictor(predictors, [Decimal("2"), Decimal("1"), Decimal("1")])
    result = ensemble.predict([Decimal("1"), Decimal("2")])
    assert result.regime_label == "BULL"
    assert result.metadata["model_count"] == "3"


def test_ensemble_predictor_validates_configuration() -> None:
    with pytest.raises(ConfigError, match="cannot be empty"):
        EnsemblePredictor([])
    predictor = [_StubPredictor(Decimal("0.2"), Decimal("0.6"), "BULL")]
    with pytest.raises(ConfigError, match="match number of predictors"):
        EnsemblePredictor(predictor, [Decimal("1"), Decimal("2")])
    with pytest.raises(ConfigError, match="must be positive"):
        EnsemblePredictor(predictor, [Decimal("0")])
