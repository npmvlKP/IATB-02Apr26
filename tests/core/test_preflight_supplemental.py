"""Supplemental coverage tests for iatb.core.preflight — additional error paths and edge cases."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.preflight import (
    _check_clock_drift,
    _check_executor,
    _check_path_writable,
    _run_check,
    run_preflight_checks,
)


class TestRunCheckEdgeCases:
    def test_non_config_error_propagates(self) -> None:
        def raise_runtime() -> None:
            raise RuntimeError("unexpected")

        with pytest.raises(RuntimeError, match="unexpected"):
            _run_check("test", raise_runtime, True)

    def test_check_preserves_current_false(self) -> None:
        result = _run_check("ok", lambda: None, False)
        assert result is False

    def test_multiple_failures_all_return_false(self) -> None:
        def fail() -> None:
            raise ConfigError("fail")

        current = True
        current = _run_check("a", fail, current)
        current = _run_check("b", fail, current)
        current = _run_check("c", lambda: None, current)
        assert current is False


class TestCheckClockDriftEdgeCases:
    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_custom_max_drift_boundary(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=2)
        mock_cls.return_value = mock_detector
        _check_clock_drift(max_drift_seconds=2)

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_drift_exceeds_custom_threshold(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=3)
        mock_cls.return_value = mock_detector
        with pytest.raises(ConfigError, match="clock drift"):
            _check_clock_drift(max_drift_seconds=2)

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_negative_drift_check(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=-3)
        mock_cls.return_value = mock_detector
        with pytest.raises(ConfigError, match="clock drift"):
            _check_clock_drift(max_drift_seconds=2)

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_zero_drift_passes(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=0)
        mock_cls.return_value = mock_detector
        _check_clock_drift()


class TestCheckExecutorEdgeCases:
    def test_executor_returns_large_count(self) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 100
        with pytest.raises(ConfigError, match="open orders"):
            _check_executor(executor)

    def test_executor_returns_one_order(self) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 1
        with pytest.raises(ConfigError, match="open orders"):
            _check_executor(executor)

    def test_executor_attribute_error_raises(self) -> None:
        executor = MagicMock()
        executor.cancel_all.side_effect = AttributeError("no attribute")
        with pytest.raises(ConfigError, match="not responding"):
            _check_executor(executor)


class TestCheckPathWritableEdgeCases:
    def test_existing_writable_parent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "audit.db"
        _check_path_writable(db_path)
        assert tmp_path.exists()

    def test_deeply_nested_path(self, tmp_path: Path) -> None:
        db_path = tmp_path / "a" / "b" / "c" / "audit.db"
        _check_path_writable(db_path)
        assert (tmp_path / "a" / "b" / "c").exists()


class TestRunPreflightChecksEdgeCases:
    def test_executor_fail_fails_preflight(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.side_effect = RuntimeError("conn failed")
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is False

    def test_missing_audit_path_succeeds_writable(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "new_audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is True
