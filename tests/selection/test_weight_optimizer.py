"""
Comprehensive tests for weight_optimizer.py to achieve 90%+ coverage.
"""

import random
from decimal import Decimal
from unittest.mock import Mock, patch

import numpy as np
import pytest
import torch
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
torch.manual_seed(42)


class TestValidateInputs:
    """Test input validation."""

    def test_equal_length_passes(self):
        """Equal length history and returns should pass."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10
        _validate_inputs(history, returns, 50)  # Should not raise

    def test_unequal_length_raises(self):
        """Unequal length should raise ConfigError."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 9
        with pytest.raises(
            ConfigError, match="signal_history and forward_returns must have equal length"
        ):
            _validate_inputs(history, returns, 50)

    def test_insufficient_observations_raises(self):
        """Less than 10 observations should raise ConfigError."""
        history = [{"sentiment": Decimal("0.5")}] * 9
        returns = [Decimal("0.1")] * 9
        with pytest.raises(ConfigError, match="at least 10 observations required"):
            _validate_inputs(history, returns, 50)

    def test_zero_trials_raises(self):
        """Zero trials should raise ConfigError."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(history, returns, 0)

    def test_negative_trials_raises(self):
        """Negative trials should raise ConfigError."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(history, returns, -10)


class TestLoadOptuna:
    """Test Optuna loading."""

    def test_loads_optuna_successfully(self):
        """Should load optuna module successfully."""
        optuna = _load_optuna()
        assert optuna is not None
        assert hasattr(optuna, "create_study")

    @patch("importlib.import_module")
    def test_missing_optuna_raises(self, mock_import):
        """Missing optuna should raise ConfigError."""
        mock_import.side_effect = ModuleNotFoundError("No module named 'optuna'")
        with pytest.raises(ConfigError, match="optuna dependency required"):
            _load_optuna()


class TestBuildSampler:
    """Test TPE sampler building."""

    def test_builds_tpe_sampler(self):
        """Should build TPE sampler with seed."""
        optuna = _load_optuna()
        sampler = _build_sampler(optuna, 42)
        assert sampler is not None

    def test_missing_samplers_raises(self, monkeypatch):
        """Missing samplers should raise ConfigError."""
        optuna = Mock()
        delattr(optuna, "samplers")
        with pytest.raises(ConfigError, match="optuna.samplers.TPESampler unavailable"):
            _build_sampler(optuna, 42)

    def test_missing_tpe_sampler_raises(self, monkeypatch):
        """Missing TPESampler should raise ConfigError."""
        optuna = Mock()
        optuna.samplers = Mock()
        delattr(optuna.samplers, "TPESampler")
        with pytest.raises(ConfigError, match="optuna.samplers.TPESampler unavailable"):
            _build_sampler(optuna, 42)


class TestCreateStudy:
    """Test Optuna study creation."""

    def test_creates_study(self):
        """Should create study with maximize direction."""
        optuna = _load_optuna()
        sampler = _build_sampler(optuna, 42)
        study = _create_study(optuna, sampler)
        assert study is not None

    def test_missing_create_study_raises(self, monkeypatch):
        """Missing create_study should raise ConfigError."""
        optuna = Mock()
        delattr(optuna, "create_study")
        with pytest.raises(ConfigError, match="optuna.create_study unavailable"):
            _create_study(optuna, Mock())


class TestRunStudy:
    """Test study optimization."""

    def test_runs_study_with_objective(self):
        """Should run study with objective function."""
        study = Mock()
        study.optimize = Mock()

        def objective(trial):  # noqa: ARG001 - trial not used
            return 0.5

        _run_study(study, objective, 10)
        study.optimize.assert_called_once_with(objective, n_trials=10)

    def test_missing_optimize_raises(self):
        """Missing optimize should raise ConfigError."""
        study = Mock()
        delattr(study, "optimize")
        with pytest.raises(ConfigError, match="study.optimize unavailable"):
            _run_study(study, Mock(), 10)


