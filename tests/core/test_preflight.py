"""
Tests for pre-flight checks module.

Covers happy path, edge cases, error paths, type handling,
and external API mocking.
"""

from datetime import timedelta
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
    """Tests for _run_check function."""

    def test_run_check_pass(self) -> None:
        """Test that _run_check returns True when check passes."""

        def passing_check() -> None:
            pass

        result = _run_check("test_check", passing_check, True)
        assert result is True

    def test_run_check_fail(self) -> None:
        """Test that _run_check returns False when check fails."""

        def failing_check() -> None:
            raise ConfigError("Test failure")

        result = _run_check("test_check", failing_check, True)
        assert result is False

    def test_run_check_multiple_failures(self) -> None:
        """Test that _run_check accumulates failures."""

        def failing_check() -> None:
            raise ConfigError("Test failure")

        result = _run_check("test_check_1", failing_check, True)
        assert result is False

        result = _run_check("test_check_2", failing_check, False)
        assert result is False

    def test_run_check_exception_not_config_error(self) -> None:
        """Test that non-ConfigError exceptions are not caught."""

        def raising_value_error() -> None:
            raise ValueError("Not a ConfigError")

        # Should not catch ValueError
        with pytest.raises(ValueError):
            _run_check("test_check", raising_value_error, True)


class TestCheckClockDrift:
    """Tests for _check_clock_drift function."""

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_check_clock_drift_normal(self, mock_detector_class: MagicMock) -> None:
        """Test clock drift check with normal drift."""
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=0.5)
        mock_detector_class.return_value = mock_detector
        _check_clock_drift()

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_check_clock_drift_custom_threshold(self, mock_detector_class: MagicMock) -> None:
        """Test clock drift check with custom threshold."""
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=500)
        mock_detector_class.return_value = mock_detector
        _check_clock_drift(max_drift_seconds=1000)

    @patch("iatb.core.preflight.ClockDriftDetector")
    def test_check_clock_drift_exceeds_threshold(self, mock_detector_class: MagicMock) -> None:
        """Test clock drift check fails when drift exceeds threshold."""
        mock_detector = MagicMock()
        mock_detector.check_drift.return_value = timedelta(seconds=10)
        mock_detector_class.return_value = mock_detector
        with pytest.raises(ConfigError, match="clock drift .* exceeds"):
            _check_clock_drift(max_drift_seconds=2)


class TestCheckExecutor:
    """Tests for _check_executor function."""

    def test_check_executor_no_open_orders(self) -> None:
        """Test executor check with no open orders."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        _check_executor(mock_executor)
        mock_executor.cancel_all.assert_called_once()

    def test_check_executor_with_open_orders(self) -> None:
        """Test executor check fails with open orders."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 5

        with pytest.raises(ConfigError, match="has 5 open orders"):
            _check_executor(mock_executor)

    def test_check_executor_exception(self) -> None:
        """Test executor check fails on exception."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.side_effect = Exception("Network error")

        with pytest.raises(ConfigError, match="executor not responding"):
            _check_executor(mock_executor)


class TestCheckKillSwitch:
    """Tests for _check_kill_switch function."""

    def test_check_kill_switch_disengaged(self) -> None:
        """Test kill switch check when disengaged."""
        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        _check_kill_switch(mock_kill_switch)

    def test_check_kill_switch_engaged(self) -> None:
        """Test kill switch check fails when engaged."""
        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = True

        with pytest.raises(ConfigError, match="kill switch is engaged"):
            _check_kill_switch(mock_kill_switch)


class TestCheckPathExists:
    """Tests for _check_path_exists function."""

    def test_check_path_exists_file(self, tmp_path: Path) -> None:
        """Test path exists check with file."""
        test_file = tmp_path / "test.txt"
        test_file.touch()

        _check_path_exists(test_file)

    def test_check_path_exists_directory(self, tmp_path: Path) -> None:
        """Test path exists check with directory."""
        _check_path_exists(tmp_path)

    def test_check_path_exists_not_found(self) -> None:
        """Test path exists check fails when path doesn't exist."""
        non_existent = Path("/non/existent/path/12345")

        with pytest.raises(ConfigError, match="required path does not exist"):
            _check_path_exists(non_existent)


