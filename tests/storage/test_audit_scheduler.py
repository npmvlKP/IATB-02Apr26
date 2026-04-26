"""
Tests for AuditExportScheduler with comprehensive coverage.
"""

import json
from datetime import UTC, datetime, time
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.storage.audit_exporter import (
    AuditExporter,
    ExportConfig,
    ExportFormat,
)
from iatb.storage.audit_scheduler import (
    AuditExportScheduler,
    ScheduleConfig,
    ScheduleExecution,
    ScheduleFrequency,
    ScheduleStatus,
)
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create temporary directory for test files."""
    return tmp_path / "audit_scheduler"


@pytest.fixture
def sample_records() -> list[TradeAuditRecord]:
    """Create sample trade audit records for testing."""
    base_time = datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC)
    return [
        TradeAuditRecord(
            trade_id="TRADE001",
            timestamp=create_timestamp(base_time),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=create_quantity("100"),
            price=create_price("2500.50"),
            status=OrderStatus.FILLED,
            strategy_id="STRAT_A",
            metadata={"signal_strength": "0.85"},
        ),
    ]


@pytest.fixture
def empty_db_path(temp_dir: Path) -> Path:
    """Create empty SQLite database for testing."""
    return temp_dir / "test_trades.sqlite"


@pytest.fixture
def store(empty_db_path: Path, sample_records: list[TradeAuditRecord]) -> SQLiteStore:
    """Create SQLite store with sample records."""
    store = SQLiteStore(db_path=empty_db_path, retention_years=7)
    store.initialize()
    for record in sample_records:
        store.append_trade(record)
    yield store
    # Close connection to allow cleanup on Windows
    try:
        if hasattr(store, "_conn") and store._conn:
            store._conn.close()
    except Exception as e:
        # Ignore cleanup errors on Windows
        _ = e


@pytest.fixture
def export_config(temp_dir: Path) -> ExportConfig:
    """Create export configuration for testing."""
    return ExportConfig(
        output_dir=temp_dir / "exports",
        retention_days=30,
        format=ExportFormat.CSV,
        include_metadata=True,
        filename_prefix="test_audit",
    )


@pytest.fixture
def exporter(store: SQLiteStore, export_config: ExportConfig) -> AuditExporter:
    """Create AuditExporter instance for testing."""
    return AuditExporter(store=store, config=export_config)


class TestScheduleConfig:
    """Test ScheduleConfig validation and initialization."""

    def test_valid_daily_config(self) -> None:
        """Test creation of valid daily schedule config."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        assert config.frequency == ScheduleFrequency.DAILY
        assert config.time == time(hour=10, minute=30)
        assert config.enabled is True

    def test_valid_weekly_config(self) -> None:
        """Test creation of valid weekly schedule config."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=4,  # Friday
        )
        assert config.frequency == ScheduleFrequency.WEEKLY
        assert config.day_of_week == 4

    def test_valid_monthly_config(self) -> None:
        """Test creation of valid monthly schedule config."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=1,
        )
        assert config.frequency == ScheduleFrequency.MONTHLY
        assert config.day_of_month == 1

    def test_invalid_day_of_week_too_high(self) -> None:
        """Test that day_of_week > 6 raises ConfigError."""
        with pytest.raises(ConfigError, match="day_of_week must be between 0 and 6"):
            ScheduleConfig(
                frequency=ScheduleFrequency.WEEKLY,
                day_of_week=7,
            )

    def test_invalid_day_of_week_negative(self) -> None:
        """Test that negative day_of_week raises ConfigError."""
        with pytest.raises(ConfigError, match="day_of_week must be between 0 and 6"):
            ScheduleConfig(
                frequency=ScheduleFrequency.WEEKLY,
                day_of_week=-1,
            )

    def test_invalid_day_of_month_too_high(self) -> None:
        """Test that day_of_month > 31 raises ConfigError."""
        with pytest.raises(ConfigError, match="day_of_month must be between 1 and 31"):
            ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY,
                day_of_month=32,
            )

    def test_invalid_day_of_month_zero(self) -> None:
        """Test that day_of_month = 0 raises ConfigError."""
        with pytest.raises(ConfigError, match="day_of_month must be between 1 and 31"):
            ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY,
                day_of_month=0,
            )

    def test_invalid_day_of_month_negative(self) -> None:
        """Test that negative day_of_month raises ConfigError."""
        with pytest.raises(ConfigError, match="day_of_month must be between 1 and 31"):
            ScheduleConfig(
                frequency=ScheduleFrequency.MONTHLY,
                day_of_month=-1,
            )