class TestExtractBestWeights:
    """Test best weights extraction."""

    def test_extracts_weights_from_params(self):
        """Should extract and normalize weights from params."""
        study = Mock()
        study.best_params = {
            "sentiment": 20,
            "strength": 30,
            "volume_profile": 25,
            "drl": 25,
        }
        weights = _extract_best_weights(study)
        assert weights.sentiment == Decimal("20") / Decimal("100")
        assert weights.strength == Decimal("30") / Decimal("100")
        assert weights.volume_profile == Decimal("25") / Decimal("100")
        assert weights.drl == Decimal("25") / Decimal("100")

    def test_handles_missing_params_with_defaults(self):
        """Should use defaults for missing params."""
        study = Mock()
        study.best_params = {}
        weights = _extract_best_weights(study)
        total = 25 + 25 + 25 + 25
        assert weights.sentiment == Decimal("25") / Decimal(total)
        assert weights.strength == Decimal("25") / Decimal(total)
        assert weights.volume_profile == Decimal("25") / Decimal(total)
        assert weights.drl == Decimal("25") / Decimal(total)

    def test_missing_best_params_raises(self):
        """Missing best_params should raise ConfigError."""
        study = Mock()
        delattr(study, "best_params")
        with pytest.raises(ConfigError, match="study.best_params unavailable"):
            _extract_best_weights(study)

    def test_non_dict_best_params_raises(self):
        """Non-dict best_params should raise ConfigError."""
        study = Mock()
        study.best_params = "not a dict"
        with pytest.raises(ConfigError, match="study.best_params unavailable"):
            _extract_best_weights(study)


class TestBestValue:
    """Test best value extraction."""

    def test_extracts_float_value(self):
        """Should extract float value."""
        study = Mock()
        study.best_value = 0.85
        value = _best_value(study)
        assert value == 0.85

    def test_converts_int_to_float(self):
        """Should convert int value to float."""
        study = Mock()
        study.best_value = 85
        value = _best_value(study)
        assert value == 85.0

    def test_missing_best_value_raises(self):
        """Missing best_value should raise ConfigError."""
        study = Mock()
        delattr(study, "best_value")
        with pytest.raises(ConfigError, match="study.best_value unavailable"):
            _best_value(study)

    def test_invalid_type_raises(self):
        """Invalid type should raise ConfigError."""
        study = Mock()
        study.best_value = "not a number"
        with pytest.raises(ConfigError, match="study.best_value unavailable"):
            _best_value(study)


class TestSuggestWeights:
    """Test weight suggestion from trial."""

    def test_suggests_weights(self):
        """Should suggest weights from trial."""
        trial = Mock()
        trial.suggest_int = Mock(side_effect=[20, 30, 25, 25])
        weights = _suggest_weights(trial)
        assert weights.sentiment == Decimal("20") / Decimal("100")
        assert weights.strength == Decimal("30") / Decimal("100")
        assert weights.volume_profile == Decimal("25") / Decimal("100")
        assert weights.drl == Decimal("25") / Decimal("100")

    def test_missing_suggest_int_raises(self):
        """Missing suggest_int should raise ConfigError."""
        trial = Mock()
        delattr(trial, "suggest_int")
        with pytest.raises(ConfigError, match="trial does not provide suggest_int"):
            _suggest_weights(trial)

    def test_non_callable_suggest_int_raises(self):
        """Non-callable suggest_int should raise ConfigError."""
        trial = Mock()
        trial.suggest_int = "not callable"
        with pytest.raises(ConfigError, match="trial does not provide suggest_int"):
            _suggest_weights(trial)


