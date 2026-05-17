"""Tests for rl/callbacks.py — training callbacks."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.rl.callbacks import (
    SharpeDropEarlyStop,
    TensorBoardCallbackConfig,
    _mean,
    create_training_callbacks,
)


class TestSharpeDropEarlyStop:
    def test_should_stop_false_below_min_history(self) -> None:
        es = SharpeDropEarlyStop()
        history = [Decimal("1"), Decimal("0.9")]
        assert es.should_stop(history) is False

    def test_should_stop_false_no_drop(self) -> None:
        es = SharpeDropEarlyStop()
        history = [Decimal("1")] * 15
        assert es.should_stop(history) is False

    def test_should_stop_true_on_significant_drop(self) -> None:
        es = SharpeDropEarlyStop(drop_threshold=Decimal("0.15"))
        history = [Decimal("1.0")] * 10 + [Decimal("0.5")] * 5
        assert es.should_stop(history) is True

    def test_zero_baseline_no_stop(self) -> None:
        es = SharpeDropEarlyStop()
        history = [Decimal("0")] * 15
        assert es.should_stop(history) is False

    def test_custom_window_and_min_history(self) -> None:
        es = SharpeDropEarlyStop(window=3, min_history=5)
        history = [Decimal("1")] * 5 + [Decimal("0.4")] * 3
        assert es.should_stop(history) is True


class TestMean:
    def test_empty(self) -> None:
        assert _mean([]) == Decimal("0")

    def test_values(self) -> None:
        assert _mean([Decimal("1"), Decimal("3")]) == Decimal("2")


class TestCreateTrainingCallbacks:
    def test_invalid_check_freq_raises(self) -> None:
        with pytest.raises(ConfigError, match="check_freq must be positive"):
            create_training_callbacks("/tmp/ck", "/tmp/tb", check_freq=0)

    def test_creates_dirs_and_returns_list(self, tmp_path: Path) -> None:
        with patch(
            "iatb.rl.callbacks.importlib.import_module", side_effect=ModuleNotFoundError
        ):
            ck_dir = str(tmp_path / "ck")
            tb_dir = str(tmp_path / "tb")
            result = create_training_callbacks(ck_dir, tb_dir, check_freq=1000)
            assert isinstance(result, list)
            assert len(result) >= 2
            assert Path(ck_dir).is_dir()
            assert Path(tb_dir).is_dir()

    def test_with_custom_early_stop(self, tmp_path: Path) -> None:
        with patch(
            "iatb.rl.callbacks.importlib.import_module", side_effect=ModuleNotFoundError
        ):
            es = SharpeDropEarlyStop(drop_threshold=Decimal("0.2"))
            result = create_training_callbacks(
                str(tmp_path / "ck"),
                str(tmp_path / "tb"),
                early_stop=es,
            )
            assert es in result

    def test_without_sb3_checkpoint(self, tmp_path: Path) -> None:
        with patch(
            "iatb.rl.callbacks.importlib.import_module", side_effect=ModuleNotFoundError
        ):
            result = create_training_callbacks(
                str(tmp_path / "ck"),
                str(tmp_path / "tb"),
            )
            has_checkpoint = any(
                hasattr(c, "save_freq")
                for c in result
                if c is not None
                and not isinstance(c, (SharpeDropEarlyStop, TensorBoardCallbackConfig))
            )
            assert not has_checkpoint
