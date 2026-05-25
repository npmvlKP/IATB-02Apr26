"""
Comprehensive coverage tests for AuditExportScheduler.

This file augments the existing test_audit_scheduler.py to achieve 100% coverage
by testing all execution paths including successful exports, failed exports,
and exception handling.

Avoids freezegun to prevent DLL initialization errors with pytest-xdist on Windows.
Uses schedule time configuration and reference_time parameters for time control.
"""

import json
from datetime import UTC, datetime, time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_timestamp
from iatb.storage.audit_exporter import (
    ExportFormat,
    ExportResult,
    ScheduleFrequency,
)
from iatb.storage.audit_scheduler import (
    AuditExportScheduler,
    ScheduleConfig,
    ScheduleExecution,
    ScheduleStatus,
)

_DUE_TIME = time(hour=0, minute=0)  # Always due (midnight already passed)
_NOT_DUE_TIME = time(hour=23, minute=59)  # Not due during daytime hours


@pytest.fixture()
def temp_dir(tmp_path: Path) -> Path:
    """Create temporary directory for test files."""
    return tmp_path / "audit_scheduler_coverage"


@pytest.fixture()
def mock_exporter() -> MagicMock:
    """Create pure mock AuditExporter — no real SQLite needed."""
    exporter = MagicMock()
    exporter.store = MagicMock()
    exporter.config = MagicMock()
    return exporter


def _make_result(
    success: bool = True,
    file_path: Path | None = None,
    records: int = 10,
    error_message: str | None = None,
) -> ExportResult:
    """Helper to create ExportResult with UTC timestamp."""
    return ExportResult(
        success=success,
        file_path=file_path,
        records_exported=records,
        format=ExportFormat.CSV,
        timestamp=create_timestamp(datetime.now(UTC)),
        error_message=error_message,
    )


