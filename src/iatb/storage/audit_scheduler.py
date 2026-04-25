"""
Scheduled audit export manager.

Provides automated scheduling for audit exports with support for
daily, weekly, and monthly frequencies.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from iatb.core.exceptions import ConfigError
from iatb.storage.audit_exporter import (
    AuditExporter,
    ScheduleFrequency,
)

if TYPE_CHECKING:
    pass


class ScheduleStatus(str, Enum):
    """Status of scheduled export execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ScheduleConfig:
    """Configuration for scheduled export."""

    frequency: ScheduleFrequency
    time: time = time(hour=23, minute=59)
    day_of_week: int = 4  # Friday (0=Monday, 6=Sunday)
    day_of_month: int = 1  # 1st of month
    enabled: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.day_of_week <= 6:
            msg = "day_of_week must be between 0 and 6"
            raise ConfigError(msg)
        if not 1 <= self.day_of_month <= 31:
            msg = "day_of_month must be between 1 and 31"
            raise ConfigError(msg)


@dataclass(frozen=True)
class ScheduleExecution:
    """Record of a scheduled export execution."""

    schedule_id: str
    status: ScheduleStatus
    timestamp: datetime
    records_exported: int
    file_path: Path | None
    error_message: str | None = None


class AuditExportScheduler:
    """Manager for scheduled audit exports."""

    def __init__(
        self,
        exporter: AuditExporter,
        schedule_config: ScheduleConfig,
        state_file: Path | None = None,
    ) -> None:
        """Initialize scheduler with exporter and schedule configuration."""
        self._exporter = exporter
        self._config = schedule_config
        self._state_file = state_file

        if state_file:
            state_file.parent.mkdir(parents=True, exist_ok=True)

    def is_due(self, reference_time: datetime | None = None) -> bool:
        """Check if scheduled export is due based on current time."""
        if not self._config.enabled:
            return False

        now = reference_time or datetime.now(UTC)

        if self._config.frequency == ScheduleFrequency.DAILY:
            return self._is_daily_due(now)
        elif self._config.frequency == ScheduleFrequency.WEEKLY:
            return self._is_weekly_due(now)
        else:  # noqa: RET505
            # ScheduleFrequency.MONTHLY is the only remaining case
            return self._is_monthly_due(now)

    def execute(self) -> ScheduleExecution:
        """Execute scheduled export and record result."""
        execution_timestamp = datetime.now(UTC)

        if not self._config.enabled:
            execution = ScheduleExecution(
                schedule_id=self._generate_schedule_id(execution_timestamp),
                status=ScheduleStatus.SKIPPED,
                timestamp=execution_timestamp,
                records_exported=0,
                file_path=None,
                error_message="Schedule is disabled",
            )
            self._save_execution(execution)
            return execution

        if not self.is_due():
            execution = ScheduleExecution(
                schedule_id=self._generate_schedule_id(execution_timestamp),
                status=ScheduleStatus.SKIPPED,
                timestamp=execution_timestamp,
                records_exported=0,
                file_path=None,
                error_message="Export not due at this time",
            )
            self._save_execution(execution)
            return execution

        try:
            result = self._exporter.export()

            if result.success:
                execution = ScheduleExecution(
                    schedule_id=self._generate_schedule_id(result.timestamp),
                    status=ScheduleStatus.SUCCESS,
                    timestamp=result.timestamp,
                    records_exported=result.records_exported,
                    file_path=result.file_path,
                    error_message=None,
                )
            else:
                execution = ScheduleExecution(
                    schedule_id=self._generate_schedule_id(result.timestamp),
                    status=ScheduleStatus.FAILED,
                    timestamp=result.timestamp,
                    records_exported=0,
                    file_path=None,
                    error_message=result.error_message,
                )
        except Exception as exc:
            execution = ScheduleExecution(
                schedule_id=self._generate_schedule_id(execution_timestamp),
                status=ScheduleStatus.FAILED,
                timestamp=execution_timestamp,
                records_exported=0,
                file_path=None,
                error_message=str(exc),
            )

        self._save_execution(execution)
        return execution

    def get_last_execution(self) -> ScheduleExecution | None:
        """Retrieve the last execution record from state file."""
        if not self._state_file or not self._state_file.exists():
            return None

        try:
            with self._state_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return ScheduleExecution(
                    schedule_id=data["schedule_id"],
                    status=ScheduleStatus(data["status"]),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    records_exported=data["records_exported"],
                    file_path=Path(data["file_path"]) if data.get("file_path") else None,
                    error_message=data.get("error_message"),
                )
        except Exception:
            return None

    def _is_daily_due(self, now: datetime) -> bool:
        """Check if daily export is due."""
        scheduled_time = datetime.combine(
            now.date(),
            self._config.time,
            tzinfo=now.tzinfo,
        )

        last_execution = self.get_last_execution()

        if last_execution is None:
            return now >= scheduled_time

        return (
            now >= scheduled_time
            and last_execution.timestamp.astimezone(now.tzinfo).date() < now.date()
        )

    def _is_weekly_due(self, now: datetime) -> bool:
        """Check if weekly export is due."""
        if now.weekday() != self._config.day_of_week:
            return False

        scheduled_time = datetime.combine(
            now.date(),
            self._config.time,
            tzinfo=now.tzinfo,
        )

        last_execution = self.get_last_execution()

        if last_execution is None:
            return now >= scheduled_time

        last_exec_time = last_execution.timestamp.astimezone(now.tzinfo)
        days_since_last = (now.date() - last_exec_time.date()).days

        return now >= scheduled_time and days_since_last >= 7

    def _is_monthly_due(self, now: datetime) -> bool:
        """Check if monthly export is due."""
        if now.day != self._config.day_of_month:
            return False

        scheduled_time = datetime.combine(
            now.date(),
            self._config.time,
            tzinfo=now.tzinfo,
        )

        last_execution = self.get_last_execution()

        if last_execution is None:
            return now >= scheduled_time

        last_exec_time = last_execution.timestamp.astimezone(now.tzinfo)
        months_since_last = (now.year - last_exec_time.year) * 12 + (
            now.month - last_exec_time.month
        )

        return now >= scheduled_time and months_since_last >= 1

    def _generate_schedule_id(self, timestamp: datetime | None = None) -> str:
        """Generate unique schedule execution ID."""
        ts = timestamp or datetime.now(UTC)
        return f"{self._config.frequency.value}_{ts.strftime('%Y%m%d_%H%M%S')}"

    def _save_execution(self, execution: ScheduleExecution) -> None:
        """Save execution record to state file."""
        if not self._state_file:
            return

        data = {
            "schedule_id": execution.schedule_id,
            "status": execution.status.value,
            "timestamp": execution.timestamp.isoformat(),
            "records_exported": execution.records_exported,
            "file_path": str(execution.file_path) if execution.file_path else None,
            "error_message": execution.error_message,
        }

        with self._state_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