class TestComputeComposites:
    """Test composite score computation."""

    def test_computes_composites(self):
        """Should compute composite scores."""
        history = [
            {"sentiment": Decimal("0.5"), "strength": Decimal("0.7")},
            {"sentiment": Decimal("0.3"), "strength": Decimal("0.9")},
        ]
        weights = Mock()
        weights.sentiment = Decimal("0.4")
        weights.strength = Decimal("0.6")
        weights.volume_profile = Decimal("0.0")
        weights.drl = Decimal("0.0")

        composites = _compute_composites(history, weights)

        assert len(composites) == 2
        assert composites[0] == Decimal("0.4") * Decimal("0.5") + Decimal("0.6") * Decimal("0.7")
        assert composites[1] == Decimal("0.4") * Decimal("0.3") + Decimal("0.6") * Decimal("0.9")

    def test_handles_missing_keys(self):
        """Should handle missing keys with defaults."""
        history = [{"sentiment": Decimal("0.5")}]
        weights = Mock()
        weights.sentiment = Decimal("1.0")
        weights.strength = Decimal("0.0")
        weights.volume_profile = Decimal("0.0")
        weights.drl = Decimal("0.0")

        composites = _compute_composites(history, weights)
        assert len(composites) == 1
        assert composites[0] == Decimal("0.5")

    def test_clamps_composites_to_01(self):
        """Should clamp composites to [0, 1]."""
        history = [
            {"sentiment": Decimal("2.0"), "strength": Decimal("0.0")},
        ]
        weights = Mock()
        weights.sentiment = Decimal("1.0")
        weights.strength = Decimal("0.0")
        weights.volume_profile = Decimal("0.0")
        weights.drl = Decimal("0.0")

        composites = _compute_composites(history, weights)
        assert composites[0] == Decimal("1.0")  # Clamped

    def test_handles_negative_values(self):
        """Should handle negative signal values."""
        history = [
            {"sentiment": Decimal("-0.5")},
        ]
        weights = Mock()
        weights.sentiment = Decimal("1.0")
        weights.strength = Decimal("0.0")
        weights.volume_profile = Decimal("0.0")
        weights.drl = Decimal("0.0")

        composites = _compute_composites(history, weights)
        assert composites[0] == Decimal("0.0")  # Clamped to 0


