"""
Tests for weight optimization module.
"""

import random
from collections.abc import Sequence
from decimal import Decimal

import numpy as np
import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.weight_optimizer import (
    _best_value,
    _build_sampler,
    _compute_composites,
    _create_study,
    _extract_best_weights,
    _load_optuna,
    _run_study,
    _suggest_weights,
    _validate_inputs,
    optimize_weights_for_regime,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)


class TestValidateInputs:
    """Test input validation."""

    def test_validate_inputs_length_mismatch_raises(self) -> None:
        """Test that mismatched lengths raise error."""
        history = [{"sentiment": Decimal("0.8")}]
        returns: Sequence[Decimal] = [Decimal("0.1"), Decimal("0.2")]
        with pytest.raises(ConfigError, match="equal length"):
            _validate_inputs(history, returns, 50)

    def test_validate_inputs_too_few_observations_raises(self) -> None:
        """Test that less than 10 observations raise error."""
        history = [{"sentiment": Decimal("0.8")}] * 9
        returns: Sequence[Decimal] = [Decimal("0.1")] * 9
        with pytest.raises(ConfigError, match="at least 10 observations"):
            _validate_inputs(history, returns, 50)

    def test_validate_inputs_zero_trials_raises(self) -> None:
        """Test that zero trials raise error."""
        history = [{"sentiment": Decimal("0.8")}] * 10
        returns: Sequence[Decimal] = [Decimal("0.1")] * 10
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(history, returns, 0)

    def test_validate_inputs_negative_trials_raises(self) -> None:
        """Test that negative trials raise error."""
        history = [{"sentiment": Decimal("0.8")}] * 10
        returns: Sequence[Decimal] = [Decimal("0.1")] * 10
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(history, returns, -1)

    def test_validate_inputs_valid_passes(self) -> None:
        """Test that valid inputs pass validation."""
        history = [{"sentiment": Decimal("0.8")}] * 10
        returns: Sequence[Decimal] = [Decimal("0.1")] * 10
        # Should not raise
        _validate_inputs(history, returns, 50)


class TestLoadOptuna:
    """Test Optuna loading."""

    def test_load_optuna_missing_dependency_raises(self) -> None:
        """Test that missing optuna raises error."""
        # Mock importlib to raise ModuleNotFoundError
        import importlib
        from unittest.mock import patch

        with patch.object(importlib, "import_module", side_effect=ModuleNotFoundError()):
            with pytest.raises(ConfigError, match="optuna dependency required"):
                _load_optuna()


class TestBuildSampler:
    """Test TPESampler building."""

    def test_build_sampler_missing_samplers_raises(self) -> None:
        """Test that missing samplers attribute raises error."""
        mock_optuna = type("MockOptuna", (), {})()
        with pytest.raises(ConfigError, match="TPESampler unavailable"):
            _build_sampler(mock_optuna, 42)

    def test_build_sampler_missing_tpe_raises(self) -> None:
        """Test that missing TPESampler class raises error."""
        mock_optuna = type("MockOptuna", (), {"samplers": None})()
        with pytest.raises(ConfigError, match="TPESampler unavailable"):
            _build_sampler(mock_optuna, 42)


class TestCreateStudy:
    """Test study creation."""

    def test_create_study_missing_create_raises(self) -> None:
        """Test that missing create_study raises error."""
        mock_optuna = type("MockOptuna", (), {})()
        mock_sampler = object()
        with pytest.raises(ConfigError, match="create_study unavailable"):
            _create_study(mock_optuna, mock_sampler)


class TestRunStudy:
    """Test study running."""

    def test_run_study_missing_optimize_raises(self) -> None:
        """Test that missing optimize method raises error."""
        mock_study = type("MockStudy", (), {})()
        with pytest.raises(ConfigError, match="optimize unavailable"):
            _run_study(mock_study, lambda: 0.5, 10)


class TestExtractBestWeights:
    """Test best weights extraction."""

    def test_extract_best_weights_missing_params_raises(self) -> None:
        """Test that missing best_params raises error."""
        mock_study = type("MockStudy", (), {})()
        with pytest.raises(ConfigError, match="best_params unavailable"):
            _extract_best_weights(mock_study)

    def test_extract_best_weights_non_dict_params_raises(self) -> None:
        """Test that non-dict best_params raises error."""
        mock_study = type("MockStudy", (), {"best_params": "not_a_dict"})()
        with pytest.raises(ConfigError, match="best_params unavailable"):
            _extract_best_weights(mock_study)

    def test_extract_best_weights_defaults_to_25(self) -> None:
        """Test that missing params default to 25."""
        mock_study = type("MockStudy", (), {"best_params": {}})()
        weights = _extract_best_weights(mock_study)
        assert weights.sentiment == Decimal("0.25")
        assert weights.strength == Decimal("0.25")
        assert weights.volume_profile == Decimal("0.25")
        assert weights.drl == Decimal("0.25")

    def test_extract_best_weights_normalizes(self) -> None:
        """Test that weights are normalized."""
        mock_study = type(
            "MockStudy",
            (),
            {"best_params": {"sentiment": 10, "strength": 20, "volume_profile": 30, "drl": 40}},
        )()
        weights = _extract_best_weights(mock_study)
        assert weights.sentiment == Decimal("0.10")
        assert weights.strength == Decimal("0.20")
        assert weights.volume_profile == Decimal("0.30")
        assert weights.drl == Decimal("0.40")


