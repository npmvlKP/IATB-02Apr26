"""
Additional tests for rl/callbacks.py to improve coverage to 90%+.
"""

from decimal import Decimal

import pytest
from iatb.rl.callbacks import (
    SharpeDropEarlyStop,
    TensorBoardCallbackConfig,
    _checkpoint_callback_or_none,
    _mean,
    create_training_callbacks,
)


class TestCreateTrainingCallbacks:
    """Test create_training_callbacks function."""

    def test_create_callbacks_with_tensorboard(self, tmp_path) -> None:
        """Test creating callbacks with tensorboard log dir."""
        callbacks = create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
        )
        # With stable_baselines3 available (via mock), we get 3 callbacks
        # Without it, we get 2 callbacks
        assert len(callbacks) in {2, 3}
        assert any(isinstance(cb, SharpeDropEarlyStop) for cb in callbacks)
        assert any(isinstance(cb, TensorBoardCallbackConfig) for cb in callbacks)

    def test_create_callbacks_with_early_stop(self, tmp_path) -> None:
        """Test creating callbacks with custom early stop."""
        early_stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.2"), window=10, min_history=5
        )
        callbacks = create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
            early_stop=early_stop,
        )
        assert any(cb is early_stop for cb in callbacks)

    def test_create_callbacks_with_both(self, tmp_path) -> None:
        """Test creating callbacks with both checkpoint and tensorboard."""
        callbacks = create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
            check_freq=5000,
        )
        assert len(callbacks) >= 2

    def test_create_callbacks_with_none(self, tmp_path) -> None:
        """Test creating callbacks with None early stop uses default."""
        callbacks = create_training_callbacks(
            checkpoint_dir=str(tmp_path),
            tensorboard_log_dir=str(tmp_path),
            early_stop=None,
        )
        assert any(isinstance(cb, SharpeDropEarlyStop) for cb in callbacks)


class TestCheckpointCallbackOrNone:
    """Test _checkpoint_callback_or_none function."""

    def test_checkpoint_callback_with_valid_path(self, tmp_path) -> None:
        """Test checkpoint callback creation with valid path."""
        result = _checkpoint_callback_or_none(str(tmp_path), 10000)
        # Should return None if stable-baselines3 is not available
        assert result is None or hasattr(result, "save_freq")

    def test_checkpoint_callback_with_none_path(self) -> None:
        """Test checkpoint callback with None path."""
        result = _checkpoint_callback_or_none("nonexistent", 10000)
        # Should return None if stable-baselines3 is not available
        assert result is None or hasattr(result, "save_freq")


class TestSharpeDropEarlyStop:
    """Test SharpeDropEarlyStop dataclass."""

    def test_initialization_defaults(self) -> None:
        """Test initialization with default values."""
        stop = SharpeDropEarlyStop()
        assert stop.drop_threshold == Decimal("0.15")
        assert stop.window == 5
        assert stop.min_history == 10

    def test_initialization_custom(self) -> None:
        """Test initialization with custom values."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.25"), window=7, min_history=15
        )
        assert stop.drop_threshold == Decimal("0.25")
        assert stop.window == 7
        assert stop.min_history == 15

    def test_should_stop_with_insufficient_history(self) -> None:
        """Test should_stop returns False with insufficient history."""
        stop = SharpeDropEarlyStop()
        history = [Decimal("1.0")] * 5
        assert not stop.should_stop(history)

    def test_should_stop_with_drop_below_threshold(self) -> None:
        """Test should_stop triggers on large drop."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.15"), window=5, min_history=10
        )
        # History: first 5 at 1.0, next 5 at 0.7 (30% drop)
        history = [Decimal("1.0")] * 5 + [Decimal("0.7")] * 5
        assert stop.should_stop(history)

    def test_should_stop_with_no_drop(self) -> None:
        """Test should_stop returns False when no significant drop."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.15"), window=5, min_history=10
        )
        history = [Decimal("1.0")] * 10
        assert not stop.should_stop(history)

    def test_should_stop_with_improvement(self) -> None:
        """Test should_stop returns False with improving Sharpe."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.15"), window=5, min_history=10
        )
        history = [Decimal("1.0")] * 5 + [Decimal("1.2")] * 5
        assert not stop.should_stop(history)

    def test_should_stop_with_zero_baseline(self) -> None:
        """Test should_stop returns False with zero baseline."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.15"), window=5, min_history=10
        )
        history = [Decimal("0")] * 5 + [Decimal("0.5")] * 5
        assert not stop.should_stop(history)

    def test_should_stop_with_negative_baseline(self) -> None:
        """Test should_stop returns False with negative baseline."""
        stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.15"), window=5, min_history=10
        )
        history = [Decimal("-0.5")] * 5 + [Decimal("-0.3")] * 5
        assert not stop.should_stop(history)

    def test_immutability(self) -> None:
        """Test that SharpeDropEarlyStop is immutable (frozen dataclass)."""
        stop = SharpeDropEarlyStop()
        # FrozenInstanceError is a subclass of AttributeError in dataclasses
        with pytest.raises(AttributeError):
            stop.drop_threshold = Decimal("0.2")


class TestTensorBoardCallbackConfig:
    """Test TensorBoardCallbackConfig dataclass."""

    def test_initialization(self, tmp_path) -> None:
        """Test TensorBoardCallbackConfig initialization."""
        log_dir = str(tmp_path / "logs")
        config = TensorBoardCallbackConfig(log_dir=log_dir)
        assert config.log_dir == log_dir

    def test_immutability(self, tmp_path) -> None:
        """Test that TensorBoardCallbackConfig is immutable."""
        log_dir = str(tmp_path / "logs")
        config = TensorBoardCallbackConfig(log_dir=log_dir)
        # FrozenInstanceError is a subclass of AttributeError in dataclasses
        with pytest.raises(AttributeError):
            config.log_dir = "/new/path"


class TestMeanFunction:
    """Test _mean utility function."""

    def test_mean_with_values(self) -> None:
        """Test _mean with list of values."""
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        result = _mean(values)
        assert result == Decimal("3")

    def test_mean_with_empty_list(self) -> None:
        """Test _mean with empty list returns 0."""
        result = _mean([])
        assert result == Decimal("0")

    def test_mean_with_negative_values(self) -> None:
        """Test _mean with negative values."""
        values = [Decimal("-5"), Decimal("5"), Decimal("0")]
        result = _mean(values)
        assert result == Decimal("0")

    def test_mean_with_decimals(self) -> None:
        """Test _mean with decimal values."""
        values = [Decimal("0.5"), Decimal("1.5"), Decimal("2.5")]
        result = _mean(values)
        assert result == Decimal("1.5")
