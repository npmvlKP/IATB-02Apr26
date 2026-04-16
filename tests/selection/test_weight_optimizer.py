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

    def test_optimize_weights_below_threshold_not_improved(self) -> None:
        """Test that IC below threshold marks as not improved."""
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
            mock_study.best_value = 0.02  # Below 0.03 threshold
            mock_optuna.create_study.return_value = mock_study
            mock_optuna.samplers.TPESampler.return_value = MagicMock()

            result = optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=5)

            assert result.regime == MarketRegime.BULL
            assert result.best_ic == Decimal("0.02")
            assert result.improved is False  # IC < 0.03 threshold

    def test_optimize_weights_uses_seed_reproducibly(self) -> None:
        """Test that seed produces reproducible results."""
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

            # Run with same seed twice
            optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=5, seed=42)
            optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=5, seed=42)

            # Verify sampler was called with seed
            mock_optuna.samplers.TPESampler.assert_called_with(seed=42)

    def test_optimize_weights_handles_all_regimes(self) -> None:
        """Test that optimization works for all market regimes."""
        from unittest.mock import MagicMock, patch

        history = [{"sentiment": Decimal("0.8")}] * 10
        returns: Sequence[Decimal] = [Decimal("0.1")] * 10

        for regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]:
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

                result = optimize_weights_for_regime(regime, history, returns, n_trials=5)

                assert result.regime == regime
                assert result.trials == 5

    def test_suggest_weights_normalizes_correctly(self) -> None:
        """Test that suggested weights are normalized to sum to 1."""
        from unittest.mock import MagicMock

        mock_trial = MagicMock()
        mock_trial.suggest_int.side_effect = [10, 20, 30, 40]

        weights = _suggest_weights(mock_trial)

        # Verify normalization: total = 10+20+30+40 = 100
        assert weights.sentiment == Decimal("0.10")
        assert weights.strength == Decimal("0.20")
        assert weights.volume_profile == Decimal("0.30")
        assert weights.drl == Decimal("0.40")

        # Verify sum is 1.0
        total = weights.sentiment + weights.strength + weights.volume_profile + weights.drl
        assert total == Decimal("1.0")

    def test_suggest_weights_calls_trial_methods(self) -> None:
        """Test that suggest_weights calls trial.suggest_int correctly."""
        from unittest.mock import MagicMock

        mock_trial = MagicMock()
        mock_trial.suggest_int.side_effect = [15, 25, 30, 30]

        _suggest_weights(mock_trial)

        # Verify suggest_int was called 4 times with correct params
        assert mock_trial.suggest_int.call_count == 4
        calls = mock_trial.suggest_int.call_args_list

        # Check first call for sentiment
        assert calls[0][0][0] == "sentiment"
        assert calls[0][0][1] == 5
        assert calls[0][0][2] == 50

        # Check other parameters
        assert calls[1][0][0] == "strength"
        assert calls[2][0][0] == "volume_profile"
        assert calls[3][0][0] == "drl"

    def test_compute_composites_handles_empty_history(self) -> None:
        """Test that empty history returns empty list."""
        history: list[dict[str, Decimal]] = []
        weights = type(
            "W",
            (),
            {
                "sentiment": Decimal("0.25"),
                "strength": Decimal("0.25"),
                "volume_profile": Decimal("0.25"),
                "drl": Decimal("0.25"),
            },
        )()
        composites = _compute_composites(history, weights)
        assert composites == []

    def test_compute_composites_handles_negative_values(self) -> None:
        """Test that negative signal values are handled correctly."""
        history = [
            {"sentiment": Decimal("-0.5"), "strength": Decimal("0.8")},
            {"sentiment": Decimal("0.3"), "strength": Decimal("-0.2")},
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
        # Negative values should be clamped to 0
        assert composites[0] == Decimal("0.15")  # max(0.5*-0.5 + 0.5*0.8, 0) = 0.15
        assert composites[1] == Decimal("0.05")  # max(0.5*0.3 + 0.5*-0.2, 0) = 0.05

    def test_optimize_weights_default_trials(self) -> None:
        """Test that default n_trials is used when not specified."""
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

            # Call without specifying n_trials (should default to 50)
            result = optimize_weights_for_regime(MarketRegime.BULL, history, returns)

            # Verify optimize was called with default 50 trials
            mock_study.optimize.assert_called_once()
            call_kwargs = mock_study.optimize.call_args[1]
            assert call_kwargs["n_trials"] == 50
            assert result.trials == 50
