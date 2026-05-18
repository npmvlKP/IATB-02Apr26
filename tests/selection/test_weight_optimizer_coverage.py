"""
Comprehensive coverage tests for weight_optimizer.py.

Tests weight optimization, Optuna integration, regime mapping, and error paths.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.weight_optimizer import (
    OptimizationResult,
    _best_value,
    _build_sampler,
    _compute_composites,
    _create_study,
    _extract_best_weights,
    _load_optuna,
    _log_optimization_result,
    _run_study,
    _suggest_weights,
    _validate_inputs,
    _weights_to_dict,
    optimize_all_regimes,
    optimize_weights_for_regime,
)


class TestValidateInputs:
    """Test _validate_inputs function."""

    def test_validate_inputs_valid(self) -> None:
        """Test with valid inputs."""
        history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.7"),
                "drl": Decimal("0.8"),
            }
            for _ in range(10)
        ]
        returns = [Decimal("0.05") for _ in range(10)]
        _validate_inputs(history, returns, 50)  # Should not raise

    def test_validate_inputs_mismatched_lengths(self) -> None:
        """Test raises ConfigError when history and returns lengths differ."""
        history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        returns = [Decimal("0.05") for _ in range(5)]

        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(history, returns, 50)
        assert "signal_history and forward_returns must have equal length" in str(
            exc_info.value
        )

    def test_validate_inputs_insufficient_observations(self) -> None:
        """Test raises ConfigError when fewer than 10 observations."""
        history = [{"sentiment": Decimal("0.5")} for _ in range(5)]
        returns = [Decimal("0.05") for _ in range(5)]

        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(history, returns, 50)
        assert "at least 10 observations required" in str(exc_info.value)

    def test_validate_inputs_invalid_n_trials_zero(self) -> None:
        """Test raises ConfigError when n_trials is zero."""
        history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        returns = [Decimal("0.05") for _ in range(10)]

        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(history, returns, 0)
        assert "n_trials must be positive" in str(exc_info.value)

    def test_validate_inputs_invalid_n_trials_negative(self) -> None:
        """Test raises ConfigError when n_trials is negative."""
        history = [{"sentiment": Decimal("0.5")} for _ in range(10)]
        returns = [Decimal("0.05") for _ in range(10)]

        with pytest.raises(ConfigError) as exc_info:
            _validate_inputs(history, returns, -10)
        assert "n_trials must be positive" in str(exc_info.value)


class TestLoadOptuna:
    """Test _load_optuna function."""

    def test_load_optuna_success(self) -> None:
        """Test successful Optuna import."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_import.return_value = mock_module
            result = _load_optuna()
            assert result == mock_module
            mock_import.assert_called_once_with("optuna")

    def test_load_optuna_module_not_found(self) -> None:
        """Test raises ConfigError when Optuna not installed."""
        with patch(
            "importlib.import_module", side_effect=ModuleNotFoundError("optuna")
        ):
            with pytest.raises(ConfigError) as exc_info:
                _load_optuna()
            assert "optuna dependency required" in str(exc_info.value)


class TestBuildSampler:
    """Test _build_sampler function."""

    def test_build_sampler_success(self) -> None:
        """Test successful sampler creation."""
        mock_optuna = MagicMock()
        mock_sampler_cls = MagicMock(return_value="sampler_instance")
        mock_optuna.samplers.TPESampler = mock_sampler_cls

        result = _build_sampler(mock_optuna, 42)
        assert result == "sampler_instance"
        mock_sampler_cls.assert_called_once_with(seed=42)

    def test_build_sampler_no_samplers_attr(self) -> None:
        """Test raises ConfigError when optuna.samplers missing."""
        mock_optuna = MagicMock()
        del mock_optuna.samplers

        with pytest.raises(ConfigError) as exc_info:
            _build_sampler(mock_optuna, 42)
        assert "optuna.samplers.TPESampler unavailable" in str(exc_info.value)

    def test_build_sampler_no_tpesampler(self) -> None:
        """Test raises ConfigError when TPESampler missing."""
        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler = None

        with pytest.raises(ConfigError) as exc_info:
            _build_sampler(mock_optuna, 42)
        assert "optuna.samplers.TPESampler unavailable" in str(exc_info.value)