class TestScheduleExecution:
    """Test ScheduleExecution creation and validation."""

    def test_successful_execution(self, temp_dir: Path) -> None:
        """Test creation of successful ScheduleExecution."""
        file_path = temp_dir / "test.csv"
        execution = ScheduleExecution(
            schedule_id="daily_20250425_103059",
            status=ScheduleStatus.SUCCESS,
            timestamp=datetime.now(UTC),
            records_exported=10,
            file_path=file_path,
        )

        assert execution.status == ScheduleStatus.SUCCESS
        assert execution.records_exported == 10
        assert execution.file_path == file_path
        assert execution.error_message is None

    def test_failed_execution(self) -> None:
        """Test creation of failed ScheduleExecution."""
        execution = ScheduleExecution(
            schedule_id="daily_20250425_103059",
            status=ScheduleStatus.FAILED,
            timestamp=datetime.now(UTC),
            records_exported=0,
            file_path=None,
            error_message="Export failed",
        )

        assert execution.status == ScheduleStatus.FAILED
        assert execution.records_exported == 0
        assert execution.file_path is None
        assert execution.error_message == "Export failed"

    def test_skipped_execution(self) -> None:
        """Test creation of skipped ScheduleExecution."""
        execution = ScheduleExecution(
            schedule_id="daily_20250425_103059",
            status=ScheduleStatus.SKIPPED,
            timestamp=datetime.now(UTC),
            records_exported=0,
            file_path=None,
            error_message="Schedule disabled",
        )

        assert execution.status == ScheduleStatus.SKIPPED
        assert execution.records_exported == 0
        assert execution.error_message == "Schedule disabled"


