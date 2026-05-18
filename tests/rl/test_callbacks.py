import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
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
    callback = SharpeDropEarlyStop(
        drop_threshold=Decimal("0.15"), window=5, min_history=10
    )
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
    monkeypatch.setattr(
        "iatb.rl.callbacks.importlib.import_module", lambda _: fake_module
    )
    callbacks = create_training_callbacks(
        checkpoint_dir=str(tmp_path),
        tensorboard_log_dir=str(tmp_path),
        check_freq=10_000,
    )
    assert any(isinstance(item, _FakeCheckpointCallback) for item in callbacks)


def test_sharpe_drop_early_stop_with_zero_baseline() -> None:
    """Test that zero/negative baseline doesn't trigger early stop."""
    stopper = SharpeDropEarlyStop(
        drop_threshold=Decimal("0.2"), window=3, min_history=5
    )
    # All values <= 0 should not trigger
    assert not stopper.should_stop([Decimal("0")] * 10)
    assert not stopper.should_stop([Decimal("-1")] * 10)
    assert not stopper.should_stop(
        [Decimal("0.5"), Decimal("0"), Decimal("-0.5")] + [Decimal("1")] * 7
    )


def test_create_training_callbacks_with_non_callable_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    """Test callback creation when CheckpointCallback is not callable."""
    fake_module = SimpleNamespace(CheckpointCallback="not_callable")
    monkeypatch.setattr(
        "iatb.rl.callbacks.importlib.import_module", lambda _: fake_module
    )
    callbacks = create_training_callbacks(
        checkpoint_dir=str(tmp_path),
        tensorboard_log_dir=str(tmp_path),
        check_freq=5000,
        early_stop=SharpeDropEarlyStop(),
    )
    assert len(callbacks) == 2  # early_stop + tensorboard (no checkpoint)


def test_create_training_callbacks_rejects_invalid_check_freq(
    tmp_path: object,
) -> None:
    """Test that check_freq must be positive."""
    with pytest.raises(ConfigError, match="check_freq must be positive"):
        create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
            check_freq=0,
        )
    with pytest.raises(ConfigError, match="check_freq must be positive"):
        create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
            check_freq=-1,
        )