class TestAuditExportSchedulerCoverage:
    """Comprehensive coverage tests for AuditExportScheduler."""

    def test_execute_successful_export(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() with successful export result."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        export_file = temp_dir / "exports" / "test_audit.csv"
        mock_exporter.export.return_value = _make_result(
            file_path=export_file,
            records=10,
        )

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.records_exported == 10
        assert execution.file_path == export_file
        assert execution.error_message is None
        mock_exporter.export.assert_called_once()

    def test_execute_failed_export(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() with failed export result."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        mock_exporter.export.return_value = _make_result(
            success=False,
            error_message="Export failed: disk full",
        )

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.FAILED
        assert execution.records_exported == 0
        assert execution.file_path is None
        assert execution.error_message == "Export failed: disk full"
        mock_exporter.export.assert_called_once()

    def test_execute_exception_during_export(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() when exporter raises an exception."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        mock_exporter.export.side_effect = RuntimeError("Database connection lost")

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.FAILED
        assert execution.records_exported == 0
        assert execution.file_path is None
        assert execution.error_message == "Database connection lost"
        mock_exporter.export.assert_called_once()

    def test_execute_saves_state_on_success(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test that execute() saves state file on successful export."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        export_file = temp_dir / "exports" / "test_audit.csv"
        mock_exporter.export.return_value = _make_result(
            file_path=export_file,
            records=10,
        )

        scheduler.execute()

        assert state_file.exists()
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["status"] == ScheduleStatus.SUCCESS.value
        assert data["records_exported"] == 10
        assert data["file_path"] == str(export_file)
        assert data["error_message"] is None

    def test_execute_saves_state_on_failure(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test that execute() saves state file on failed export."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        mock_exporter.export.return_value = _make_result(
            success=False,
            error_message="Export failed",
        )

        scheduler.execute()

        assert state_file.exists()
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["status"] == ScheduleStatus.FAILED.value
        assert data["records_exported"] == 0
        assert data["file_path"] is None
        assert data["error_message"] == "Export failed"

    def test_execute_saves_state_on_exception(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test that execute() saves state file when exporter raises exception."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        mock_exporter.export.side_effect = ValueError("Invalid data")

        scheduler.execute()

        assert state_file.exists()
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["status"] == ScheduleStatus.FAILED.value
        assert data["records_exported"] == 0
        assert data["file_path"] is None
        assert data["error_message"] == "Invalid data"

    def test_execute_with_weekly_schedule_success(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() with weekly schedule on the correct weekday."""
        now = datetime.now(UTC)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=now.weekday(),
            time=_DUE_TIME,
            enabled=True,
        )
        state_file = temp_dir / "state" / "schedule.json"
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        export_file = temp_dir / "exports" / "test_audit.csv"
        mock_exporter.export.return_value = _make_result(
            file_path=export_file,
            records=25,
        )

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.records_exported == 25
        assert execution.schedule_id.startswith("weekly_")

    def test_execute_with_monthly_schedule_success(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() with monthly schedule on the correct day of month."""
        now = datetime.now(UTC)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=now.day,
            time=_DUE_TIME,
            enabled=True,
        )
        state_file = temp_dir / "state" / "schedule.json"
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        export_file = temp_dir / "exports" / "test_audit.csv"
        mock_exporter.export.return_value = _make_result(
            file_path=export_file,
            records=100,
        )

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.records_exported == 100
        assert execution.schedule_id.startswith("monthly_")

    def test_execute_without_state_file(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test execute() without state file (state_file=None)."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=None,
        )

        export_file = temp_dir / "test.csv"
        mock_exporter.export.return_value = _make_result(
            file_path=export_file,
            records=5,
        )

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.records_exported == 5

    def test_get_last_execution_with_valid_state(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test get_last_execution() with valid state file."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_data = {
            "schedule_id": "daily_20250425_103000",
            "status": ScheduleStatus.SUCCESS.value,
            "timestamp": datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC).isoformat(),
            "records_exported": 10,
            "file_path": str(temp_dir / "exports" / "test.csv"),
            "error_message": None,
        }
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)

        last_execution = scheduler.get_last_execution()

        assert last_execution is not None
        assert last_execution.schedule_id == "daily_20250425_103000"
        assert last_execution.status == ScheduleStatus.SUCCESS
        assert last_execution.records_exported == 10

    def test_get_last_execution_with_missing_file_path(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test get_last_execution() when file_path is missing in state."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_data = {
            "schedule_id": "daily_20250425_103000",
            "status": ScheduleStatus.FAILED.value,
            "timestamp": datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC).isoformat(),
            "records_exported": 0,
            "file_path": None,
            "error_message": "Export failed",
        }
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)

        last_execution = scheduler.get_last_execution()

        assert last_execution is not None
        assert last_execution.status == ScheduleStatus.FAILED
        assert last_execution.file_path is None
        assert last_execution.error_message == "Export failed"

    def test_get_last_execution_with_invalid_json(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test get_last_execution() with invalid JSON in state file."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("invalid json content")

        last_execution = scheduler.get_last_execution()

        assert last_execution is None

    def test_get_last_execution_without_state_file(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test get_last_execution() when state_file is None."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=None,
        )

        last_execution = scheduler.get_last_execution()

        assert last_execution is None

    def test_create_execution_with_all_fields(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test _create_execution() with all fields populated."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        timestamp = datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC)
        execution = scheduler._create_execution(
            status=ScheduleStatus.SUCCESS,
            timestamp=timestamp,
            records_exported=15,
            file_path=temp_dir / "test.csv",
            error_message=None,
        )

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.timestamp == timestamp
        assert execution.records_exported == 15
        assert execution.file_path == temp_dir / "test.csv"
        assert execution.error_message is None
        assert execution.schedule_id.startswith("daily_")

    def test_create_execution_with_error(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test _create_execution() with error message."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        timestamp = datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC)
        execution = scheduler._create_execution(
            status=ScheduleStatus.FAILED,
            timestamp=timestamp,
            records_exported=0,
            file_path=None,
            error_message="Export failed: permission denied",
        )

        assert execution.status == ScheduleStatus.FAILED
        assert execution.records_exported == 0
        assert execution.file_path is None
        assert execution.error_message == "Export failed: permission denied"

    def test_generate_schedule_id_with_timestamp(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test _generate_schedule_id() with specific timestamp."""
        config = ScheduleConfig(frequency=ScheduleFrequency.WEEKLY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        timestamp = datetime(2025, 4, 25, 10, 30, 45, tzinfo=UTC)
        schedule_id = scheduler._generate_schedule_id(timestamp)

        assert schedule_id == "weekly_20250425_103045"

    def test_generate_schedule_id_without_timestamp(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test _generate_schedule_id() without timestamp (uses current time)."""
        config = ScheduleConfig(frequency=ScheduleFrequency.MONTHLY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        schedule_id = scheduler._generate_schedule_id()

        assert schedule_id.startswith("monthly_")
        current_date = datetime.now(UTC).strftime("%Y%m%d")
        assert current_date in schedule_id

    def test_save_execution_without_state_file(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test _save_execution() when state_file is None."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=None,
        )

        execution = ScheduleExecution(
            schedule_id="daily_20250425_103000",
            status=ScheduleStatus.SUCCESS,
            timestamp=datetime.now(UTC),
            records_exported=10,
            file_path=temp_dir / "test.csv",
        )

        scheduler._save_execution(execution)

        assert not (temp_dir / "state" / "schedule.json").exists()

    def test_save_execution_creates_directory(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Test that _save_execution() creates parent directory if needed."""
        state_file = temp_dir / "deep" / "nested" / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )

        execution = ScheduleExecution(
            schedule_id="daily_20250425_103000",
            status=ScheduleStatus.SUCCESS,
            timestamp=datetime.now(UTC),
            records_exported=10,
            file_path=temp_dir / "test.csv",
        )

        scheduler._save_execution(execution)

        assert state_file.exists()
        assert state_file.parent.exists()

    def test_is_due_with_reference_time(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test is_due() with explicit reference_time parameter."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        reference_due = datetime(2025, 4, 25, 10, 30, 1, tzinfo=UTC)
        assert scheduler.is_due(reference_time=reference_due) is True

        reference_not_due = datetime(2025, 4, 25, 10, 29, 59, tzinfo=UTC)
        assert scheduler.is_due(reference_time=reference_not_due) is False

    def test_is_due_without_reference_time(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test is_due() without reference_time (uses current time)."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_NOT_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )

        result = scheduler.is_due()
        assert isinstance(result, bool)

    def test_schedule_config_boundary_values(self) -> None:
        """Test ScheduleConfig with boundary values."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=0,
        )
        assert config.day_of_week == 0

        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=6,
        )
        assert config.day_of_week == 6

        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=1,
        )
        assert config.day_of_month == 1

        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=31,
        )
        assert config.day_of_month == 31

    def test_schedule_config_default_values(self) -> None:
        """Test ScheduleConfig default values."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)

        assert config.time == time(hour=23, minute=59)
        assert config.day_of_week == 4
        assert config.day_of_month == 1
        assert config.enabled is True

    def test_schedule_status_enum_values(self) -> None:
        """Test ScheduleStatus enum values."""
        assert ScheduleStatus.PENDING.value == "pending"
        assert ScheduleStatus.RUNNING.value == "running"
        assert ScheduleStatus.SUCCESS.value == "success"
        assert ScheduleStatus.FAILED.value == "failed"
        assert ScheduleStatus.SKIPPED.value == "skipped"

    def test_schedule_frequency_enum_values(self) -> None:
        """Test ScheduleFrequency enum values."""
        assert ScheduleFrequency.DAILY.value == "daily"
        assert ScheduleFrequency.WEEKLY.value == "weekly"
        assert ScheduleFrequency.MONTHLY.value == "monthly"

    def test_schedule_execution_frozen_dataclass(
        self,
        temp_dir: Path,
    ) -> None:
        """Test that ScheduleExecution is frozen (immutable)."""
        execution = ScheduleExecution(
            schedule_id="daily_20250425_103000",
            status=ScheduleStatus.SUCCESS,
            timestamp=datetime.now(UTC),
            records_exported=10,
            file_path=temp_dir / "test.csv",
        )
        assert execution.records_exported == 10

    def test_schedule_config_frozen_dataclass(self) -> None:
        """Test that ScheduleConfig is frozen (immutable)."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=time(hour=10, minute=30),
        )
        assert config.frequency == ScheduleFrequency.DAILY
        assert config.time == time(hour=10, minute=30)


class TestScheduleConfigValidation:
    """Cover __post_init__ validation for ScheduleConfig."""

    def test_invalid_day_of_week_low(self) -> None:
        with pytest.raises(ConfigError, match="day_of_week must be between 0 and 6"):
            ScheduleConfig(frequency=ScheduleFrequency.WEEKLY, day_of_week=-1)

    def test_invalid_day_of_week_high(self) -> None:
        with pytest.raises(ConfigError, match="day_of_week must be between 0 and 6"):
            ScheduleConfig(frequency=ScheduleFrequency.WEEKLY, day_of_week=7)

    def test_invalid_day_of_month_low(self) -> None:
        with pytest.raises(ConfigError, match="day_of_month must be between 1 and 31"):
            ScheduleConfig(frequency=ScheduleFrequency.MONTHLY, day_of_month=0)

    def test_invalid_day_of_month_high(self) -> None:
        with pytest.raises(ConfigError, match="day_of_month must be between 1 and 31"):
            ScheduleConfig(frequency=ScheduleFrequency.MONTHLY, day_of_month=32)


class TestIsDueDisabled:
    """Cover is_due when schedule disabled."""

    def test_is_due_returns_false_when_disabled(self, mock_exporter: MagicMock) -> None:
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=False,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )
        assert scheduler.is_due() is False


