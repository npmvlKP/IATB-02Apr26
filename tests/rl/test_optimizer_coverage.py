"""
Comprehensive coverage tests for optimizer.py.

Tests weight optimization, Optuna integration, and parameter search.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.optimizer import (
    OptimizationResult,
    RLParameterOptimizer,
    _best_params,
    _best_value,
    _build_sampler,
    _create_study,
    _load_optuna_module,
    _suggest_params,
    _validate_search_space,
)


class TestValidateSearchSpace:
    """Test search space validation."""

    def test_valid_search_space(self):
        """Test valid search space."""
        search_space = {"learning_rate": (1, 10), "gamma": (90, 100)}
        _validate_search_space(search_space)  # Should not raise

    def test_empty_search_space_raises_error(self):
        """Test that empty search space raises ConfigError."""
        with pytest.raises(ConfigError, match="search_space cannot be empty"):
            _validate_search_space({})

    def test_invalid_bounds_raises_error(self):
        """Test that invalid bounds raise ConfigError."""
        with pytest.raises(ConfigError, match="invalid bounds"):
            _validate_search_space({"param": (10, 5)})  # low > high


class TestLoadOptunaModule:
    """Test Optuna module loading."""

    def test_load_optuna_success(self):
        """Test successful Optuna loading."""
        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            result = _load_optuna_module()
            assert result is not None
            mock_import.assert_called_once_with("optuna")

    def test_load_optuna_failure_raises_error(self):
        """Test that missing Optuna raises ConfigError."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("optuna not found")

            with pytest.raises(ConfigError, match="optuna dependency is required"):
                _load_optuna_module()


class TestBuildSampler:
    """Test sampler building."""

    def test_build_sampler_success(self):
        """Test successful sampler building."""
        mock_optuna = MagicMock()
        mock_sampler_cls = MagicMock(return_value=MagicMock())
        mock_optuna.samplers.TPESampler = mock_sampler_cls

        sampler = _build_sampler(mock_optuna, seed=42)

        assert sampler is not None
        mock_sampler_cls.assert_called_once_with(seed=42)

    def test_build_sampler_no_tpe_raises_error(self):
        """Test that missing TPESampler raises ConfigError."""
        mock_optuna = MagicMock()
        mock_optuna.samplers.TPESampler = None

        with pytest.raises(
            ConfigError, match="optuna.samplers.TPESampler is unavailable"
        ):
            _build_sampler(mock_optuna, seed=42)


class TestCreateStudy:
    """Test study creation."""

    def test_create_study_success(self):
        """Test successful study creation."""
        mock_optuna = MagicMock()
        mock_study = MagicMock()
        mock_create_study = MagicMock(return_value=mock_study)
        mock_optuna.create_study = mock_create_study

        mock_sampler = MagicMock()

        study = _create_study(mock_optuna, mock_sampler)

        assert study == mock_study
        mock_create_study.assert_called_once_with(
            direction="maximize", sampler=mock_sampler
        )

    def test_create_study_no_method_raises_error(self):
        """Test that missing create_study raises ConfigError."""
        mock_optuna = MagicMock()
        mock_optuna.create_study = None

        with pytest.raises(ConfigError, match="optuna.create_study is unavailable"):
            _create_study(mock_optuna, MagicMock())


class TestSuggestParams:
    """Test parameter suggestion."""

    def test_suggest_params_success(self):
        """Test successful parameter suggestion."""
        mock_trial = MagicMock()
        mock_trial.suggest_int = MagicMock(return_value=5)

        search_space = {"param1": (1, 10), "param2": (20, 30)}

        params = _suggest_params(mock_trial, search_space)

        assert params["param1"] == 5
        assert params["param2"] == 5
        assert len(params) == 2

    def test_suggest_params_no_method_raises_error(self):
        """Test that missing suggest_int raises ConfigError."""
        mock_trial = MagicMock()
        mock_trial.suggest_int = None

        with pytest.raises(
            ConfigError, match="optuna trial does not provide suggest_int"
        ):
            _suggest_params(mock_trial, {"param": (1, 10)})

    def test_suggest_params_invalid_type_raises_error(self):
        """Test that non-int return raises ConfigError."""
        mock_trial = MagicMock()
        mock_trial.suggest_int = MagicMock(return_value="not an int")

        with pytest.raises(ConfigError, match=r"trial parameter '.*' must be int"):
            _suggest_params(mock_trial, {"param": (1, 10)})


class TestBestParams:
    """Test best parameter extraction."""

    def test_best_params_success(self):
        """Test successful best params extraction."""
        mock_study = MagicMock()
        mock_study.best_params = {"param1": 5, "param2": 10}

        names = ["param1", "param2"]
        params = _best_params(mock_study, names)

        assert params["param1"] == 5
        assert params["param2"] == 10

    def test_best_params_no_dict_raises_error(self):
        """Test that missing best_params raises ConfigError."""
        mock_study = MagicMock()
        mock_study.best_params = None

        with pytest.raises(
            ConfigError, match="optuna study does not expose dict best_params"
        ):
            _best_params(mock_study, ["param1"])

    def test_best_params_missing_value_raises_error(self):
        """Test that missing param value raises ConfigError."""
        # Use a custom mock object that mimics dict behavior
        class MockBestParams(dict):
            def get(self, key, default=None):
                # Return None for param2 (which is being looked up)
                if key == "param2":
                    return None
                return super().get(key, default)
        
        mock_study = MagicMock()
        mock_study.best_params = MockBestParams({"param1": 5})

        with pytest.raises(ConfigError, match="best_params missing int value"):
            _best_params(mock_study, ["param2"])

    def test_best_params_invalid_type_raises_error(self):
        """Test that non-int value raises ConfigError."""
        mock_study = MagicMock()
        mock_study.best_params = {"param1": "not an int"}

        with pytest.raises(ConfigError, match="best_params missing int value"):
            _best_params(mock_study, ["param1"])


