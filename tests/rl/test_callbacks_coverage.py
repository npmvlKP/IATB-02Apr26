"""
Comprehensive coverage tests for callbacks.py.

Tests callback utilities for RL training control.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.callbacks import (
    SharpeDropEarlyStop,
    TensorBoardCallbackConfig,
    create_training_callbacks,
)


class TestTensorBoardCallbackConfig:
    """Test TensorBoard callback configuration."""

    def test_create_config(self):
        """Test creating TensorBoard callback config."""
        config = TensorBoardCallbackConfig(log_dir="/tmp/logs")
        assert config.log_dir == "/tmp/logs"


class TestSharpeDropEarlyStop:
    """Test Sharpe drop early stopping."""

    def test_default_config(self):
        """Test default configuration values."""
        early_stop = SharpeDropEarlyStop()
        assert early_stop.drop_threshold == Decimal("0.15")
        assert early_stop.window == 5
        assert early_stop.min_history == 10

    def test_custom_config(self):
        """Test custom configuration values."""
        early_stop = SharpeDropEarlyStop(
            drop_threshold=Decimal("0.2"),
            window=10,
            min_history=20,
        )
        assert early_stop.drop_threshold == Decimal("0.2")
        assert early_stop.window == 10

    def test_should_stop_insufficient_history(self):
        """Test that insufficient history doesn't trigger stop."""
        early_stop = SharpeDropEarlyStop()
        sharpe_history = [Decimal("1.0"), Decimal("0.9"), Decimal("0.8")]

        result = early_stop.should_stop(sharpe_history)

        assert result is False

    def test_should_stop_no_drop(self):
        """Test that no drop doesn't trigger stop."""
        early_stop = SharpeDropEarlyStop()
        sharpe_history = [
            Decimal("1.0"),
            Decimal("1.1"),
            Decimal("1.2"),
            Decimal("1.1"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.1"),
            Decimal("1.2"),
            Decimal("1.3"),
            Decimal("1.2"),
            Decimal("1.3"),
        ]

        result = early_stop.should_stop(sharpe_history)

        assert result is False

    def test_should_stop_with_drop(self):
        """Test that significant drop triggers stop."""
        early_stop = SharpeDropEarlyStop(drop_threshold=Decimal("0.1"))
        sharpe_history = [
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("0.9"),
            Decimal("0.8"),
            Decimal("0.7"),
            Decimal("0.6"),
            Decimal("0.5"),
        ]

        result = early_stop.should_stop(sharpe_history)

        assert result is True

    def test_should_stop_negative_baseline(self):
        """Test that negative baseline doesn't trigger stop."""
        early_stop = SharpeDropEarlyStop()
        sharpe_history = [
            Decimal("-0.5"),
            Decimal("-0.4"),
            Decimal("-0.3"),
            Decimal("-0.2"),
            Decimal("-0.1"),
            Decimal("-0.2"),
            Decimal("-0.3"),
            Decimal("-0.4"),
            Decimal("-0.5"),
            Decimal("-0.6"),
        ]

        result = early_stop.should_stop(sharpe_history)

        assert result is False


class TestCreateTrainingCallbacks:
    """Test creating training callbacks."""

    def test_create_callbacks_with_defaults(self):
        """Test creating callbacks with default parameters."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("stable_baselines3 not found")

            callbacks = create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
            )

            assert len(callbacks) >= 2
            assert any(isinstance(cb, SharpeDropEarlyStop) for cb in callbacks)
            assert any(isinstance(cb, TensorBoardCallbackConfig) for cb in callbacks)

    def test_create_callbacks_with_custom_early_stop(self):
        """Test creating callbacks with custom early stopping."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("stable_baselines3 not found")

            early_stop = SharpeDropEarlyStop(drop_threshold=Decimal("0.25"))
            callbacks = create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
                early_stop=early_stop,
            )

            assert any(cb is early_stop for cb in callbacks)

    def test_create_callbacks_invalid_check_freq_raises_error(self):
        """Test that invalid check_freq raises ConfigError."""
        with pytest.raises(ConfigError, match="check_freq must be positive"):
            create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
                check_freq=0,
            )

    def test_create_callbacks_negative_check_freq_raises_error(self):
        """Test that negative check_freq raises ConfigError."""
        with pytest.raises(ConfigError, match="check_freq must be positive"):
            create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
                check_freq=-1,
            )

    def test_create_callbacks_with_checkpoint_available(self):
        """Test creating callbacks when checkpoint callback is available."""
        mock_module = MagicMock()
        mock_checkpoint_cls = MagicMock()
        mock_module.CheckpointCallback = mock_checkpoint_cls
        mock_callback_instance = MagicMock()
        mock_checkpoint_cls.return_value = mock_callback_instance

        with patch("importlib.import_module", return_value=mock_module):
            callbacks = create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
                check_freq=5000,
            )

            assert len(callbacks) >= 3
            assert any(isinstance(cb, SharpeDropEarlyStop) for cb in callbacks)
            assert any(isinstance(cb, TensorBoardCallbackConfig) for cb in callbacks)
            assert mock_callback_instance in callbacks
            mock_checkpoint_cls.assert_called_once_with(
                save_freq=5000, save_path="/tmp/checkpoints", name_prefix="iatb_rl"
            )

    def test_create_callbacks_checkpoint_not_found(self):
        """Test creating callbacks when CheckpointCallback is not found."""
        mock_module = MagicMock()
        mock_module.CheckpointCallback = None

        with patch("importlib.import_module", return_value=mock_module):
            callbacks = create_training_callbacks(
                checkpoint_dir="/tmp/checkpoints",
                tensorboard_log_dir="/tmp/logs",
            )

            assert len(callbacks) == 2
            assert any(isinstance(cb, SharpeDropEarlyStop) for cb in callbacks)
            assert any(isinstance(cb, TensorBoardCallbackConfig) for cb in callbacks)