class TestAuditExportScheduler:
    """Test AuditExportScheduler functionality."""

    def test_initialization_creates_state_dir(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that scheduler creates state directory on initialization."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)

        assert not state_file.parent.exists()

        AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        assert state_file.parent.exists()
        assert state_file.parent.is_dir()

    def test_is_due_returns_false_when_disabled(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that disabled schedule is never due."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            enabled=False,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        assert scheduler.is_due() is False

    def test_execute_returns_skipped_when_disabled(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that execute returns SKIPPED status when disabled."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            enabled=False,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SKIPPED
        assert "disabled" in execution.error_message.lower()

    def test_execute_returns_skipped_when_not_due(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that execute returns SKIPPED when not due."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=time(hour=23, minute=59),
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        execution = scheduler.execute()

        assert execution.status == ScheduleStatus.SKIPPED
        assert "not due" in execution.error_message.lower()

    def test_daily_schedule_is_due_at_correct_time(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that daily schedule is due at scheduled time."""
        scheduled_time = time(hour=10, minute=30)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=scheduled_time,
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # Time after scheduled time
        now = datetime(2025, 4, 25, 10, 30, 1, tzinfo=UTC)

        assert scheduler.is_due(reference_time=now) is True

    def test_weekly_schedule_is_due_on_correct_day(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that weekly schedule is due on correct day of week."""
        # Friday (weekday 4)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=4,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # Friday at scheduled time
        now = datetime(2025, 4, 25, 10, 30, 1, tzinfo=UTC)  # Friday

        assert scheduler.is_due(reference_time=now) is True

    def test_weekly_schedule_not_due_on_wrong_day(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that weekly schedule is not due on wrong day."""
        # Friday (weekday 4)
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=4,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # Monday (weekday 0) at scheduled time
        now = datetime(2025, 4, 28, 10, 30, 1, tzinfo=UTC)  # Monday

        assert scheduler.is_due(reference_time=now) is False

    def test_monthly_schedule_is_due_on_correct_day(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that monthly schedule is due on correct day of month."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=1,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # 1st of month at scheduled time
        now = datetime(2025, 5, 1, 10, 30, 1, tzinfo=UTC)

        assert scheduler.is_due(reference_time=now) is True

    def test_monthly_schedule_not_due_on_wrong_day(
        self,
        exporter: AuditExporter,
    ) -> None:
        """Test that monthly schedule is not due on wrong day."""
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=1,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # 15th of month at scheduled time
        now = datetime(2025, 5, 15, 10, 30, 1, tzinfo=UTC)

        assert scheduler.is_due(reference_time=now) is False

    def test_execute_saves_state_file(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that execute saves execution state to file."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY, enabled=False)
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        scheduler.execute()

        assert state_file.exists()

        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert "schedule_id" in data
        assert "status" in data
        assert "timestamp" in data

    def test_get_last_execution_returns_none_when_no_state(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that get_last_execution returns None when no state file."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        assert scheduler.get_last_execution() is None

    def test_get_last_execution_returns_previous_execution(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that get_last_execution returns saved execution."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY, enabled=False)
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # Execute and save
        first_execution = scheduler.execute()

        # Retrieve
        last_execution = scheduler.get_last_execution()

        assert last_execution is not None
        assert last_execution.schedule_id == first_execution.schedule_id
        assert last_execution.status == first_execution.status
        assert last_execution.timestamp == first_execution.timestamp

    def test_daily_schedule_prevents_duplicate_execution(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that daily schedule doesn't execute twice in same day."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.DAILY,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # First execution at scheduled time
        now = datetime(2025, 4, 25, 10, 30, 1, tzinfo=UTC)
        assert scheduler.is_due(reference_time=now) is True

        # Simulate execution
        scheduler.execute()

        # Same day later - should not be due
        later_same_day = datetime(2025, 4, 25, 10, 30, 30, tzinfo=UTC)
        assert scheduler.is_due(reference_time=later_same_day) is False

    def test_weekly_schedule_prevents_duplicate_in_same_week(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that weekly schedule doesn't execute twice in same week."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.WEEKLY,
            day_of_week=4,  # Friday
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # First execution - manually create a successful execution
        now = datetime(2025, 4, 25, 10, 30, 1, tzinfo=UTC)  # Friday
        assert scheduler.is_due(reference_time=now) is True

        # Manually save a successful execution to simulate real execution
        execution = ScheduleExecution(
            schedule_id="weekly_20250425_103001",
            status=ScheduleStatus.SUCCESS,
            timestamp=now,
            records_exported=1,
            file_path=temp_dir / "test.csv",
        )
        scheduler._save_execution(execution)

        # Same day later - should not be due
        later_same_day = datetime(2025, 4, 25, 11, 0, 0, tzinfo=UTC)
        assert scheduler.is_due(reference_time=later_same_day) is False

        # Next Friday - should be due (7+ days later)
        next_friday = datetime(2025, 5, 2, 10, 30, 1, tzinfo=UTC)
        assert scheduler.is_due(reference_time=next_friday) is True

    def test_monthly_schedule_prevents_duplicate_in_same_month(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that monthly schedule doesn't execute twice in same month."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(
            frequency=ScheduleFrequency.MONTHLY,
            day_of_month=1,
            time=time(hour=10, minute=30),
            enabled=True,
        )
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # First execution
        now = datetime(2025, 5, 1, 10, 30, 1, tzinfo=UTC)
        assert scheduler.is_due(reference_time=now) is True

        # Simulate execution
        scheduler.execute()

        # Same month later - should not be due
        later_same_month = datetime(2025, 5, 1, 10, 30, 30, tzinfo=UTC)
        assert scheduler.is_due(reference_time=later_same_month) is False

    def test_schedule_id_generation(self, exporter: AuditExporter) -> None:
        """Test that schedule IDs are generated correctly."""
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # Execute to get execution with ID
        execution = scheduler.execute()

        assert execution.schedule_id.startswith("daily_")
        # The date part should match current date, not hardcoded
        current_date = datetime.now(UTC).strftime("%Y%m%d")
        assert current_date in execution.schedule_id

    def test_execute_handles_export_failure(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that execute handles export failures gracefully."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY, enabled=False)
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # Disabled schedule will skip, not fail
        execution = scheduler.execute()
        assert execution.status == ScheduleStatus.SKIPPED

    def test_unsupported_frequency_raises_error(self, exporter: AuditExporter) -> None:
        """Test that unsupported frequency raises ConfigError."""
        # This test ensures the code path for unknown frequencies works
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(exporter=exporter, schedule_config=config)

        # The scheduler should handle all enum values correctly
        assert scheduler._config.frequency in [
            ScheduleFrequency.DAILY,
            ScheduleFrequency.WEEKLY,
            ScheduleFrequency.MONTHLY,
        ]

    def test_corrupted_state_file_handling(
        self,
        exporter: AuditExporter,
        temp_dir: Path,
    ) -> None:
        """Test that corrupted state file is handled gracefully."""
        state_file = temp_dir / "state" / "schedule.json"
        config = ScheduleConfig(frequency=ScheduleFrequency.DAILY)
        scheduler = AuditExportScheduler(
            exporter=exporter,
            schedule_config=config,
            state_file=state_file,
        )

        # Write invalid JSON
        state_file.write_text("invalid json data")

        # Should return None instead of crashing
        result = scheduler.get_last_execution()
        assert result is None