class TestBestValue:
    """Test best value extraction."""

    def test_best_value_float(self):
        """Test best value extraction with float."""
        mock_study = MagicMock()
        mock_study.best_value = 0.5

        value = _best_value(mock_study)

        assert value == 0.5

    def test_best_value_int(self):
        """Test best value extraction with int."""
        mock_study = MagicMock()
        mock_study.best_value = 5

        value = _best_value(mock_study)

        assert value == 5.0

    def test_best_value_no_value_raises_error(self):
        """Test that missing best_value raises ConfigError."""
        mock_study = MagicMock()
        mock_study.best_value = None

        with pytest.raises(
            ConfigError, match="optuna study does not expose numeric best_value"
        ):
            _best_value(mock_study)

    def test_best_value_invalid_type_raises_error(self):
        """Test that non-numeric value raises ConfigError."""
        mock_study = MagicMock()
        mock_study.best_value = "not a number"

        with pytest.raises(
            ConfigError, match="optuna study does not expose numeric best_value"
        ):
            _best_value(mock_study)


class TestRLParameterOptimizer:
    """Test RL parameter optimizer."""

    def _make_objective(self, params):
        """Helper function to create objective for testing."""
        return Decimal("0.5")

    def test_optimizer_initialization(self):
        """Test optimizer initialization."""
        optimizer = RLParameterOptimizer(self._make_objective)

        assert optimizer._objective == self._make_objective
        assert optimizer._n_trials == 20
        assert optimizer._seed == 42

    def test_invalid_n_trials_raises_error(self):
        """Test that invalid n_trials raises ConfigError."""
        with pytest.raises(ConfigError, match="n_trials must be positive"):
            RLParameterOptimizer(self._make_objective, n_trials=0)

    def test_optimize_success(self):
        """Test successful optimization."""
        optimizer = RLParameterOptimizer(self._make_objective, n_trials=10)

        search_space = {"learning_rate": (1, 10)}

        # Mock Optuna
        mock_study = MagicMock()
        mock_study.best_params = {"learning_rate": 5}
        mock_study.best_value = 0.5

        with patch("iatb.rl.optimizer._load_optuna_module") as mock_load:
            with patch("iatb.rl.optimizer._build_sampler") as mock_sampler:
                with patch("iatb.rl.optimizer._create_study") as mock_create:
                    mock_optuna = MagicMock()
                    mock_load.return_value = mock_optuna
                    mock_sampler.return_value = MagicMock()
                    mock_create.return_value = mock_study

                    result = optimizer.optimize(search_space)

                    assert isinstance(result, OptimizationResult)
                    assert result.best_params["learning_rate"] == 5
                    assert result.best_value == Decimal("0.5")
                    assert result.trial_count == 10

    def _make_invalid_objective(self, params):
        """Helper function for invalid objective test."""
        return Decimal("0.5")

    def test_optimize_no_optimize_method_raises_error(self):
        """Test that missing optimize method raises ConfigError."""
        optimizer = RLParameterOptimizer(self._make_invalid_objective)

        search_space = {"learning_rate": (1, 10)}

        # Mock Optuna with broken study
        mock_study = MagicMock()
        mock_study.optimize = None

        with patch("iatb.rl.optimizer._load_optuna_module") as mock_load:
            with patch("iatb.rl.optimizer._build_sampler") as mock_sampler:
                with patch("iatb.rl.optimizer._create_study") as mock_create:
                    mock_optuna = MagicMock()
                    mock_load.return_value = mock_optuna
                    mock_sampler.return_value = MagicMock()
                    mock_create.return_value = mock_study

                    with pytest.raises(
                        ConfigError, match="optuna study does not provide optimize"
                    ):
                        optimizer.optimize(search_space)

    def _mock_optimize_call(self, fn, n_trials):
        """Helper to mock optimize calling the function."""
        return fn(None)

    def test_objective_wrapper_calls_objective(self):
        """Test that objective wrapper calls the objective function."""
        objective = MagicMock(return_value=Decimal("0.5"))
        optimizer = RLParameterOptimizer(objective)

        search_space = {"learning_rate": (1, 10)}

        # Mock Optuna
        mock_study = MagicMock()
        mock_study.best_params = {"learning_rate": 5}
        mock_study.best_value = 0.5

        mock_study.optimize = MagicMock(side_effect=self._mock_optimize_call)

        with patch("iatb.rl.optimizer._load_optuna_module") as mock_load:
            with patch("iatb.rl.optimizer._build_sampler") as mock_sampler:
                with patch("iatb.rl.optimizer._create_study") as mock_create:
                    with patch("iatb.rl.optimizer._suggest_params") as mock_suggest:
                        mock_optuna = MagicMock()
                        mock_load.return_value = mock_optuna
                        mock_sampler.return_value = MagicMock()
                        mock_create.return_value = mock_study
                        mock_suggest.return_value = {"learning_rate": 5}

                        optimizer.optimize(search_space)

                        # Objective should have been called
                        objective.assert_called_once_with({"learning_rate": 5})


class TestOptimizationResult:
    """Test optimization result dataclass."""

    def test_result_creation(self):
        """Test creating an optimization result."""
        result = OptimizationResult(
            best_params={"learning_rate": 5},
            best_value=Decimal("0.5"),
            trial_count=10,
            sampler_name="TPESampler",
        )

        assert result.best_params["learning_rate"] == 5
        assert result.best_value == Decimal("0.5")
        assert result.trial_count == 10
        assert result.sampler_name == "TPESampler"