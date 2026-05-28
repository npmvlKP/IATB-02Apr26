"""Coverage tests for iatb.core.preflight — Preflight checks, clock drift."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.preflight import (
    _check_clock_drift,
    _check_executor,
    _check_kill_switch,
    _check_path_exists,
    _check_path_writable,
    _run_check,
    run_preflight_checks,
)


class TestRunCheck:
    def test_passing_check_returns_current(self) -> None:
        result = _run_check("test_ok", lambda: None, True)
        assert result is True

    def test_failing_check_returns_false(self) -> None:
        def fail() -> None:
            raise ConfigError("fail")

        with patch("iatb.core.preflight.logger"):
            result = _run_check("test_fail", fail, True)
            assert result is False

    def test_failing_check_resets_even_if_current_true(self) -> None:
        def fail() -> None:
            raise ConfigError("fail")

        result = _run_check("test_fail", fail, True)
        assert result is False

    def test_passing_preserves_false_if_previously_failed(self) -> None:
        result = _run_check("test_ok", lambda: None, False)
        assert result is False


class TestCheckClockDrift:
    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_no_drift_passes(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        from datetime import timedelta

        mock_detector.check_drift.return_value = timedelta(seconds=0)
        mock_cls.return_value = mock_detector
        _check_clock_drift()

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_excessive_drift_raises(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        from datetime import timedelta

        mock_detector.check_drift.return_value = timedelta(seconds=10)
        mock_cls.return_value = mock_detector
        with pytest.raises(ConfigError, match="clock drift"):
            _check_clock_drift()

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_ntp_unreachable_skips(self, mock_cls: MagicMock) -> None:
        mock_detector = MagicMock()
        mock_detector.check_drift.side_effect = Exception("NTP unreachable")
        mock_cls.return_value = mock_detector
        _check_clock_drift()


class TestCheckExecutor:
    def test_no_open_orders_passes(self) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        _check_executor(executor)

    def test_open_orders_raises(self) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 5
        with pytest.raises(ConfigError, match="open orders"):
            _check_executor(executor)

    def test_executor_exception_raises(self) -> None:
        executor = MagicMock()
        executor.cancel_all.side_effect = RuntimeError("connection failed")
        with pytest.raises(ConfigError, match="not responding"):
            _check_executor(executor)


class TestCheckKillSwitch:
    def test_not_engaged_passes(self) -> None:
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        _check_kill_switch(kill_switch)

    def test_engaged_raises(self) -> None:
        kill_switch = MagicMock()
        kill_switch.is_engaged = True
        with pytest.raises(ConfigError, match="kill switch"):
            _check_kill_switch(kill_switch)


class TestCheckPathExists:
    def test_existing_path_passes(self, tmp_path: Path) -> None:
        _check_path_exists(tmp_path)

    def test_missing_path_raises(self) -> None:
        with pytest.raises(ConfigError, match="does not exist"):
            _check_path_exists(Path("/nonexistent/path/abc123"))


class TestCheckPathWritable:
    def test_writable_parent_passes(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _check_path_writable(db_path)

    def test_creates_parent_if_missing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "test.db"
        _check_path_writable(db_path)
        assert (tmp_path / "subdir").exists()


class TestRunPreflightChecks:
    def test_all_pass(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is True

    def test_kill_switch_engaged_fails(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        kill_switch = MagicMock()
        kill_switch.is_engaged = True
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is False

    def test_missing_data_dir_fails(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "nonexistent"
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is False

    def test_executor_failure_fails(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 5
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is False

    def test_multiple_failures_returns_false(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 3
        kill_switch = MagicMock()
        kill_switch.is_engaged = True
        data_dir = tmp_path / "nonexistent"
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is False

    def test_all_pass_returns_true(self, tmp_path: Path) -> None:
        executor = MagicMock()
        executor.cancel_all.return_value = 0
        kill_switch = MagicMock()
        kill_switch.is_engaged = False
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "audit.db"
        with patch("iatb.core.preflight._check_clock_drift"):
            result = run_preflight_checks(executor, kill_switch, data_dir, audit_path)
        assert result is True


class TestRunCheckLogging:
    def test_passing_check_logs_info(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.INFO):
            _run_check("test_pass", lambda: None, True)
        assert any("PASS" in r.message for r in caplog.records)

    def test_failing_check_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        def fail() -> None:
            raise ConfigError("test fail")

        with caplog.at_level(logging.ERROR):
            _run_check("test_fail_log", fail, True)
        assert any("FAIL" in r.message for r in caplog.records)


class TestCheckPathWritableEdgeCases:
    def test_deeply_nested_parent_creates_all(self, tmp_path: Path) -> None:
        db_path = tmp_path / "a" / "b" / "c" / "test.db"
        _check_path_writable(db_path)
        assert (tmp_path / "a" / "b" / "c").exists()

    def test_existing_parent_no_error(self, tmp_path: Path) -> None:
        existing = tmp_path / "existing"
        existing.mkdir()
        db_path = existing / "test.db"
        _check_path_writable(db_path)