class TestBestValue:
    """Test best value extraction."""

    def test_best_value_missing_raises(self) -> None:
        """Test that missing best_value raises error."""
        mock_study = type("MockStudy", (), {})()
        with pytest.raises(ConfigError, match="best_value unavailable"):
            _best_value(mock_study)

    def test_best_value_float_returns_float(self) -> None:
        """Test that float best_value is returned."""
        mock_study = type("MockStudy", (), {"best_value": 0.85})()
        assert _best_value(mock_study) == 0.85

    def test_best_value_int_converts_to_float(self) -> None:
        """Test that int best_value is converted to float."""
        mock_study = type("MockStudy", (), {"best_value": 1})()
        assert _best_value(mock_study) == 1.0


class TestSuggestWeights:
    """Test weight suggestion from trial."""

    def test_suggest_weights_missing_suggest_int_raises(self) -> None:
        """Test that missing suggest_int raises error."""
        mock_trial = type("MockTrial", (), {})()
        with pytest.raises(ConfigError, match="suggest_int"):
            _suggest_weights(mock_trial)


class TestComputeComposites:
    """Test composite score computation."""

    def test_compute_composites_basic(self) -> None:
        """Test basic composite computation."""
        history = [
            {"sentiment": Decimal("0.8"), "strength": Decimal("0.7")},
            {"sentiment": Decimal("0.6"), "strength": Decimal("0.9")},
        ]
        weights = type(
            "W",
            (),
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.5"),
                "volume_profile": Decimal("0.0"),
                "drl": Decimal("0.0"),
            },
        )()
        composites = _compute_composites(history, weights)
        assert len(composites) == 2
        assert composites[0] == Decimal("0.75")  # 0.5*0.8 + 0.5*0.7
        assert composites[1] == Decimal("0.75")  # 0.5*0.6 + 0.5*0.9

    def test_compute_composites_with_missing_keys(self) -> None:
        """Test that missing keys default to 0."""
        history = [{"sentiment": Decimal("0.8")}, {"strength": Decimal("0.9")}]
        weights = type(
            "W",
            (),
            {
                "sentiment": Decimal("1.0"),
                "strength": Decimal("0.0"),
                "volume_profile": Decimal("0.0"),
                "drl": Decimal("0.0"),
            },
        )()
        composites = _compute_composites(history, weights)
        assert composites[0] == Decimal("0.8")
        assert composites[1] == Decimal("0.0")

    def test_compute_composites_clamps_to_01(self) -> None:
        """Test that composites are clamped to [0, 1]."""
        history = [{"sentiment": Decimal("1.5"), "strength": Decimal("1.5")}]
        weights = type(
            "W",
            (),
            {
                "sentiment": Decimal("1.0"),
                "strength": Decimal("1.0"),
                "volume_profile": Decimal("0.0"),
                "drl": Decimal("0.0"),
            },
        )()
        composites = _compute_composites(history, weights)
        assert composites[0] == Decimal("1.0")


class TestOptimizeWeightsForRegime:
    """Test main optimization function."""

    def test_optimize_weights_validates_inputs(self) -> None:
        """Test that optimization validates inputs."""
        from unittest.mock import patch

        history = [{"sentiment": Decimal("0.8")}] * 5
        returns: Sequence[Decimal] = [Decimal("0.1")] * 5

        with patch("iatb.selection.weight_optimizer._validate_inputs") as mock_validate:
            optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=5)
            mock_validate.assert_called_once()

    def test_optimize_weights_calls_study_methods(self) -> None:
        """Test that optimization calls study methods correctly."""
        from unittest.mock import MagicMock, patch

        history = [{"sentiment": Decimal("0.8")}] * 10
        returns: Sequence[Decimal] = [Decimal("0.1")] * 10

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            mock_optuna = MagicMock()
            mock_load.return_value = mock_optuna

            mock_study = MagicMock()
            mock_study.best_params = {
                "sentiment": 25,
                "strength": 25,
                "volume_profile": 25,
                "drl": 25,
            }
            mock_study.best_value = 0.05
            mock_optuna.create_study.return_value = mock_study
            mock_optuna.samplers.TPESampler.return_value = MagicMock()

            result = optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=5)

            assert result.regime == MarketRegime.BULL
            assert result.trials == 5
            assert result.best_ic == Decimal("0.05")
            assert result.improved is True  # IC >= 0.03 threshold