class TestCreateStudy:
    """Test _create_study function."""

    def test_create_study_success(self) -> None:
        """Test successful study creation."""
        mock_optuna = MagicMock()
        mock_study = MagicMock()
        mock_optuna.create_study = MagicMock(return_value=mock_study)

        sampler = MagicMock()
        result = _create_study(mock_optuna, sampler)
        assert result == mock_study
        mock_optuna.create_study.assert_called_once_with(
            direction="maximize", sampler=sampler
        )

    def test_create_study_no_create_study(self) -> None:
        """Test raises ConfigError when create_study missing."""
        mock_optuna = MagicMock()
        mock_optuna.create_study = None

        with pytest.raises(ConfigError) as exc_info:
            _create_study(mock_optuna, MagicMock())
        assert "optuna.create_study unavailable" in str(exc_info.value)


class TestRunStudy:
    """Test _run_study function."""

    def test_run_study_success(self) -> None:
        """Test successful study optimization."""
        mock_study = MagicMock()
        objective = MagicMock()

        _run_study(mock_study, objective, 50)
        mock_study.optimize.assert_called_once_with(objective, n_trials=50)

    def test_run_study_no_optimize(self) -> None:
        """Test raises ConfigError when optimize missing."""
        mock_study = MagicMock()
        mock_study.optimize = None

        with pytest.raises(ConfigError) as exc_info:
            _run_study(mock_study, MagicMock(), 50)
        assert "study.optimize unavailable" in str(exc_info.value)


class TestSuggestWeights:
    """Test _suggest_weights function."""

    def test_suggest_weights_success(self) -> None:
        """Test successful weight suggestion."""
        mock_trial = MagicMock()
        mock_trial.suggest_int = MagicMock(side_effect=[10, 20, 30, 40])

        result = _suggest_weights(mock_trial)
        assert isinstance(result, RegimeWeights)
        # Check weights sum to 1
        total = result.sentiment + result.strength + result.volume_profile + result.drl
        assert total == Decimal("1")

    def test_suggest_weights_no_suggest_int(self) -> None:
        """Test raises ConfigError when suggest_int missing."""
        mock_trial = MagicMock()
        mock_trial.suggest_int = None

        with pytest.raises(ConfigError) as exc_info:
            _suggest_weights(mock_trial)
        assert "trial does not provide suggest_int()" in str(exc_info.value)


class TestExtractBestWeights:
    """Test _extract_best_weights function."""

    def test_extract_best_weights_success(self) -> None:
        """Test successful weight extraction."""
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": "10",
            "strength": "20",
            "volume_profile": "30",
            "drl": "40",
        }

        result = _extract_best_weights(mock_study)
        assert isinstance(result, RegimeWeights)
        total = result.sentiment + result.strength + result.volume_profile + result.drl
        assert total == Decimal("1")

    def test_extract_best_weights_missing_params(self) -> None:
        """Test uses defaults when params missing."""
        mock_study = MagicMock()
        mock_study.best_params = {}

        result = _extract_best_weights(mock_study)
        assert isinstance(result, RegimeWeights)
        # All should be 0.25 (default/total)
        assert result.sentiment == Decimal("0.25")

    def test_extract_best_weights_no_best_params(self) -> None:
        """Test raises ConfigError when best_params missing."""
        mock_study = MagicMock()
        mock_study.best_params = None

        with pytest.raises(ConfigError) as exc_info:
            _extract_best_weights(mock_study)
        assert "study.best_params unavailable" in str(exc_info.value)


class TestBestValue:
    """Test _best_value function."""

    def test_best_value_float(self) -> None:
        """Test with float value."""
        mock_study = MagicMock()
        mock_study.best_value = 0.05

        result = _best_value(mock_study)
        assert result == 0.05

    def test_best_value_int(self) -> None:
        """Test with int value."""
        mock_study = MagicMock()
        mock_study.best_value = 5

        result = _best_value(mock_study)
        assert result == 5.0

    def test_best_value_no_best_value(self) -> None:
        """Test raises ConfigError when best_value missing."""
        mock_study = MagicMock()
        mock_study.best_value = None

        with pytest.raises(ConfigError) as exc_info:
            _best_value(mock_study)
        assert "study.best_value unavailable" in str(exc_info.value)

    def test_best_value_invalid_type(self) -> None:
        """Test raises ConfigError when best_value is invalid type."""
        mock_study = MagicMock()
        mock_study.best_value = "invalid"

        with pytest.raises(ConfigError) as exc_info:
            _best_value(mock_study)
        assert "study.best_value unavailable" in str(exc_info.value)


class TestWeightsToDict:
    """Test _weights_to_dict function."""

    def test_weights_to_dict_success(self) -> None:
        """Test successful conversion to dict."""
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