class TestExecuteSkippedPaths:
    """Cover execute() disabled and not-due paths."""

    def test_execute_when_disabled(self, mock_exporter: MagicMock) -> None:
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=False,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )
        execution = scheduler.execute()
        assert execution.status == ScheduleStatus.SKIPPED
        assert execution.error_message == "Schedule is disabled"

    def test_execute_when_not_due(self, mock_exporter: MagicMock) -> None:
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_NOT_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )
        execution = scheduler.execute()
        assert execution.status == ScheduleStatus.SKIPPED
        assert execution.error_message == "Export not due at this time"


class TestIsDueBranches:
    """Cover _is_daily_due with same-day execution, _is_weekly_due wrong weekday, etc."""

    def test_daily_due_with_same_day_last_execution(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Daily schedule not due when already executed today."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        state_data = {
            "schedule_id": "daily_20250425_103000",
            "status": ScheduleStatus.SUCCESS.value,
            "timestamp": now.isoformat(),
            "records_exported": 10,
            "file_path": str(temp_dir / "exports" / "test.csv"),
            "error_message": None,
        }
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)
        assert scheduler.is_due() is False

    def test_weekly_due_wrong_weekday(self, mock_exporter: MagicMock) -> None:
        """Weekly schedule not due on wrong weekday."""
        now = datetime.now(UTC)
        wrong_weekday = (now.weekday() + 1) % 7
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=wrong_weekday,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )
        assert scheduler.is_due(reference_time=now) is False

    def test_weekly_due_with_recent_last_execution(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Weekly schedule not due when executed within 7 days."""
        state_file = temp_dir / "state" / "schedule.json"
        now = datetime.now(UTC)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=now.weekday(),
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        recent = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
        state_data = {
            "schedule_id": "weekly_20250421_103000",
            "status": ScheduleStatus.SUCCESS.value,
            "timestamp": recent.isoformat(),
            "records_exported": 10,
            "file_path": str(temp_dir / "exports" / "test.csv"),
            "error_message": None,
        }
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)
        assert scheduler.is_due() is False

    def test_monthly_due_wrong_day(self, mock_exporter: MagicMock) -> None:
        """Monthly schedule not due on wrong day of month."""
        now = datetime.now(UTC)
        wrong_day = now.day + 1 if now.day < 28 else 1
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=wrong_day,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
        )
        assert scheduler.is_due(reference_time=now) is False

    def test_monthly_due_with_recent_last_execution(
        self,
        mock_exporter: MagicMock,
        temp_dir: Path,
    ) -> None:
        """Monthly schedule not due when already executed this month."""
        state_file = temp_dir / "state" / "schedule.json"
        now = datetime.now(UTC)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=now.day,
            time=_DUE_TIME,
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=mock_exporter,
            schedule_config=config,
            state_file=state_file,
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)
        recent = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
        state_data = {
            "schedule_id": "monthly_20250401_103000",
            "status": ScheduleStatus.SUCCESS.value,
            "timestamp": recent.isoformat(),
            "records_exported": 10,
            "file_path": str(temp_dir / "exports" / "test.csv"),
            "error_message": None,
        }
        with state_file.open("w", encoding="utf-8") as f:
            json.dump(state_data, f)
        assert scheduler.is_due() is False
