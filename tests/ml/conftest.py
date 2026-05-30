"""ML test fixtures shared across ML module tests."""

from decimal import Decimal

import pytest
from iatb.ml.base import PredictionResult


@pytest.fixture()
def sample_features() -> list[Decimal]:
    """Provide standard feature list for predictor tests."""
    return [Decimal("100"), Decimal("200"), Decimal("300")]


@pytest.fixture()
def sample_prediction_result() -> PredictionResult:
    """Provide a valid PredictionResult for reuse."""
    return PredictionResult(
        symbol="RELIANCE",
        score=Decimal("0.75"),
        confidence=Decimal("0.8"),
        regime_label="BULL",
    )


@pytest.fixture()
def sample_train_features() -> list[list[Decimal]]:
    """Provide training feature sequences."""
    return [
        [Decimal("100"), Decimal("200"), Decimal("300")],
        [Decimal("110"), Decimal("210"), Decimal("310")],
        [Decimal("120"), Decimal("220"), Decimal("320")],
    ]


@pytest.fixture()
def sample_train_targets() -> list[Decimal]:
    """Provide training targets matching sample_train_features."""
    return [Decimal("300"), Decimal("310"), Decimal("320")]


@pytest.fixture()
def mock_predictor() -> object:
    """Create a mock predictor implementing the Predictor protocol."""

    class _MockPredictor:
        def predict(self, features: list[Decimal]) -> PredictionResult:
            _ = features
            return PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0.5"),
                confidence=Decimal("0.6"),
                regime_label="BULL",
            )

    return _MockPredictor()


@pytest.fixture()
def mock_trainable_model() -> object:
    """Create a mock model with train() returning Decimal."""

    class _MockTrainable:
        def train(
            self, features: list[list[Decimal]], targets: list[Decimal]
        ) -> Decimal:
            return Decimal("0.1")

        def predict(self, features: list[Decimal]) -> PredictionResult:
            return PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0.5"),
                confidence=Decimal("0.6"),
                regime_label="BULL",
            )

    return _MockTrainable()


@pytest.fixture()
def mock_fit_model() -> object:
    """Create a mock model with fit() and predict() methods."""

    class _MockFitModel:
        def fit(self, features: list[list[Decimal]], targets: list[Decimal]) -> None:
            pass

        def predict(self, features: list[Decimal]) -> PredictionResult:
            return PredictionResult(
                symbol="RELIANCE",
                score=Decimal("0.5"),
                confidence=Decimal("0.6"),
                regime_label="SIDEWAYS",
            )

    return _MockFitModel()