class TestComputeComposites:
    """Test _compute_composites function."""

    def test_compute_composites_basic(self) -> None:
        """Test basic composite computation."""
        history = [
            {"sentiment": Decimal("0.5"), "strength": Decimal("0.6")},
            {"sentiment": Decimal("0.7"), "strength": Decimal("0.8")},
        ]
        weights = RegimeWeights(
            sentiment=Decimal("0.5"),
            strength=Decimal("0.5"),
            volume_profile=Decimal("0.0"),
            drl=Decimal("0.0"),
        )

        result = _compute_composites(history, weights)
        assert len(result) == 2
        assert result[0] == Decimal("0.55")  # 0.5*0.5 + 0.6*0.5
        assert result[1] == Decimal("0.75")  # 0.7*0.5 + 0.8*0.5

    def test_compute_composites_with_missing_keys(self) -> None:
        """Test computation with missing keys (defaults to 0)."""
        history = [
            {"sentiment": Decimal("0.5")},  # Missing strength
        ]
        weights = RegimeWeights(
            sentiment=Decimal("0.5"),
            strength=Decimal("0.5"),
            volume_profile=Decimal("0.0"),
            drl=Decimal("0.0"),
        )

        result = _compute_composites(history, weights)
        assert len(result) == 1
        assert result[0] == Decimal("0.25")  # 0.5*0.5 + 0*0.5

    def test_compute_composites_clamping(self) -> None:
        """Test that composites are clamped to [0, 1]."""
        history = [{"sentiment": Decimal("1.5"), "strength": Decimal("0.5")}]
        weights = RegimeWeights(
            sentiment=Decimal("0.8"),
            strength=Decimal("0.2"),
            volume_profile=Decimal("0.0"),
            drl=Decimal("0.0"),
        )

        result = _compute_composites(history, weights)
        # 1.5*0.8 + 0.5*0.2 = 1.2 + 0.1 = 1.3, clamped to 1.0
        assert result[0] == Decimal("1")  # Clamped to 1


class TestLogOptimizationResult:
    """Test _log_optimization_result function."""

    def test_log_optimization_result_improved(self, caplog) -> None:
        """Test logging for improved result."""
        _log_optimization_result(MarketRegime.SIDEWAYS, Decimal("0.05"), True)
        assert "Weight optimization for SIDEWAYS: IC=0.0500 (improved)" in caplog.text

    def test_log_optimization_result_below_threshold(self, caplog) -> None:
        """Test logging for result below threshold."""
        _log_optimization_result(MarketRegime.SIDEWAYS, Decimal("0.02"), False)
        assert (
            "Weight optimization for SIDEWAYS: IC=0.0200 (below threshold)"
            in caplog.text
        )


class TestOptimizeWeightsForRegime:
    """Test optimize_weights_for_regime function."""

    @patch("iatb.selection.weight_optimizer._load_optuna")
    @patch("iatb.selection.weight_optimizer._build_sampler")
    @patch("iatb.selection.weight_optimizer._create_study")
    @patch("iatb.selection.weight_optimizer._run_study")
    @patch("iatb.selection.weight_optimizer._extract_best_weights")
    @patch("iatb.selection.weight_optimizer._best_value")
    @patch("iatb.selection.weight_optimizer._save_weights_to_config")
    def test_optimize_weights_for_regime_success(
        self,
        mock_save_weights,
        mock_best_value,
        mock_extract_weights,
        mock_run_study,
        mock_create_study,
        mock_build_sampler,
        mock_load_optuna,
    ) -> None:
        """Test successful weight optimization."""
        # Setup mocks
        mock_optuna = MagicMock()
        mock_load_optuna.return_value = mock_optuna
        mock_sampler = MagicMock()
        mock_build_sampler.return_value = mock_sampler
        mock_study = MagicMock()
        mock_create_study.return_value = mock_study
        mock_weights = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )
        mock_extract_weights.return_value = mock_weights
        mock_best_value.return_value = 0.05

        history = [
            {
                "sentiment": Decimal("0.5"),
                "strength": Decimal("0.6"),
                "volume_profile": Decimal("0.7"),
                "drl": Decimal("0.8"),
            }
            for _ in range(10)
        ]
        returns = [Decimal("0.05") for _ in range(10)]

        result = optimize_weights_for_regime(
            MarketRegime.SIDEWAYS, history, returns, n_trials=50, persist=False
        )

        assert isinstance(result, OptimizationResult)
        assert result.regime == MarketRegime.SIDEWAYS
        assert result.best_weights == mock_weights
        assert result.best_ic == Decimal("0.05")
        assert result.trials == 50
        assert result.improved is True

    @patch("iatb.selection.weight_optimizer._load_optuna")
    @patch("iatb.selection.weight_optimizer._save_weights_to_config")
    def test_optimize_weights_for_regime_with_persist(
        self,
        mock_save_weights,
        mock_load_optuna,
        caplog,
    ) -> None:
        """Test weight optimization with persistence."""
        # Setup minimal mocks
        mock_optuna = MagicMock()
        mock_load_optuna.return_value = mock_optuna
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": "10",
            "strength": "10",
            "volume_profile": "10",
            "drl": "10",
        }
        mock_study.best_value = 0.05

        with patch("iatb.selection.weight_optimizer._build_sampler"):
            with patch(
                "iatb.selection.weight_optimizer._create_study", return_value=mock_study
            ):
                with patch("iatb.selection.weight_optimizer._run_study"):
                    history = [
                        {
                            "sentiment": Decimal("0.5"),
                            "strength": Decimal("0.6"),
                            "volume_profile": Decimal("0.7"),
                            "drl": Decimal("0.8"),
                        }
                        for _ in range(10)
                    ]
                    returns = [Decimal("0.05") for _ in range(10)]

                    optimize_weights_for_regime(
                        MarketRegime.SIDEWAYS,
                        history,
                        returns,
                        n_trials=50,
                        persist=True,
                    )

                    mock_save_weights.assert_called_once()

    def test_optimize_weights_for_regime_invalid_inputs(self) -> None:
        """Test raises ConfigError with invalid inputs."""
        history = [{"sentiment": Decimal("0.5")} for _ in range(5)]
        returns = [Decimal("0.05") for _ in range(5)]

        with pytest.raises(ConfigError):
            optimize_weights_for_regime(MarketRegime.SIDEWAYS, history, returns)


