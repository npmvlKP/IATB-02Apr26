"""Tests for rl/optimizer.py — hyperparameter optimization."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.optimizer import (
    RLParameterOptimizer,
    _best_params,
    _best_value,
    _load_optuna_module,
    _suggest_params,
    _validate_search_space,
)


class TestValidateSearchSpace:
    def test_empty_space_raises(self) -> None:
        with pytest.raises(ConfigError, match="search_space cannot be empty"):
            _validate_search_space({})

    def test_low_gt_high_raises(self) -> None:
        with pytest.raises(ConfigError, match="invalid bounds"):
            _validate_search_space({"lr": (100, 1)})

    def test_valid_space(self) -> None:
        _validate_search_space({"lr": (1, 100), "batch": (8, 64)})


class TestLoadOptunaModule:
    def test_missing_optuna_raises(self) -> None:
        with patch(
            "importlib.import_module", side_effect=ModuleNotFoundError
        ), pytest.raises(ConfigError, match="optuna dependency"):
            _load_optuna_module()


class TestSuggestParams:
    def test_valid_trial(self) -> None:
        trial = MagicMock()
        trial.suggest_int.side_effect = lambda name, _low, _high: {
            "lr": 10,
            "batch": 32,
        }[name]
        space = {"lr": (1, 100), "batch": (8, 128)}
        result = _suggest_params(trial, space)
        assert result == {"lr": 10, "batch": 32}

    def test_non_int_value_raises(self) -> None:
        trial = MagicMock()
        trial.suggest_int.return_value = 10.5
        with pytest.raises(ConfigError, match="must be int"):
            _suggest_params(trial, {"lr": (1, 100)})

    def test_missing_suggest_int_raises(self) -> None:
        trial = MagicMock(spec=[])
        with pytest.raises(ConfigError, match="suggest_int"):
            _suggest_params(trial, {"lr": (1, 100)})


class TestBestParams:
    def test_valid_study(self) -> None:
        study = MagicMock()
        study.best_params = {"lr": 10, "batch": 32}
        result = _best_params(study, ["lr", "batch"])
        assert result == {"lr": 10, "batch": 32}

    def test_non_dict_best_params_raises(self) -> None:
        study = MagicMock(spec=[])
        with pytest.raises(ConfigError, match="dict best_params"):
            _best_params(study, ["lr"])

    def test_missing_key_raises(self) -> None:
        study = MagicMock()
        study.best_params = {"lr": 10}
        with pytest.raises(ConfigError, match="missing int value"):
            _best_params(study, ["lr", "batch"])


class TestBestValue:
    def test_float_value(self) -> None:
        study = MagicMock()
        study.best_value = 0.85
        assert _best_value(study) == 0.85

    def test_int_value(self) -> None:
        study = MagicMock()
        study.best_value = 1
        assert _best_value(study) == 1.0

    def test_non_numeric_raises(self) -> None:
        study = MagicMock()
        study.best_value = "bad"
        with pytest.raises(ConfigError, match="numeric best_value"):
            _best_value(study)


def _objective(params: dict) -> Decimal:
    return Decimal(str(sum(params.values())))


class TestRLParameterOptimizer:
    def test_negative_trials_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            RLParameterOptimizer(_objective, n_trials=-1)

    def test_zero_trials_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            RLParameterOptimizer(_objective, n_trials=0)

    def test_successful_optimization(self) -> None:
        mock_study = MagicMock()
        mock_study.best_params = {"lr": 50, "batch": 64}
        mock_study.best_value = 0.9
        mock_study.optimize = MagicMock()

        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler.return_value = MagicMock()
        mock_optuna.create_study.return_value = mock_study

        opt = RLParameterOptimizer(_objective, n_trials=5)

        with patch("iatb.rl.optimizer._load_optuna_module", return_value=mock_optuna):
            result = opt.optimize({"lr": (1, 100), "batch": (8, 128)})

        assert result.best_params == {"lr": 50, "batch": 64}
        assert result.best_value == Decimal("0.9")
        assert result.trial_count == 5