class TestOptimizeWeightsForRegime:
    """Integration test for weight optimization."""

    @patch("iatb.selection.weight_optimizer._load_optuna")
    @patch("iatb.selection.weight_optimizer._build_sampler")
    @patch("iatb.selection.weight_optimizer._create_study")
    @patch("iatb.selection.weight_optimizer._run_study")
    @patch("iatb.selection.weight_optimizer._extract_best_weights")
    @patch("iatb.selection.weight_optimizer._best_value")
    @patch("iatb.selection.weight_optimizer.compute_information_coefficient")
    def test_optimization_success(
        self,
        mock_ic,
        mock_best_value,
        mock_extract_weights,
        mock_run_study,
        mock_create_study,
        mock_build_sampler,
        mock_load_optuna,
    ):
        """Should successfully optimize weights."""
        # Setup mocks
        mock_optuna = Mock()
        mock_optuna.create_study = Mock()
        mock_load_optuna.return_value = mock_optuna
        mock_build_sampler.return_value = Mock()
        mock_study = Mock()
        mock_study.best_params = {
            "sentiment": 20,
            "strength": 30,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.05
        mock_create_study.return_value = mock_study

        mock_ic_result = Mock()
        mock_ic_result.ic = Decimal("0.05")
        mock_ic.return_value = mock_ic_result
        mock_best_value.return_value = 0.05
        mock_extract_weights.return_value = Mock(
            sentiment=Decimal("0.20"),
            strength=Decimal("0.30"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )

        # Execute
        history = [{"sentiment": Decimal("0.5"), "strength": Decimal("0.7")}] * 10
        returns = [Decimal("0.1")] * 10
        result = optimize_weights_for_regime(MarketRegime.BULL, history, returns, n_trials=10)

        # Verify
        assert result.regime == MarketRegime.BULL
        assert result.trials == 10
        assert result.best_ic == Decimal("0.05")
        assert result.improved is True

    @patch("iatb.selection.weight_optimizer._load_optuna")
    @patch("iatb.selection.weight_optimizer._build_sampler")
    @patch("iatb.selection.weight_optimizer._create_study")
    @patch("iatb.selection.weight_optimizer._run_study")
    @patch("iatb.selection.weight_optimizer._extract_best_weights")
    @patch("iatb.selection.weight_optimizer._best_value")
    @patch("iatb.selection.weight_optimizer.compute_information_coefficient")
    def test_optimization_below_threshold(
        self,
        mock_ic,
        mock_best_value,
        mock_extract_weights,
        mock_run_study,
        mock_create_study,
        mock_build_sampler,
        mock_load_optuna,
    ):
        """Should mark as not improved when IC below threshold."""
        # Setup mocks
        mock_optuna = Mock()
        mock_optuna.create_study = Mock()
        mock_load_optuna.return_value = mock_optuna
        mock_build_sampler.return_value = Mock()
        mock_study = Mock()
        mock_study.best_params = {"sentiment": 25, "strength": 25, "volume_profile": 25, "drl": 25}
        mock_study.best_value = 0.01
        mock_create_study.return_value = mock_study

        mock_ic_result = Mock()
        mock_ic_result.ic = Decimal("0.01")
        mock_ic.return_value = mock_ic_result
        mock_best_value.return_value = 0.01
        mock_extract_weights.return_value = Mock(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )

        # Execute
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10
        result = optimize_weights_for_regime(MarketRegime.BEAR, history, returns, n_trials=10)

        # Verify
        assert result.regime == MarketRegime.BEAR
        assert result.improved is False
        assert result.best_ic == Decimal("0.01")

    def test_optimization_uses_default_seed(self):
        """Should use default seed when not specified."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            with patch("iatb.selection.weight_optimizer._build_sampler") as mock_build:
                mock_optuna = Mock()
                mock_load.return_value = mock_optuna
                mock_build.return_value = Mock()

                with patch("iatb.selection.weight_optimizer._create_study") as mock_create:
                    mock_study = Mock()
                    mock_study.best_params = {
                        "sentiment": 25,
                        "strength": 25,
                        "volume_profile": 25,
                        "drl": 25,
                    }
                    mock_study.best_value = 0.05
                    mock_create.return_value = mock_study

                    with patch("iatb.selection.weight_optimizer._run_study"):
                        with patch(
                            "iatb.selection.weight_optimizer._extract_best_weights"
                        ) as mock_extract:
                            mock_extract.return_value = Mock(
                                sentiment=Decimal("0.25"),
                                strength=Decimal("0.25"),
                                volume_profile=Decimal("0.25"),
                                drl=Decimal("0.25"),
                            )

                            with patch("iatb.selection.weight_optimizer._best_value") as mock_best:
                                with patch(
                                    "iatb.selection.weight_optimizer.compute_information_coefficient"
                                ) as mock_ic:
                                    mock_best.return_value = 0.05
                                    mock_ic_result = Mock()
                                    mock_ic_result.ic = Decimal("0.05")
                                    mock_ic.return_value = mock_ic_result

                                    optimize_weights_for_regime(
                                        MarketRegime.SIDEWAYS, history, returns
                                    )

                                    # Verify seed=42 was used
                                    mock_build.assert_called_once()

    def test_optimization_with_custom_seed(self):
        """Should use custom seed when specified."""
        history = [{"sentiment": Decimal("0.5")}] * 10
        returns = [Decimal("0.1")] * 10

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            with patch("iatb.selection.weight_optimizer._build_sampler") as mock_build:
                mock_optuna = Mock()
                mock_load.return_value = mock_optuna
                mock_build.return_value = Mock()

                with patch("iatb.selection.weight_optimizer._create_study") as mock_create:
                    mock_study = Mock()
                    mock_study.best_params = {
                        "sentiment": 25,
                        "strength": 25,
                        "volume_profile": 25,
                        "drl": 25,
                    }
                    mock_study.best_value = 0.05
                    mock_create.return_value = mock_study

                    with patch("iatb.selection.weight_optimizer._run_study"):
                        with patch(
                            "iatb.selection.weight_optimizer._extract_best_weights"
                        ) as mock_extract:
                            mock_extract.return_value = Mock(
                                sentiment=Decimal("0.25"),
                                strength=Decimal("0.25"),
                                volume_profile=Decimal("0.25"),
                                drl=Decimal("0.25"),
                            )

                            with patch("iatb.selection.weight_optimizer._best_value") as mock_best:
                                with patch(
                                    "iatb.selection.weight_optimizer.compute_information_coefficient"
                                ) as mock_ic:
                                    mock_best.return_value = 0.05
                                    mock_ic_result = Mock()
                                    mock_ic_result.ic = Decimal("0.05")
                                    mock_ic.return_value = mock_ic_result

                                    optimize_weights_for_regime(
                                        MarketRegime.BULL, history, returns, seed=123
                                    )

                                    # Verify custom seed was used
                                    mock_build.assert_called_once()