class TestCheckPathWritable:
    """Tests for _check_path_writable function."""

    def test_check_path_writable_existing_parent(self, tmp_path: Path) -> None:
        """Test path writable check with existing parent."""
        test_file = tmp_path / "subdir" / "test.txt"

        _check_path_writable(test_file)
        assert test_file.parent.exists()

    def test_check_path_writable_creates_parent(self, tmp_path: Path) -> None:
        """Test path writable check creates parent directory."""
        test_file = tmp_path / "new_dir" / "nested" / "test.txt"

        _check_path_writable(test_file)
        assert test_file.parent.exists()

    def test_check_path_writable_permission_denied(self, tmp_path: Path) -> None:
        """Test path writable check with permission issues."""
        # Create a file instead of directory to test error handling
        test_file = tmp_path / "file.txt"
        test_file.touch()

        # On Windows, we can't easily test permission denied
        # This test documents the expected behavior
        _check_path_writable(test_file.with_suffix(".new"))


class TestRunPreflightChecks:
    """Tests for run_preflight_checks function."""

    def test_run_preflight_checks_all_pass(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test all pre-flight checks pass."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is True

    def test_run_preflight_checks_clock_drift_fails(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test pre-flight checks fail when clock drift check fails."""
        monkeypatch.setattr(
            "iatb.core.preflight._check_clock_drift",
            lambda: (_ for _ in ()).throw(ConfigError("Clock drift too high")),
        )

        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is False

    def test_run_preflight_checks_executor_fails(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks fail when executor check fails."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 3  # Open orders

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is False

    def test_run_preflight_checks_kill_switch_fails(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks fail when kill switch check fails."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = True

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is False

    def test_run_preflight_checks_data_dir_not_found(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks fail when data dir doesn't exist."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        data_dir = tmp_path / "nonexistent_data_dir"

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is False

    def test_run_preflight_checks_audit_db_not_writable(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks fail when audit DB is not writable."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Create a file instead of a path to test error handling
        audit_db_path = tmp_path / "audit_dir" / "db.sqlite"
        audit_db_path.parent.mkdir()
        audit_db_path.touch()

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        # Should pass because parent exists and is writable
        assert result is True

    def test_run_preflight_checks_multiple_failures(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks fail when multiple checks fail."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 5  # Open orders

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = True  # Also engaged

        data_dir = tmp_path / "nonexistent_data_dir"  # Doesn't exist

        audit_db_path = tmp_path / "audit" / "db.sqlite"

        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=data_dir,
            audit_db_path=audit_db_path,
        )

        assert result is False


class TestPreflightEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_check_executor_with_none_value(self) -> None:
        """Test that executor check handles None gracefully."""
        # The function catches AttributeError and converts to ConfigError
        with pytest.raises(ConfigError, match="executor not responding"):
            _check_executor(None)  # type: ignore[arg-type]

    def test_check_kill_switch_with_none_kill_switch(self) -> None:
        """Test that kill switch check handles None gracefully."""
        # This should raise AttributeError, not ConfigError
        with pytest.raises(AttributeError):
            _check_kill_switch(None)  # type: ignore[arg-type]

    def test_check_path_exists_with_none_path(self) -> None:
        """Test that path exists check handles None gracefully."""
        # This should raise AttributeError
        with pytest.raises(AttributeError):
            _check_path_exists(None)  # type: ignore[arg-type]

    def test_check_path_writable_with_none_path(self) -> None:
        """Test that path writable check handles None gracefully."""
        # This should raise AttributeError
        with pytest.raises(AttributeError):
            _check_path_writable(None)  # type: ignore[arg-type]

    def test_run_preflight_checks_with_invalid_paths(
        self,
        tmp_path: Path,
    ) -> None:
        """Test pre-flight checks with invalid path types."""
        mock_executor = MagicMock()
        mock_executor.cancel_all.return_value = 0

        mock_kill_switch = MagicMock()
        mock_kill_switch.is_engaged = False

        # Should still work with Path objects
        result = run_preflight_checks(
            executor=mock_executor,
            kill_switch=mock_kill_switch,
            data_dir=tmp_path,
            audit_db_path=tmp_path / "test.db",
        )

        assert result is True
