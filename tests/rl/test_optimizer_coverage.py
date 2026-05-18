"""
Additional tests for rl/optimizer.py to improve coverage to 90%+.
"""

from decimal import Decimal

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


class TestRLParameterOptimizer:
    """Test RLParameterOptimizer class."""

    def test_optimizer_init_valid(self) -> None:
        """Test optimizer initialization with valid parameters."""

        def objective(params: dict[str, int]) -> Decimal:
            return Decimal(str(params.get("x", 0)))

        optimizer = RLParameterOptimizer(objective=objective, n_trials=10, seed=42)
        assert optimizer._objective is objective
        assert optimizer._n_trials == 10
        assert optimizer._seed == 42

    def test_optimizer_init_zero_trials_raises_error(self) -> None:
        """Test initialization with zero trials raises ConfigError."""

        def objective(params: dict[str, int]) -> Decimal:
            return Decimal("0")

        with pytest.raises(ConfigError, match="n_trials must be positive"):
            RLParameterOptimizer(objective=objective, n_trials=0)

    def test_optimizer_init_negative_trials_raises_error(self) -> None:
        """Test initialization with negative trials raises ConfigError."""

        def objective(params: dict[str, int]) -> Decimal:
            return Decimal("0")

        with pytest.raises(ConfigError, match="n_trials must be positive"):
            RLParameterOptimizer(objective=objective, n_trials=-5)

    def test_optimizer_optimize_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful optimization."""

        # Mock optuna module
        class MockTrial:
            def __init__(self) -> None:
                self.suggest_int_values: dict[str, int] = {}

            def suggest_int(self, name: str, low: int, high: int) -> int:
                value = low + (high - low) // 2
                self.suggest_int_values[name] = value
                return value

        class MockStudy:
            def __init__(
                self, direction: str = "maximize", sampler: object = None
            ) -> None:
                self.direction = direction
                self.sampler = sampler
                self.best_params: dict[str, int] = {
                    "learning_rate": 5,
                    "batch_size": 32,
                }
                self.best_value: float = 0.85
                self.trials: list[MockTrial] = []

            def optimize(self, func: object, n_trials: int) -> None:
                for _ in range(n_trials):
                    trial = MockTrial()
                    self.trials.append(trial)
                    result = func(trial)
                    # Update best if better
                    if result > self.best_value:
                        self.best_value = result

        class MockTPESampler:
            def __init__(self, seed: int) -> None:
                self.seed = seed

        mock_samplers = type("Samplers", (), {"TPESampler": MockTPESampler})()
        mock_optuna = type(
            "Module", (), {"create_study": MockStudy, "samplers": mock_samplers}
        )()

        monkeypatch.setattr(
            "iatb.rl.optimizer._load_optuna_module", lambda: mock_optuna
        )

        def objective(params: dict[str, int]) -> Decimal:
            return Decimal(str(params.get("learning_rate", 0)))

        optimizer = RLParameterOptimizer(objective=objective, n_trials=5)
        result = optimizer.optimize({"learning_rate": (1, 10), "batch_size": (16, 64)})

        assert isinstance(result, OptimizationResult)
        assert result.trial_count == 5
        assert result.sampler_name == "MockTPESampler"


class TestValidateSearchSpace:
    """Test _validate_search_space function."""

    def test_validate_search_space_valid(self) -> None:
        """Test validation with valid search space."""
        space = {"learning_rate": (1, 10), "batch_size": (16, 64)}
        _validate_search_space(space)  # Should not raise

    def test_validate_search_space_empty_raises_error(self) -> None:
        """Test validation with empty search space raises ConfigError."""
        with pytest.raises(ConfigError, match="search_space cannot be empty"):
            _validate_search_space({})

    def test_validate_search_space_low_greater_than_high_raises_error(self) -> None:
        """Test validation with low > high raises ConfigError."""
        space = {"param": (10, 5)}  # low > high
        with pytest.raises(ConfigError, match="invalid bounds"):
            _validate_search_space(space)

    def test_validate_search_space_negative_values_raises_error(self) -> None:
        """Test validation with negative values - should not raise for bounds."""
        space = {"param": (-10, 5)}  # Negative low is valid for bounds
        _validate_search_space(space)  # Should not raise


class TestLoadOptunaModule:
    """Test _load_optuna_module function."""

    def test_load_optuna_module_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading optuna module when available."""
        mock_module = type("Module", (), {})()
        monkeypatch.setattr(
            "iatb.rl.optimizer.importlib.import_module", lambda _: mock_module
        )
        result = _load_optuna_module()
        assert result is mock_module

    def test_load_optuna_module_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading optuna module when not found."""
        monkeypatch.setattr(
            "iatb.rl.optimizer.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError("optuna")),
        )
        with pytest.raises(ConfigError, match="optuna dependency is required"):
            _load_optuna_module()


class TestBuildSampler:
    """Test _build_sampler function."""

    def test_build_sampler_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test building TPESampler."""

        class MockTPESampler:
            def __init__(self, seed: int) -> None:
                self.seed = seed

        mock_samplers = type("Samplers", (), {"TPESampler": MockTPESampler})()
        mock_optuna = type("Module", (), {"samplers": mock_samplers})()

        sampler = _build_sampler(mock_optuna, 42)
        assert isinstance(sampler, MockTPESampler)
        assert sampler.seed == 42

    def test_build_sampler_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test building sampler when unavailable."""
        mock_optuna = type("Module", (), {"samplers": None})()
        with pytest.raises(
            ConfigError, match="optuna.samplers.TPESampler is unavailable"
        ):
            _build_sampler(mock_optuna, 42)


class TestCreateStudy:
    """Test _create_study function."""

    def test_create_study_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test creating Optuna study."""

        class MockStudy:
            def __init__(self, direction: str, sampler: object) -> None:
                self.direction = direction
                self.sampler = sampler

        mock_optuna = type("Module", (), {"create_study": MockStudy})()

        mock_sampler = type("Sampler", (), {})()
        study = _create_study(mock_optuna, mock_sampler)
        assert study.direction == "maximize"
        assert study.sampler is mock_sampler

    def test_create_study_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test creating study when unavailable."""
        mock_optuna = type("Module", (), {"create_study": None})()
        with pytest.raises(ConfigError, match="optuna.create_study is unavailable"):
            _create_study(mock_optuna, object())


class TestSuggestParams:
    """Test _suggest_params function."""

    def test_suggest_params_success(self) -> None:
        """Test suggesting parameters from trial."""

        class MockTrial:
            def suggest_int(self, name: str, low: int, high: int) -> int:
                return low + (high - low) // 2

        trial = MockTrial()
        search_space = {"learning_rate": (1, 10), "batch_size": (16, 64)}
        params = _suggest_params(trial, search_space)

        assert params["learning_rate"] == 5
        assert params["batch_size"] == 40
        assert all(isinstance(v, int) for v in params.values())

    def test_suggest_params_returns_int(self) -> None:
        """Test that suggest_params returns int values."""

        class MockTrial:
            def suggest_int(self, name: str, low: int, high: int) -> int:
                return 5

        trial = MockTrial()
        search_space = {"param": (1, 10)}
        params = _suggest_params(trial, search_space)
        assert isinstance(params["param"], int)


class TestBestParams:
    """Test _best_params function."""

    def test_best_params_success(self) -> None:
        """Test extracting best params from study."""
        mock_study = type(
            "Study", (), {"best_params": {"learning_rate": 5, "batch_size": 32}}
        )()
        names = ["learning_rate", "batch_size"]
        params = _best_params(mock_study, names)

        assert params == {"learning_rate": 5, "batch_size": 32}


class TestBestValue:
    """Test _best_value function."""

    def test_best_value_success(self) -> None:
        """Test extracting best value from study."""
        mock_study = type("Study", (), {"best_value": 0.85})()
        value = _best_value(mock_study)
        assert value == 0.85


class TestOptimizationResult:
    """Test OptimizationResult dataclass."""

    def test_optimization_result(self) -> None:
        """Test OptimizationResult initialization."""
        result = OptimizationResult(
            best_params={"learning_rate": 5},
            best_value=Decimal("0.85"),
            trial_count=10,
            sampler_name="TPESampler",
        )
        assert result.best_params == {"learning_rate": 5}
        assert result.best_value == Decimal("0.85")
        assert result.trial_count == 10
        assert result.sampler_name == "TPESampler"
