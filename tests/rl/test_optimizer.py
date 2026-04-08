import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.rl.optimizer import RLParameterOptimizer

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeSampler:
    def __init__(self, seed: int) -> None:
        self.seed = seed


class _FakeTrial:
    def __init__(self) -> None:
        self.params: dict[str, int] = {}

    def suggest_int(self, name: str, low: int, high: int) -> int:
        value = high
        _ = low
        self.params[name] = value
        return value


class _FakeStudy:
    def __init__(self) -> None:
        self.best_value = float("-inf")
        self.best_params: dict[str, int] = {}

    def optimize(self, objective: object, n_trials: int) -> None:
        if not callable(objective):
            raise AssertionError("objective must be callable")
        for _ in range(n_trials):
            trial = _FakeTrial()
            value = objective(trial)
            if value > self.best_value:
                self.best_value = value
                self.best_params = dict(trial.params)


def test_optimizer_runs_optuna_study_with_deterministic_sampler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_optuna = SimpleNamespace(
        samplers=SimpleNamespace(TPESampler=_FakeSampler),
        create_study=lambda direction, sampler: _FakeStudy(),
    )
    monkeypatch.setattr("iatb.rl.optimizer.importlib.import_module", lambda _: fake_optuna)

    def objective(params: dict[str, int]) -> Decimal:
        return Decimal(params["fast"]) + Decimal(params["slow"])

    optimizer = RLParameterOptimizer(objective=objective, n_trials=3, seed=99)
    result = optimizer.optimize({"fast": (3, 8), "slow": (10, 20)})
    assert result.best_params == {"fast": 8, "slow": 20}
    assert result.best_value == Decimal("28.0")
    assert result.sampler_name == "_FakeSampler"


def test_optimizer_validates_search_space_and_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    optimizer = RLParameterOptimizer(objective=lambda params: Decimal("1"), n_trials=1)
    with pytest.raises(ConfigError, match="search_space cannot be empty"):
        optimizer.optimize({})
    monkeypatch.setattr(
        "iatb.rl.optimizer.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="optuna dependency"):
        optimizer.optimize({"window": (1, 2)})


def test_optimizer_validates_trials_bounds_and_optuna_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ConfigError, match="n_trials must be positive"):
        RLParameterOptimizer(objective=lambda params: Decimal("1"), n_trials=0)
    optimizer = RLParameterOptimizer(objective=lambda params: Decimal("1"), n_trials=1)
    with pytest.raises(ConfigError, match="low > high"):
        optimizer.optimize({"window": (5, 1)})
    bad_sampler_module = SimpleNamespace(
        samplers=SimpleNamespace(), create_study=lambda **kwargs: _FakeStudy()
    )
    monkeypatch.setattr("iatb.rl.optimizer.importlib.import_module", lambda _: bad_sampler_module)
    with pytest.raises(ConfigError, match="TPESampler is unavailable"):
        optimizer.optimize({"window": (1, 2)})


def test_optimizer_rejects_bad_trial_and_best_params(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadTrial:
        def suggest_int(self, name: str, low: int, high: int) -> str:
            _ = name
            _ = low
            _ = high
            return "bad"

    class _BadTrialStudy:
        best_value = 1.0
        best_params = {"window": 5}

        def optimize(self, objective: object, n_trials: int) -> None:
            _ = n_trials
            if not callable(objective):
                raise AssertionError("objective must be callable")
            objective(_BadTrial())

    class _BadParamsStudy:
        best_value = 1.0
        best_params = {"window": "x"}

        def optimize(self, objective: object, n_trials: int) -> None:
            _ = n_trials
            if not callable(objective):
                raise AssertionError("objective must be callable")
            objective(_FakeTrial())

    optimizer = RLParameterOptimizer(objective=lambda params: Decimal("1"), n_trials=1)
    bad_trial_module = SimpleNamespace(
        samplers=SimpleNamespace(TPESampler=_FakeSampler),
        create_study=lambda direction, sampler: _BadTrialStudy(),
    )
    monkeypatch.setattr("iatb.rl.optimizer.importlib.import_module", lambda _: bad_trial_module)
    with pytest.raises(ConfigError, match="must be int"):
        optimizer.optimize({"window": (1, 2)})
    bad_params_module = SimpleNamespace(
        samplers=SimpleNamespace(TPESampler=_FakeSampler),
        create_study=lambda direction, sampler: _BadParamsStudy(),
    )
    monkeypatch.setattr("iatb.rl.optimizer.importlib.import_module", lambda _: bad_params_module)
    with pytest.raises(ConfigError, match="best_params missing int value"):
        optimizer.optimize({"window": (1, 2)})
