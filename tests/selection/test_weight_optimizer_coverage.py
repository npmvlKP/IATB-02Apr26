"""Tests for selection/weight_optimizer.py — weight optimization, regime mapping."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import RegimeWeights
from iatb.selection.weight_optimizer import (
    OptimizationResult,
    _compute_composites,
    _create_objective,
    _extract_best_weights,
    _load_optuna,
    _suggest_weights,
    _validate_inputs,
    _weights_to_dict,
    optimize_all_regimes,
    optimize_weights_for_regime,
)

# Skip tests requiring optuna if not available (system Python only)
_optuna_available = True
try:
    import optuna  # noqa: F401
except (ImportError, ModuleNotFoundError):
    _optuna_available = False


def _valid_weights() -> RegimeWeights:
    return RegimeWeights(
        sentiment=Decimal("0.25"),
        strength=Decimal("0.25"),
        volume_profile=Decimal("0.25"),
        drl=Decimal("0.25"),
    )


def _signal_history(n: int = 12) -> list[dict[str, Decimal]]:
    return [
        {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.5"),
            "volume_profile": Decimal("0.5"),
            "drl": Decimal("0.5"),
        }
        for _ in range(n)
    ]


def _forward_returns(n: int = 12) -> list[Decimal]:
    return [Decimal("0.01") for _ in range(n)]


class TestValidateInputs:
    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_inputs(_signal_history(10), _forward_returns(5), 50)

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ConfigError, match="at least 10"):
            _validate_inputs(_signal_history(5), _forward_returns(5), 50)

    def test_zero_trials_raises(self) -> None:
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            _validate_inputs(_signal_history(10), _forward_returns(10), 0)

    def test_valid_inputs_pass(self) -> None:
        _validate_inputs(_signal_history(10), _forward_returns(10), 50)


class TestComputeComposites:
    def test_uniform_weights_and_signals(self) -> None:
        weights = _valid_weights()
        history = _signal_history(1)
        result = _compute_composites(history, weights)
        assert len(result) == 1
        assert result[0] == Decimal("0.5")

    def test_missing_keys_default_zero(self) -> None:
        weights = _valid_weights()
        history = [{"sentiment": Decimal("1")} for _ in range(2)]
        result = _compute_composites(history, weights)
        assert all(Decimal("0") <= r <= Decimal("1") for r in result)

    def test_empty_history(self) -> None:
        weights = _valid_weights()
        assert _compute_composites([], weights) == []


class TestSuggestWeights:
    def test_valid_trial_returns_weights(self) -> None:
        trial = MagicMock()
        trial.suggest_int.side_effect = lambda name, _low, _high: {  # noqa: ARG005
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }[name]
        result = _suggest_weights(trial)
        assert isinstance(result, RegimeWeights)
        total = result.sentiment + result.strength + result.volume_profile + result.drl
        assert total == Decimal("1")

    def test_invalid_trial_raises(self) -> None:
        trial = MagicMock(spec=[])
        with pytest.raises(ConfigError, match="suggest_int"):
            _suggest_weights(trial)


class TestLoadOptuna:
    def test_missing_optuna_raises(self) -> None:
        with patch(
            "importlib.import_module", side_effect=ModuleNotFoundError
        ), pytest.raises(ConfigError, match="optuna dependency"):
            _load_optuna()


class TestCreateObjective:
    def test_objective_returns_float(self) -> None:
        history = _signal_history(3)
        returns = [Decimal("0.01")] * 3
        objective = _create_objective(history, returns)
        trial = MagicMock()
        trial.suggest_int.side_effect = lambda _n, _lo, _hi: 25  # noqa: ARG005
        result = objective(trial)
        assert isinstance(result, float)


class TestWeightsToDict:
    def test_converts_to_string_dict(self) -> None:
        w = _valid_weights()
        d = _weights_to_dict(w)
        assert all(isinstance(v, str) for v in d.values())
        assert set(d.keys()) == {"sentiment", "strength", "volume_profile", "drl"}


class TestExtractBestWeights:
    def test_valid_study(self) -> None:
        study = MagicMock()
        study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        result = _extract_best_weights(study)
        assert isinstance(result, RegimeWeights)
        total = result.sentiment + result.strength + result.volume_profile + result.drl
        assert total == Decimal("1")

    def test_missing_best_params_raises(self) -> None:
        study = MagicMock(spec=[])
        with pytest.raises(ConfigError, match="best_params"):
            _extract_best_weights(study)


@pytest.mark.skipif(
    not _optuna_available, reason="optuna not available (system Python only)"
)
class TestOptimizeWeightsForRegime:
    def test_full_optimization_flow(self) -> None:
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 30,
            "strength": 20,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.05
        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler.return_value = MagicMock()
        mock_optuna.create_study.return_value = mock_study

        with patch(
            "iatb.selection.weight_optimizer._load_optuna", return_value=mock_optuna
        ), patch("iatb.selection.weight_optimizer._save_weights_to_config"):
            result = optimize_weights_for_regime(
                MarketRegime.BULL,
                _signal_history(15),
                _forward_returns(15),
                n_trials=5,
                persist=False,
            )

        assert isinstance(result, OptimizationResult)
        assert result.regime == MarketRegime.BULL
        assert result.trials == 5

    def test_persist_false_skips_save(self) -> None:
        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.04
        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler.return_value = MagicMock()
        mock_optuna.create_study.return_value = mock_study

        with patch(
            "iatb.selection.weight_optimizer._load_optuna", return_value=mock_optuna
        ), patch(
            "iatb.selection.weight_optimizer._save_weights_to_config"
        ) as mock_save:
            optimize_weights_for_regime(
                MarketRegime.SIDEWAYS,
                _signal_history(15),
                _forward_returns(15),
                n_trials=5,
                persist=False,
            )
            mock_save.assert_not_called()


@pytest.mark.skipif(
    not _optuna_available, reason="optuna not available (system Python only)"
)
class TestOptimizeAllRegimes:
    def test_multiple_regimes(self) -> None:
        history = {
            MarketRegime.BULL: _signal_history(15),
            MarketRegime.BEAR: _signal_history(15),
        }
        returns = {
            MarketRegime.BULL: _forward_returns(15),
            MarketRegime.BEAR: _forward_returns(15),
        }

        mock_study = MagicMock()
        mock_study.best_params = {
            "sentiment": 25,
            "strength": 25,
            "volume_profile": 25,
            "drl": 25,
        }
        mock_study.best_value = 0.04
        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler.return_value = MagicMock()
        mock_optuna.create_study.return_value = mock_study

        with patch(
            "iatb.selection.weight_optimizer._load_optuna", return_value=mock_optuna
        ), patch("iatb.selection.weight_optimizer._save_weights_to_config"):
            results = optimize_all_regimes(history, returns, n_trials=5)

        assert MarketRegime.BULL in results
        assert MarketRegime.BEAR in results

    def test_empty_returns_skipped(self) -> None:
        history = {MarketRegime.BULL: _signal_history(15)}
        returns: dict[MarketRegime, list[Decimal]] = {MarketRegime.BULL: []}

        results = optimize_all_regimes(history, returns, n_trials=5)
        assert MarketRegime.BULL not in results