class TestOptimizeAllRegimes:
    """Test optimize_all_regimes function."""

    @patch("iatb.selection.weight_optimizer.optimize_weights_for_regime")
    def test_optimize_all_regimes_success(self, mock_optimize) -> None:
        """Test successful optimization for all regimes."""
        mock_result = OptimizationResult(
            regime=MarketRegime.SIDEWAYS,
            best_weights=RegimeWeights(
                sentiment=Decimal("0.25"),
                strength=Decimal("0.25"),
                volume_profile=Decimal("0.25"),
                drl=Decimal("0.25"),
            ),
            best_ic=Decimal("0.05"),
            trials=50,
            improved=True,
        )
        mock_optimize.return_value = mock_result

        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [{"sentiment": Decimal("0.5")} for _ in range(10)],
            MarketRegime.BULL: [{"sentiment": Decimal("0.6")} for _ in range(10)],
        }
        forward_returns_by_regime = {
            MarketRegime.SIDEWAYS: [Decimal("0.05") for _ in range(10)],
            MarketRegime.BULL: [Decimal("0.07") for _ in range(10)],
        }

        result = optimize_all_regimes(
            signal_history_by_regime, forward_returns_by_regime
        )

        assert len(result) == 2
        assert MarketRegime.SIDEWAYS in result
        assert MarketRegime.BULL in result

    @patch("iatb.selection.weight_optimizer.optimize_weights_for_regime")
    def test_optimize_all_regimes_missing_returns(self, mock_optimize, caplog) -> None:
        """Test skips regime when returns missing."""
        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [{"sentiment": Decimal("0.5")} for _ in range(10)],
        }
        forward_returns_by_regime = {}  # Empty

        result = optimize_all_regimes(
            signal_history_by_regime, forward_returns_by_regime
        )

        assert len(result) == 0
        assert "No forward returns for regime SIDEWAYS" in caplog.text

    @patch("iatb.selection.weight_optimizer.optimize_weights_for_regime")
    def test_optimize_all_regimes_optimization_failure(
        self, mock_optimize, caplog
    ) -> None:
        """Test handles optimization failures gracefully."""
        mock_optimize.side_effect = Exception("Optimization failed")

        signal_history_by_regime = {
            MarketRegime.SIDEWAYS: [{"sentiment": Decimal("0.5")} for _ in range(10)],
        }
        forward_returns_by_regime = {
            MarketRegime.SIDEWAYS: [Decimal("0.05") for _ in range(10)],
        }

        result = optimize_all_regimes(
            signal_history_by_regime, forward_returns_by_regime
        )

        assert len(result) == 0
        assert "Failed to optimize weights for regime SIDEWAYS" in caplog.text
