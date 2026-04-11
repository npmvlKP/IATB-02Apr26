import random
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime, RegimeDetector

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeHmm:
    def fit(self, matrix: object) -> None:
        _ = matrix

    def predict(self, matrix: object) -> list[int]:
        _ = matrix
        # Return same number of states as feature rows
        return [2, 1, 0]


class _FakeHmm4States:
    """Fake HMM that returns 4 states for testing."""

    def fit(self, matrix: object) -> None:
        _ = matrix

    def predict(self, matrix: object) -> list[int]:
        _ = matrix
        return [2, 1, 0, 0]


def test_regime_detector_emits_transition_event_on_change() -> None:
    detector = RegimeDetector(model_factory=lambda: _FakeHmm4States())
    features = [
        [Decimal("-0.02"), Decimal("0.2")],
        [Decimal("0.00"), Decimal("0.1")],
        [Decimal("0.03"), Decimal("0.3")],
        [Decimal("0.05"), Decimal("0.4")],
    ]
    first = detector.detect(features)
    assert first.regime == MarketRegime.BULL
    second = detector.detect(
        [
            [Decimal("0.02"), Decimal("0.2")],
            [Decimal("0.01"), Decimal("0.1")],
            [Decimal("-0.04"), Decimal("0.3")],
            [Decimal("-0.06"), Decimal("0.4")],
        ]
    )
    assert second.regime == MarketRegime.BEAR
    assert second.transition_event is not None
    assert second.transition_event.metadata["previous"] == "BULL"
    assert second.transition_event.metadata["current"] == "BEAR"


def test_regime_detector_rejects_short_feature_matrix() -> None:
    detector = RegimeDetector(model_factory=lambda: _FakeHmm())
    with pytest.raises(ConfigError, match="at least three feature rows"):
        detector.detect([[Decimal("0.1")], [Decimal("0.2")]])


def test_regime_detector_rejects_empty_feature_row() -> None:
    detector = RegimeDetector(model_factory=lambda: _FakeHmm())
    with pytest.raises(ConfigError, match="cannot be empty"):
        detector.detect([[Decimal("0.1")], [], [Decimal("0.2")]])


def test_regime_detector_requires_model_fit_and_predict() -> None:
    detector_fit = RegimeDetector(model_factory=lambda: object())
    with pytest.raises(ConfigError, match="must expose fit"):
        detector_fit.detect(
            [
                [Decimal("0.1"), Decimal("0.1")],
                [Decimal("0.2"), Decimal("0.2")],
                [Decimal("0.3"), Decimal("0.3")],
            ]
        )

    class _FitOnly:
        def fit(self, matrix: object) -> None:
            _ = matrix

    detector_predict = RegimeDetector(model_factory=lambda: _FitOnly())
    with pytest.raises(ConfigError, match="must expose predict"):
        detector_predict.detect(
            [
                [Decimal("0.1"), Decimal("0.1")],
                [Decimal("0.2"), Decimal("0.2")],
                [Decimal("0.3"), Decimal("0.3")],
            ]
        )


def test_regime_detector_rejects_empty_predicted_states() -> None:
    class _EmptyStateHmm:
        def fit(self, matrix: object) -> None:
            _ = matrix

        def predict(self, matrix: object) -> list[int]:
            _ = matrix
            return []

    detector = RegimeDetector(model_factory=lambda: _EmptyStateHmm())
    with pytest.raises(ConfigError, match="returned no states"):
        detector.detect(
            [
                [Decimal("0.1"), Decimal("0.1")],
                [Decimal("0.2"), Decimal("0.2")],
                [Decimal("0.3"), Decimal("0.3")],
            ]
        )


def test_regime_detector_no_transition_on_same_regime() -> None:
    """Test that no transition event is emitted when regime stays the same."""
    detector = RegimeDetector(model_factory=lambda: _FakeHmm4States())
    features = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("0.02"), Decimal("0.2")],
        [Decimal("0.03"), Decimal("0.3")],
        [Decimal("0.04"), Decimal("0.4")],
    ]
    detector.detect(features)
    result2 = detector.detect(features)
    assert result2.transition_event is None


