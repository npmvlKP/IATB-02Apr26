"""
Callback utilities for RL training control.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class TensorBoardCallbackConfig:
    log_dir: str


@dataclass(frozen=True)
class SharpeDropEarlyStop:
    drop_threshold: Decimal = Decimal("0.15")
    window: int = 5
    min_history: int = 10

    def should_stop(self, sharpe_history: list[Decimal]) -> bool:
        if len(sharpe_history) < self.min_history:
            return False
        recent = _mean(sharpe_history[-self.window :])
        baseline_end = len(sharpe_history) - self.window
        baseline = _mean(sharpe_history[:baseline_end])
        if baseline <= Decimal("0"):
            return False
        drop_ratio = (baseline - recent) / baseline
        return drop_ratio > self.drop_threshold


def create_training_callbacks(
    checkpoint_dir: str,
    tensorboard_log_dir: str,
    check_freq: int = 10_000,
    early_stop: SharpeDropEarlyStop | None = None,
) -> list[object]:
    if check_freq <= 0:
        msg = "check_freq must be positive"
        raise ConfigError(msg)
    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(tensorboard_log_dir).mkdir(parents=True, exist_ok=True)
    callbacks: list[object] = [early_stop or SharpeDropEarlyStop()]
    callbacks.append(TensorBoardCallbackConfig(log_dir=tensorboard_log_dir))
    checkpoint = _checkpoint_callback_or_none(checkpoint_dir, check_freq)
    if checkpoint is not None:
        callbacks.append(checkpoint)
    return callbacks


def _checkpoint_callback_or_none(checkpoint_dir: str, check_freq: int) -> object | None:
    try:
        module = importlib.import_module("stable_baselines3.common.callbacks")
    except ModuleNotFoundError:
        return None
    callback_cls = getattr(module, "CheckpointCallback", None)
    if not callable(callback_cls):
        return None
    callback = callback_cls(save_freq=check_freq, save_path=checkpoint_dir, name_prefix="iatb_rl")
    return cast(object, callback)


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))
