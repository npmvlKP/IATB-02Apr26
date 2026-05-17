"""
Comprehensive coverage tests for weight_optimizer.py.

Tests weight optimization, regime mapping, and Optuna integration.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.weight_optimizer import (
    OptimizationResult,
    _create_objective,
    _extract_best_weights,
    _load_optuna,
    _validate_inputs,
    _weights_to_dict,
    optimize_all_regimes,
    optimize_weights_for_regime,
)


class TestOptimizeWeightsForRegime:
    """Test weight optimization for a single regime."""

    def test_valid_optimization_with_mock_optuna(self):
        """Test successful optimization with mocked Optuna."""
        signal_history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.4"),
                "drl": Decimal("0.7"),
            }
            for _ in range(10)
        ]
        forward_returns = [Decimal("0.01") * i for i in range(10)]

        # Mock Optuna components
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.05

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            mock_optuna = MagicMock()
            mock_optuna.samplers.TPESampler = MagicMock(return_value=MagicMock())
            mock_optuna.create_study = MagicMock(return_value=mock_study)
            mock_load.return_value = mock_optuna

            result = optimize_weights_for_regime(
                MarketRegime.SIDEWAYS,
                signal_history,
                forward_returns,
                n_trials=10,
                persist=False,
            )

            assert result.regime == MarketRegime.SIDEWAYS
            assert result.trials == 10
            assert isinstance(result.best_weights, RegimeWeights)
            assert result.best_ic == Decimal("0.05")

    def test_validation_error_mismatched_lengths(self):
        """Test that mismatched lengths raise ConfigError."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(5)]  # Different length

        with pytest.raises(
            ConfigError,
            match="signal_history and forward_returns must have equal length",
        ):
            optimize_weights_for_regime(
                MarketRegime.SIDEWAYS, signal_history, forward_returns
            )

    def test_validation_error_insufficient_observations(self):
        """Test that insufficient observations raise ConfigError."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(5)]  # < 10
        forward_returns = [Decimal("0.01") for _ in range(5)]

        with pytest.raises(ConfigError, match="at least 10 observations required"):
            optimize_weights_for_regime(
                MarketRegime.SIDEWAYS, signal_history, forward_returns
            )

    def test_validation_error_invalid_trials(self):
        """Test that invalid trial count raises ConfigError."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(10)]

        with pytest.raises(ConfigError, match="n_trials must be positive"):
            optimize_weights_for_regime(
                MarketRegime.SIDEWAYS, signal_history, forward_returns, n_trials=0
            )

    def test_optuna_not_available_raises_config_error(self):
        """Test that missing Optuna raises ConfigError."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(10)]

        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("optuna not found")

            with pytest.raises(ConfigError, match="optuna dependency required"):
                optimize_weights_for_regime(
                    MarketRegime.SIDEWAYS, signal_history, forward_returns
                )

    def test_improved_flag_based_on_ic_threshold(self):
        """Test that improved flag is set correctly based on IC."""
        signal_history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.4"),
                "drl": Decimal("0.7"),
            }
            for _ in range(10)
        ]
        forward_returns = [Decimal("0.01") * i for i in range(10)]

        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.05  # Above threshold of 0.03

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            mock_optuna = MagicMock()
            mock_optuna.samplers.TPESampler = MagicMock(return_value=MagicMock())
            mock_optuna.create_study = MagicMock(return_value=mock_study)
            mock_load.return_value = mock_optuna

            result = optimize_weights_for_regime(
                MarketRegime.SIDEWAYS, signal_history, forward_returns, persist=False
            )

            assert result.improved is True

    def test_persist_saves_to_config(self):
        """Test that persist=True saves weights to config."""
        signal_history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.4"),
                "drl": Decimal("0.7"),
            }
            for _ in range(10)
        ]
        forward_returns = [Decimal("0.01") * i for i in range(10)]

        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.05

        with patch("iatb.selection.weight_optimizer._load_optuna") as mock_load:
            with patch(
                "iatb.selection.weight_optimizer.get_config_manager"
            ) as mock_config:
                mock_optuna = MagicMock()
                mock_optuna.samplers.TPESampler = MagicMock(return_value=MagicMock())
                mock_optuna.create_study = MagicMock(return_value=mock_study)
                mock_load.return_value = mock_optuna

                optimize_weights_for_regime(
                    MarketRegime.SIDEWAYS, signal_history, forward_returns, persist=True
                )

                # Verify config manager was called
                mock_config.assert_called_once()
                mock_config.return_value.set_regime_weights.assert_called_once()


class TestOptimizeAllRegimes:
    """Test weight optimization for multiple regimes."""

    def test_optimize_multiple_regimes(self):
        """Test optimization across multiple market regimes."""
        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [
                {
                    "sentiment": Decimal("0.5"),
                    "strength": Decimal("0.6"),
                    "volume_profile": Decimal("0.4"),
                    "drl": Decimal("0.7"),
                }
                for _ in range(10)
            ],
            MarketRegime.BULL: [
                {
                    "sentiment": Decimal("0.7"),
                    "strength": Decimal("0.8"),
                    "volume_profile": Decimal("0.6"),
                    "drl": Decimal("0.9"),
                }
                for _ in range(10)
            ],
        }
        forward_returns_by_regime = {
            MarketRegime.SIDEWAYS: [Decimal("0.01") * i for i in range(10)],
            MarketRegime.BULL: [Decimal("0.02") * i for i in range(10)],
        }

        with patch(
            "iatb.selection.weight_optimizer.optimize_weights_for_regime"
        ) as mock_opt:
            mock_opt.return_value = OptimizationResult(
                regime=MarketRegime.SIDEWAYS,
                best_weights=RegimeWeights(
                    sentiment=Decimal("0.25"),
                    strength=Decimal("0.25"),
                    volume_profile=Decimal("0.25"),
                    drl=Decimal("0.25"),
                ),
                best_ic=Decimal("0.05"),
                trials=10,
                improved=True,
            )

            results = optimize_all_regimes(
                signal_history_by_regime, forward_returns_by_regime, n_trials=10
            )

            assert len(results) == 2
            assert MarketRegime.SIDEWAYS in results
            assert MarketRegime.BULL in results

    def test_skip_regime_with_no_returns(self):
        """Test that regimes without forward returns are skipped."""
        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [{"sentiment": Decimal("0.5")} for _ in range(10)],
        }
        forward_returns_by_regime = {
            MarketRegime.SIDEWAYS: [],  # Empty
        }

        results = optimize_all_regimes(
            signal_history_by_regime, forward_returns_by_regime
        )

        assert len(results) == 0

    def test_handle_exception_for_single_regime(self):
        """Test that exceptions for individual regimes don't break entire run."""
        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [{"sentiment": Decimal("0.5")} for _ in range(10)],
        }
        forward_returns_by_regime = {
            MarketRegime.SIDEWAYS: [Decimal("0.01") for _ in range(10)],
        }

        with patch(
            "iatb.selection.weight_optimizer.optimize_weights_for_regime"
        ) as mock_opt:
            mock_opt.side_effect = Exception("Optuna failed")

            results = optimize_all_regimes(
                signal_history_by_regime, forward_returns_by_regime
            )

            assert len(results) == 0


