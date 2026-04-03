"""
Optuna-backed optimizer for RL strategy parameter search.
"""

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

ObjectiveFn = Callable[[dict[str, int]], Decimal]


@dataclass(frozen=True)
class OptimizationResult:
    best_params: dict[str, int]
    best_value: Decimal
    trial_count: int
    sampler_name: str


class RLParameterOptimizer:
    """Deterministic Optuna optimizer using TPESampler(seed=...)."""

    def __init__(self, objective: ObjectiveFn, n_trials: int = 20, seed: int = 42) -> None:
        if n_trials <= 0:
            msg = "n_trials must be positive"
            raise ConfigError(msg)
        self._objective = objective
        self._n_trials = n_trials
        self._seed = seed

    def optimize(self, search_space: dict[str, tuple[int, int]]) -> OptimizationResult:
        _validate_search_space(search_space)
        optuna = _load_optuna_module()
        sampler = _build_sampler(optuna, self._seed)
        study = _create_study(optuna, sampler)

        def objective_wrapper(trial: object) -> float:
            params = _suggest_params(trial, search_space)
            score = self._objective(params)
            # API boundary: Optuna objective callbacks operate with float values.
            return float(score)

        optimize_method = getattr(study, "optimize", None)
        if not callable(optimize_method):
            msg = "optuna study does not provide optimize()"
            raise ConfigError(msg)
        optimize_method(objective_wrapper, n_trials=self._n_trials)
        best_params = _best_params(study, search_space.keys())
        best_value = Decimal(str(_best_value(study)))
        return OptimizationResult(
            best_params=best_params,
            best_value=best_value,
            trial_count=self._n_trials,
            sampler_name=type(sampler).__name__,
        )


def _validate_search_space(search_space: dict[str, tuple[int, int]]) -> None:
    if not search_space:
        msg = "search_space cannot be empty"
        raise ConfigError(msg)
    for name, (low, high) in search_space.items():
        if low > high:
            msg = f"invalid bounds for '{name}': low > high"
            raise ConfigError(msg)


def _load_optuna_module() -> object:
    try:
        return importlib.import_module("optuna")
    except ModuleNotFoundError as exc:
        msg = "optuna dependency is required for RLParameterOptimizer"
        raise ConfigError(msg) from exc


def _build_sampler(optuna: object, seed: int) -> object:
    samplers = getattr(optuna, "samplers", None)
    sampler_cls = getattr(samplers, "TPESampler", None)
    if not callable(sampler_cls):
        msg = "optuna.samplers.TPESampler is unavailable"
        raise ConfigError(msg)
    return sampler_cls(seed=seed)


def _create_study(optuna: object, sampler: object) -> object:
    create_study = getattr(optuna, "create_study", None)
    if not callable(create_study):
        msg = "optuna.create_study is unavailable"
        raise ConfigError(msg)
    return create_study(direction="maximize", sampler=sampler)


def _suggest_params(trial: object, search_space: dict[str, tuple[int, int]]) -> dict[str, int]:
    suggest_int = getattr(trial, "suggest_int", None)
    if not callable(suggest_int):
        msg = "optuna trial does not provide suggest_int()"
        raise ConfigError(msg)
    params: dict[str, int] = {}
    for name, (low, high) in search_space.items():
        value = suggest_int(name, low, high)
        if not isinstance(value, int):
            msg = f"trial parameter '{name}' must be int"
            raise ConfigError(msg)
        params[name] = value
    return params


def _best_params(study: object, names: Iterable[str]) -> dict[str, int]:
    params = getattr(study, "best_params", None)
    if not isinstance(params, dict):
        msg = "optuna study does not expose dict best_params"
        raise ConfigError(msg)
    result: dict[str, int] = {}
    for name in names:
        value = params.get(name)
        if not isinstance(value, int):
            msg = f"best_params missing int value for '{name}'"
            raise ConfigError(msg)
        result[name] = value
    return result


def _best_value(study: object) -> float:
    value = getattr(study, "best_value", None)
    if not isinstance(value, float | int):
        msg = "optuna study does not expose numeric best_value"
        raise ConfigError(msg)
    return float(value)
