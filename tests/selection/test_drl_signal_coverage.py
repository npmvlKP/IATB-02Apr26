"""
Comprehensive coverage tests for drl_signal.py.

Tests DRL signal computation, model inference, and error paths.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.selection.drl_signal import (
    compute_drl_signal,
    load_drl_model,
)


class TestLoadDrlModel:
    """Test load_drl_model function."""

    @patch("importlib.import_module")
    def test_load_model_success(self, mock_import) -> None:
        """Test successful model loading."""
        mock_module = MagicMock()
        mock_import.return_value = mock_module

        result = load_drl_model("test_model")
        assert result is not None
        mock_import.assert_called_once()

    @patch("importlib.import_module")
    def test_load_model_not_found(self, mock_import) -> None:
        """Test model not found."""
        mock_import.side_effect = ModuleNotFoundError("torch")

        with pytest.raises(ImportError) as exc_info:
            load_drl_model("test_model")
        assert (
            "model" in str(exc_info.value).lower()
            or "torch" in str(exc_info.value).lower()
        )


class TestComputeDrlSignal:
    """Test compute_drl_signal function."""

    def test_basic_signal_computation(self) -> None:
        """Test basic DRL signal computation."""
        features = {
            "price_momentum": Decimal("0.05"),
            "volume_trend": Decimal("0.02"),
            "volatility": Decimal("0.03"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_high_confidence_signal(self) -> None:
        """Test high confidence signal."""
        features = {
            "price_momentum": Decimal("0.9"),
            "volume_trend": Decimal("0.8"),
            "volatility": Decimal("0.7"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        assert result > Decimal("0.7")

    def test_low_confidence_signal(self) -> None:
        """Test low confidence signal."""
        features = {
            "price_momentum": Decimal("0.1"),
            "volume_trend": Decimal("0.1"),
            "volatility": Decimal("0.1"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        assert result < Decimal("0.3")

    def test_missing_feature(self) -> None:
        """Test with missing feature."""
        features = {
            "price_momentum": Decimal("0.5"),
            # Missing volume_trend
            "volatility": Decimal("0.3"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        # Should handle missing gracefully
        assert Decimal("0.0") <= result <= Decimal("1.0")

    def test_empty_features(self) -> None:
        """Test with empty features."""
        features: dict[str, Decimal] = {}
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        assert result == Decimal("0")

    def test_invalid_feature_range_high(self) -> None:
        """Test with feature above 1.0."""
        features = {
            "price_momentum": Decimal("1.5"),
            "volume_trend": Decimal("0.2"),
            "volatility": Decimal("0.3"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        # Should handle gracefully, might clamp or compute
        assert isinstance(result, Decimal)

    def test_invalid_feature_range_negative(self) -> None:
        """Test with negative feature."""
        features = {
            "price_momentum": Decimal("-0.5"),
            "volume_trend": Decimal("0.2"),
            "volatility": Decimal("0.3"),
        }
        weights = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.3"),
            "volatility": Decimal("0.2"),
        }

        result = compute_drl_signal(features, weights)
        # Should handle gracefully
        assert isinstance(result, Decimal)

    def test_zero_weights(self) -> None:
        """Test with all zero weights."""
        features = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.2"),
            "volatility": Decimal("0.3"),
        }
        weights = {
            "price_momentum": Decimal("0.0"),
            "volume_trend": Decimal("0.0"),
            "volatility": Decimal("0.0"),
        }

        result = compute_drl_signal(features, weights)
        assert result == Decimal("0")

    def test_with_model_inference(self) -> None:
        """Test with actual model inference (mocked)."""
        features = {
            "price_momentum": Decimal("0.5"),
            "volume_trend": Decimal("0.2"),
            "volatility": Decimal("0.3"),
        }

        mock_model = MagicMock()
        mock_model.predict.return_value = 0.75

        with patch("iatb.selection.drl_signal.load_drl_model", return_value=mock_model):
            result = compute_drl_signal(features, model="test_model")
            assert result == Decimal("0.75")
            mock_model.predict.assert_called_once()