class TestHelperFunctions:
    """Test helper functions."""

    def test_validate_inputs_valid(self):
        """Test validation with valid inputs."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(10)]
        n_trials = 10

        # Should not raise
        _validate_inputs(signal_history, forward_returns, n_trials)

    def test_validate_inputs_mismatched_length(self):
        """Test validation raises on mismatched length."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(5)]

        with pytest.raises(
            ConfigError,
            match="signal_history and forward_returns must have equal length",
        ):
            _validate_inputs(signal_history, forward_returns, 10)

    def test_validate_inputs_insufficient_observations(self):
        """Test validation raises on insufficient observations."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(5)]
        forward_returns = [Decimal("0.01") for _ in range(5)]

        with pytest.raises(ConfigError, match="at least 10 observations required"):
            _validate_inputs(signal_history, forward_returns, 10)

    def test_validate_inputs_invalid_trials(self):
        """Test validation raises on invalid trials."""
        signal_history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        forward_returns = [Decimal("0.01") for _ in range(10)]

        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(signal_history, forward_returns, 0)

    def test_load_optuna_success(self):
        """Test successful Optuna loading."""
        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            result = _load_optuna()
            assert result is not None
            mock_import.assert_called_once_with("optuna")

    def test_load_optuna_failure(self):
        """Test Optuna loading failure."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("optuna not found")

            with pytest.raises(ConfigError, match="optuna dependency required"):
                _load_optuna()

    def test_extract_best_weights_valid(self):
        """Test extracting best weights from study."""
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 30,
            "strength": 20,
            "volume_profile": 25,
            "drl": 25,
        }

        weights = _extract_best_weights(mock_study)

        assert isinstance(weights, RegimeWeights)
        assert weights.sentiment == Decimal("0.3")
        assert weights.strength == Decimal("0.2")
        assert weights.volume_profile == Decimal("0.25")
        assert weights.drl == Decimal("0.25")

    def test_weights_to_dict(self):
        """Test converting RegimeWeights to dict."""
        weights = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )

        result = _weights_to_dict(weights)

        assert result == {
            "sentiment": "0.25",
            "strength": "0.25",
            "volume_profile": "0.25",
            "drl": "0.25",
        }

    def test_create_objective(self):
        """Test objective function creation."""
        signal_history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.4"),
                "drl": Decimal("0.7"),
            }
            for _ in range(10)
        ]
        forward_returns = [Decimal("0.01") * i for i in range(10)]

        objective = _create_objective(signal_history, forward_returns)

        # Create mock trial
        mock_trial = MagicMock()
        mock_trial.suggest_int = MagicMock(side_effect=lambda name, low, high: 25)

        result = objective(mock_trial)

        # Result should be a float (Optuna requirement)
        assert isinstance(result, float)