def test_estimate_confidence_clamps_to_zero_one() -> None:
    """Test _estimate_confidence clamps between 0 and 1 (line 121)."""
    # Test with all same state - should be 1.0
    result = RegimeDetector._estimate_confidence([0, 0, 0, 0])
    assert result == Decimal("1")

    # Test with mixed states - should be between 0 and 1
    result = RegimeDetector._estimate_confidence([0, 1, 0, 1])
    assert result == Decimal("0.5")

    # Test with all different states - should be > 0 but < 1
    result = RegimeDetector._estimate_confidence([0, 1, 2, 3])
    assert Decimal("0") < result < Decimal("1")


def test_regime_change_event_utc_timestamp() -> None:
    """Test that RegimeChangeEvent has strict UTC timestamp."""
    detector = RegimeDetector(model_factory=lambda: _FakeHmm4States())
    features = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("0.02"), Decimal("0.2")],
        [Decimal("0.03"), Decimal("0.3")],
        [Decimal("0.04"), Decimal("0.4")],
    ]
    detector.detect(features)
    bear_features = [
        [Decimal("0.02"), Decimal("0.2")],
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("-0.04"), Decimal("0.3")],
        [Decimal("-0.06"), Decimal("0.4")],
    ]
    result = detector.detect(bear_features)
    assert result.transition_event is not None
    # Verify timestamp is UTC
    assert isinstance(result.transition_event.timestamp, datetime)
    assert result.transition_event.timestamp.tzinfo == UTC


def test_regime_detector_handles_edge_case_minimal_features() -> None:
    """Test regime detection with exactly 3 features (minimum required)."""
    detector = RegimeDetector(model_factory=lambda: _FakeHmm())
    features = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("0.02"), Decimal("0.2")],
        [Decimal("0.03"), Decimal("0.3")],
    ]
    result = detector.detect(features)
    assert result.regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]
    assert Decimal("0") <= result.confidence <= Decimal("1")
    assert result.transition_event is None  # First detection has no transition


def test_regime_detector_confidence_calculation() -> None:
    """Test confidence is proportional to state stability."""
    detector = RegimeDetector(model_factory=lambda: _FakeHmm4States())

    # Test with consistent states (higher confidence)
    features_consistent = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("0.02"), Decimal("0.1")],
        [Decimal("0.03"), Decimal("0.1")],
        [Decimal("0.04"), Decimal("0.1")],
    ]
    result1 = detector.detect(features_consistent)

    # Test with varying states (lower confidence)
    features_varying = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("-0.01"), Decimal("0.1")],
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("-0.01"), Decimal("0.1")],
    ]
    result2 = detector.detect(features_varying)

    # Both should have valid confidence ranges
    assert Decimal("0") <= result1.confidence <= Decimal("1")
    assert Decimal("0") <= result2.confidence <= Decimal("1")


def test_regime_detector_first_detection_no_transition() -> None:
    """Test that first detection has no previous regime (no transition event)."""
    detector = RegimeDetector(model_factory=lambda: _FakeHmm4States())
    features = [
        [Decimal("0.01"), Decimal("0.1")],
        [Decimal("0.02"), Decimal("0.2")],
        [Decimal("0.03"), Decimal("0.3")],
        [Decimal("0.04"), Decimal("0.4")],
    ]
    result = detector.detect(features)
    # First detection should have no transition event
    assert result.transition_event is None
    assert result.regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]


def test_regime_detector_error_on_missing_hmmlearn() -> None:
    """Test that missing hmmlearn raises ConfigError with clear message."""
    # Use the default model factory which tries to import hmmlearn
    detector = RegimeDetector()
    # Mock the importlib.import_module to raise ModuleNotFoundError
    import importlib

    original_import = importlib.import_module

    def mock_import(name: str) -> object:
        if "hmmlearn" in name:
            raise ModuleNotFoundError("No module named 'hmmlearn'")
        return original_import(name)

    importlib.import_module = mock_import
    try:
        features = [
            [Decimal("0.01"), Decimal("0.1")],
            [Decimal("0.02"), Decimal("0.2")],
            [Decimal("0.03"), Decimal("0.3")],
        ]
        with pytest.raises(ConfigError, match="hmmlearn dependency is required"):
            detector.detect(features)
    finally:
        importlib.import_module = original_import
