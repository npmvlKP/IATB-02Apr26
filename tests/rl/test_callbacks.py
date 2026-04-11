import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.rl.callbacks import (
    SharpeDropEarlyStop,
    TensorBoardCallbackConfig,
    create_training_callbacks,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeCheckpointCallback:
    def __init__(self, save_freq: int, save_path: str, name_prefix: str) -> None:
        self.save_freq = save_freq
        self.save_path = save_path
        self.name_prefix = name_prefix


def test_sharpe_drop_early_stop_triggers_on_large_degradation() -> None:
    callback = SharpeDropEarlyStop(drop_threshold=Decimal("0.15"), window=5, min_history=10)
    history = [Decimal("1.0")] * 5 + [Decimal("0.7")] * 5
    assert callback.should_stop(history)


def test_create_training_callbacks_returns_metadata_without_sb3(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setattr(
        "iatb.rl.callbacks.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    callbacks = create_training_callbacks(
        checkpoint_dir=str(tmp_path),
        tensorboard_log_dir=str(tmp_path),
    )
    assert any(isinstance(item, SharpeDropEarlyStop) for item in callbacks)
    assert any(isinstance(item, TensorBoardCallbackConfig) for item in callbacks)


def test_create_training_callbacks_includes_checkpoint_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    fake_module = SimpleNamespace(CheckpointCallback=_FakeCheckpointCallback)
    monkeypatch.setattr("iatb.rl.callbacks.importlib.import_module", lambda _: fake_module)
    callbacks = create_training_callbacks(
        checkpoint_dir=str(tmp_path),
        tensorboard_log_dir=str(tmp_path),
        check_freq=10_000,
    )
    assert any(isinstance(item, _FakeCheckpointCallback) for item in callbacks)
