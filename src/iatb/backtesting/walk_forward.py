"""
Walk-forward optimization with TPE sampler initialization and overfitting checks.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

SharpeScorer = Callable[[list[Decimal]], Decimal]
_SQRT_252 = Decimal("15.8745078664")


@dataclass(frozen=True)
class WalkForwardFold:
    fold_index: int
    in_sample_sharpe: Decimal
    out_sample_sharpe: Decimal
    overfit_ratio: Decimal
    overfit_flag: bool


@dataclass(frozen=True)
class WalkForwardResult:
    folds: list[WalkForwardFold]
    overfitting_detected: bool
    sampler_name: str


class WalkForwardOptimizer:
    """Time-series split optimizer with overfitting signal detection."""

    def __init__(self, n_splits: int = 5, scorer: SharpeScorer | None = None) -> None:
        if n_splits < 2:
            msg = "n_splits must be >= 2"
            raise ConfigError(msg)
        self._n_splits = n_splits
        self._scorer = scorer or _default_sharpe_scorer

    def run(self, returns: list[Decimal]) -> WalkForwardResult:
        if len(returns) < (self._n_splits + 1) * 2:
            msg = "returns length insufficient for walk-forward splits"
            raise ConfigError(msg)
        sampler_name = _initialize_tpe_sampler()
        folds: list[WalkForwardFold] = []
        split_windows = _time_series_splits(returns, self._n_splits)
        for index, (in_sample, out_sample) in enumerate(split_windows, start=1):
            in_sharpe = self._scorer(in_sample)
            out_sharpe = self._scorer(out_sample)
            ratio = _overfit_ratio(in_sharpe, out_sharpe)
            folds.append(
                WalkForwardFold(
                    fold_index=index,
                    in_sample_sharpe=in_sharpe,
                    out_sample_sharpe=out_sharpe,
                    overfit_ratio=ratio,
                    overfit_flag=ratio > Decimal("2"),
                )
            )
        return WalkForwardResult(
            folds=folds,
            overfitting_detected=any(fold.overfit_flag for fold in folds),
            sampler_name=sampler_name,
        )


def _default_sharpe_scorer(returns: list[Decimal]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean_return = sum(returns, Decimal("0")) / Decimal(len(returns))
    abs_dev = [abs(value - mean_return) for value in returns]
    dispersion = sum(abs_dev, Decimal("0")) / Decimal(len(abs_dev))
    if dispersion == Decimal("0"):
        return Decimal("0")
    return (mean_return / dispersion) * _SQRT_252


def _time_series_splits(
    returns: list[Decimal],
    n_splits: int,
) -> list[tuple[list[Decimal], list[Decimal]]]:
    chunk = len(returns) // (n_splits + 1)
    if chunk == 0:
        msg = "returns length too short for requested splits"
        raise ConfigError(msg)
    splits: list[tuple[list[Decimal], list[Decimal]]] = []
    for index in range(1, n_splits + 1):
        train_end = chunk * index
        test_end = len(returns) if index == n_splits else chunk * (index + 1)
        splits.append((returns[:train_end], returns[train_end:test_end]))
    return splits


def _overfit_ratio(in_sample: Decimal, out_sample: Decimal) -> Decimal:
    denominator = max(abs(out_sample), Decimal("0.0001"))
    return abs(in_sample) / denominator


def _initialize_tpe_sampler() -> str:
    try:
        optuna = importlib.import_module("optuna")
    except ModuleNotFoundError as exc:
        msg = "optuna dependency is required for walk-forward optimization"
        raise ConfigError(msg) from exc
    sampler_cls = getattr(getattr(optuna, "samplers", object()), "TPESampler", None)
    if not callable(sampler_cls):
        msg = "optuna.samplers.TPESampler is unavailable"
        raise ConfigError(msg)
    sampler = sampler_cls(seed=42)
    return type(sampler).__name__
