"""Coverage tests for iatb.ml.predictor - EnsemblePredictor and helpers."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.predictor import (
    EnsemblePredictor,
    _clamp_01,
    _normalize_weights,
    _regime_vote,
    _weighted_average,
)


class TestNormalizeWeights:
    def test_none_returns_uniform_weights(self) -> None:
        result = _normalize_weights(None, 3)
        assert result == [Decimal("1"), Decimal("1"), Decimal("1")]

    def test_valid_weights_returned(self) -> None:
        result = _normalize_weights([Decimal("2"), Decimal("3")], 2)
        assert result == [Decimal("2"), Decimal("3")]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must match"):
            _normalize_weights([Decimal("1")], 2)

    def test_zero_weight_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must be positive"):
            _normalize_weights([Decimal("1"), Decimal("0")], 2)

    def test_negative_weight_raises(self) -> None:
        with pytest.raises(ConfigError, match="weights must be positive"):
            _normalize_weights([Decimal("1"), Decimal("-1")], 2)


class TestWeightedAverage:
    def test_uniform_weights(self) -> None:
        values = [Decimal("10"), Decimal("20")]
        weights = [Decimal("1"), Decimal("1")]
        result = _weighted_average(values, weights)
        assert result == Decimal("15")

    def test_custom_weights(self) -> None:
        values = [Decimal("10"), Decimal("20")]
        weights = [Decimal("3"), Decimal("1")]
        result = _weighted_average(values, weights)
        expected = (Decimal("30") + Decimal("20")) / Decimal("4")
        assert result == expected


class TestRegimeVote:
    def test_majority_vote(self) -> None:
        predictions = [
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BEAR"),
        ]
        result = _regime_vote(predictions, [Decimal("1")] * 3)
        assert result == "BULL"

    def test_weighted_vote(self) -> None:
        predictions = [
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BEAR"),
            PredictionResult("A", Decimal("0"), Decimal("0.5"), "BULL"),
        ]
        weights = [Decimal("3"), Decimal("1")]
        result = _regime_vote(predictions, weights)
        assert result == "BEAR"


class TestClamp01:
    def test_value_within_range(self) -> None:
        assert _clamp_01(Decimal("0.5")) == Decimal("0.5")

    def test_value_below_zero_clamped(self) -> None:
        assert _clamp_01(Decimal("-0.5")) == Decimal("0")

    def test_value_above_one_clamped(self) -> None:
        assert _clamp_01(Decimal("1.5")) == Decimal("1")

    def test_exact_zero(self) -> None:
        assert _clamp_01(Decimal("0")) == Decimal("0")

    def test_exact_one(self) -> None:
        assert _clamp_01(Decimal("1")) == Decimal("1")


class TestEnsemblePredictor:
    def test_empty_predictors_raises(self) -> None:
        with pytest.raises(ConfigError, match="predictors cannot be empty"):
            EnsemblePredictor([])

    def test_single_predictor(
        self,
        mock_predictor: object,
        sample_features: list[Decimal],
    ) -> None:
        ensemble = EnsemblePredictor([mock_predictor])
        result = ensemble.predict(sample_features)
        assert isinstance(result, PredictionResult)
        assert result.symbol == "RELIANCE"

    def test_multiple_predictors(
        self,
        sample_features: list[Decimal],
    ) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A",
            Decimal("0.6"),
            Decimal("0.7"),
            "BULL",
        )
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult(
            "A",
            Decimal("0.4"),
            Decimal("0.5"),
            "BEAR",
        )
        ensemble = EnsemblePredictor([p1, p2])
        result = ensemble.predict(sample_features)
        assert isinstance(result.score, Decimal)
        assert isinstance(result.confidence, Decimal)
        assert result.regime_label in {"BULL", "BEAR"}

    def test_custom_weights(
        self,
        sample_features: list[Decimal],
    ) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A",
            Decimal("1"),
            Decimal("1"),
            "BULL",
        )
        p2 = MagicMock()
        p2.predict.return_value = PredictionResult(
            "A",
            Decimal("0"),
            Decimal("0"),
            "BEAR",
        )
        ensemble = EnsemblePredictor(
            [p1, p2],
            weights=[Decimal("3"), Decimal("1")],
        )
        result = ensemble.predict(sample_features)
        assert result.score == Decimal("0.75")

    def test_confidence_clamped_at_boundary(self) -> None:
        p1 = MagicMock()
        p1.predict.return_value = PredictionResult(
            "A",
            Decimal("0"),
            Decimal("1"),
            "BULL",
        )
        ensemble = EnsemblePredictor([p1])
        result = ensemble.predict([Decimal("1")])
        assert result.confidence == Decimal("1")
