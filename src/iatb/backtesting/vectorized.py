"""
Vectorized backtesting wrappers for parameter sweeps.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from itertools import product

from iatb.core.exceptions import ConfigError

SweepEvaluator = Callable[[list[Decimal], dict[str, Decimal]], Decimal]


@dataclass(frozen=True)
class VectorizedSweepResult:
    best_params: dict[str, Decimal]
    best_score: Decimal
    scores: dict[str, Decimal]


class VectorizedBacktester:
    """Parameter sweep utility backed by vectorbt-ready evaluator hooks."""

    def __init__(self, evaluator: SweepEvaluator | None = None) -> None:
        self._evaluator = evaluator or _default_evaluator

    def run_sweep(
        self,
        close_prices: list[Decimal],
        parameter_grid: dict[str, list[Decimal]],
    ) -> VectorizedSweepResult:
        if len(close_prices) < 2:
            msg = "close_prices must contain at least two points"
            raise ConfigError(msg)
        if not parameter_grid:
            msg = "parameter_grid cannot be empty"
            raise ConfigError(msg)
        scores: dict[str, Decimal] = {}
        best_params: dict[str, Decimal] = {}
        best_score = Decimal("-999999")
        for params in _iter_parameter_sets(parameter_grid):
            score = self._evaluator(close_prices, params)
            key = _parameter_key(params)
            scores[key] = score
            if score > best_score:
                best_score = score
                best_params = params
        return VectorizedSweepResult(best_params=best_params, best_score=best_score, scores=scores)


def _default_evaluator(close_prices: list[Decimal], params: dict[str, Decimal]) -> Decimal:
    _load_vectorbt_module()
    start_price = close_prices[0]
    end_price = close_prices[-1]
    baseline = max(start_price, Decimal("1"))
    trend_return = (end_price - start_price) / baseline
    fast_window = params.get("fast_window", Decimal("10"))
    slow_window = params.get("slow_window", Decimal("30"))
    penalty = abs(slow_window - fast_window) / Decimal("1000")
    return trend_return - penalty


def _iter_parameter_sets(parameter_grid: dict[str, list[Decimal]]) -> list[dict[str, Decimal]]:
    keys = list(parameter_grid.keys())
    values = [parameter_grid[key] for key in keys]
    sets: list[dict[str, Decimal]] = []
    for combination in product(*values):
        sets.append(dict(zip(keys, combination, strict=True)))
    return sets


def _parameter_key(params: dict[str, Decimal]) -> str:
    items = sorted(params.items())
    return "|".join(f"{name}={value}" for name, value in items)


def _load_vectorbt_module() -> object:
    try:
        return importlib.import_module("vectorbt")
    except ModuleNotFoundError as exc:
        msg = "vectorbt dependency is required for vectorized backtesting"
        raise ConfigError(msg) from exc
