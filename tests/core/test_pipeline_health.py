"""
Tests for Phase H - Pipeline Integration Hardening.

Covers:
- PipelineHealthMonitor: stage tracking, health aggregation, statistics
- PipelineRun: stage recording, snapshots, finish lifecycle
- PipelineStageTimer: context manager timing, success/failure marking
- PipelineCheckpoint: save/load/delete/cleanup lifecycle
- CheckpointData: serialization/deserialization round-trip
- Integration: health monitor wired into scan_cycle
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.pipeline_checkpoint import (
    CheckpointData,
    PipelineCheckpoint,
    create_checkpoint_from_stages,
)
from iatb.core.pipeline_health import (
    PipelineHealthMonitor,
    PipelineRun,
    PipelineSnapshot,
    PipelineStage,
    PipelineStageTimer,
    StageResult,
)


class TestPipelineStage:
    """Test PipelineStage enum."""

    def test_all_stages_defined(self) -> None:
        expected = [
            "INIT",
            "ML_READINESS",
            "DATA_FETCH",
            "SENTIMENT",
            "STRENGTH",
            "SCAN",
            "TRADE_EXECUTION",
            "AUDIT",
            "COMPLETE",
        ]
        values = [s.value for s in PipelineStage]
        for stage in expected:
            assert stage in values

    def test_stage_is_string_enum(self) -> None:
        assert isinstance(PipelineStage.INIT, str)
        assert PipelineStage.INIT == "INIT"


class TestStageResult:
    """Test StageResult immutable dataclass."""

    def test_create_successful_result(self) -> None:
        now = datetime.now(UTC)
        result = StageResult(
            stage=PipelineStage.SCAN,
            success=True,
            duration_ms=150,
            timestamp_utc=now,
        )
        assert result.stage == PipelineStage.SCAN
        assert result.success is True
        assert result.duration_ms == 150
        assert result.error is None
        assert result.metadata == {}

    def test_create_failed_result(self) -> None:
        now = datetime.now(UTC)
        result = StageResult(
            stage=PipelineStage.DATA_FETCH,
            success=False,
            duration_ms=2000,
            timestamp_utc=now,
            error="Connection timeout",
            metadata={"provider": "kite"},
        )
        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.metadata["provider"] == "kite"

    def test_result_is_frozen(self) -> None:
        result = StageResult(
            stage=PipelineStage.INIT,
            success=True,
            duration_ms=10,
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            result.success = False


class TestPipelineRun:
    """Test PipelineRun lifecycle."""

    def _create_monitor(self) -> PipelineHealthMonitor:
        return PipelineHealthMonitor()

    def test_record_successful_stage(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-001")

        result = run.record_stage(PipelineStage.INIT, success=True, duration_ms=50)

        assert result.stage == PipelineStage.INIT
        assert result.success is True
        assert run.current_stage == PipelineStage.INIT
        assert PipelineStage.INIT in run.stages_completed

    def test_record_failed_stage_not_in_completed(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-002")

        run.record_stage(PipelineStage.DATA_FETCH, success=False, duration_ms=100, error="fail")

        assert run.current_stage == PipelineStage.DATA_FETCH
        assert PipelineStage.DATA_FETCH not in run.stages_completed

    def test_multiple_stages_recorded(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-003")

        run.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        run.record_stage(PipelineStage.ML_READINESS, success=True, duration_ms=20)
        run.record_stage(PipelineStage.DATA_FETCH, success=True, duration_ms=30)

        assert len(run.stages_completed) == 3
        assert run.current_stage == PipelineStage.DATA_FETCH

    def test_get_snapshot(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-004")

        run.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        run.record_stage(PipelineStage.SCAN, success=False, duration_ms=50, error="err")

        snapshot = run.get_snapshot()

        assert snapshot.pipeline_id == "test-004"
        assert len(snapshot.stages_completed) == 1
        assert snapshot.error_count == 1
        assert snapshot.total_duration_ms == 60
        assert snapshot.is_healthy is False

    def test_finish_records_in_monitor(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-005")

        run.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        snapshot = run.finish()

        assert snapshot.pipeline_id == "test-005"
        assert monitor.get_latest_run() is snapshot

    def test_finish_twice_raises(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("test-006")
        run.finish()

        with pytest.raises(ConfigError, match="already finished"):
            run.finish()

    def test_pipeline_id_property(self) -> None:
        monitor = self._create_monitor()
        run = monitor.start_run("my-pipeline")
        assert run.pipeline_id == "my-pipeline"


class TestPipelineHealthMonitor:
    """Test PipelineHealthMonitor aggregate tracking."""

    def test_run_history_bounded(self) -> None:
        monitor = PipelineHealthMonitor(max_history=3)

        for i in range(5):
            run = monitor.start_run(f"run-{i}")
            run.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
            run.finish()

        history = monitor.get_run_history()
        assert len(history) == 3

    def test_latest_run(self) -> None:
        monitor = PipelineHealthMonitor()

        run1 = monitor.start_run("first")
        run1.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        run1.finish()

        run2 = monitor.start_run("second")
        run2.record_stage(PipelineStage.INIT, success=True, duration_ms=20)
        run2.finish()

        latest = monitor.get_latest_run()
        assert latest is not None
        assert latest.pipeline_id == "second"

    def test_latest_run_none_when_empty(self) -> None:
        monitor = PipelineHealthMonitor()
        assert monitor.get_latest_run() is None

    def test_consecutive_failures(self) -> None:
        monitor = PipelineHealthMonitor()

        run1 = monitor.start_run("ok")
        run1.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        run1.finish()

        for i in range(3):
            run = monitor.start_run(f"fail-{i}")
            run.record_stage(PipelineStage.SCAN, success=False, duration_ms=10, error="x")
            run.finish()

        assert monitor.get_consecutive_failures() == 3

    def test_consecutive_failures_reset_by_success(self) -> None:
        monitor = PipelineHealthMonitor()

        run_fail = monitor.start_run("f")
        run_fail.record_stage(PipelineStage.SCAN, success=False, duration_ms=10, error="x")
        run_fail.finish()

        run_ok = monitor.start_run("ok")
        run_ok.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
        run_ok.finish()

        assert monitor.get_consecutive_failures() == 0

    def test_is_healthy_below_threshold(self) -> None:
        monitor = PipelineHealthMonitor(unhealthy_threshold=3)

        for i in range(2):
            run = monitor.start_run(f"f-{i}")
            run.record_stage(PipelineStage.SCAN, success=False, duration_ms=10, error="x")
            run.finish()

        assert monitor.is_healthy() is True

    def test_is_unhealthy_at_threshold(self) -> None:
        monitor = PipelineHealthMonitor(unhealthy_threshold=2)

        for i in range(2):
            run = monitor.start_run(f"f-{i}")
            run.record_stage(PipelineStage.SCAN, success=False, duration_ms=10, error="x")
            run.finish()

        assert monitor.is_healthy() is False

    def test_stage_stats(self) -> None:
        monitor = PipelineHealthMonitor()

        run1 = monitor.start_run("s1")
        run1.record_stage(PipelineStage.SCAN, success=True, duration_ms=100)
        run1.finish()

        run2 = monitor.start_run("s2")
        run2.record_stage(PipelineStage.SCAN, success=False, duration_ms=200, error="x")
        run2.finish()

        stats = monitor.get_stage_stats(PipelineStage.SCAN)
        assert stats["total_runs"] == 2
        assert stats["avg_duration_ms"] == 150
        assert stats["success_rate"] == Decimal("50")

    def test_stage_stats_no_data(self) -> None:
        monitor = PipelineHealthMonitor()
        stats = monitor.get_stage_stats(PipelineStage.AUDIT)
        assert stats["total_runs"] == 0
        assert stats["avg_duration_ms"] == 0

    def test_invalid_max_history(self) -> None:
        with pytest.raises(ConfigError, match="max_history"):
            PipelineHealthMonitor(max_history=0)

    def test_invalid_unhealthy_threshold(self) -> None:
        with pytest.raises(ConfigError, match="unhealthy_threshold"):
            PipelineHealthMonitor(unhealthy_threshold=0)

    def test_history_does_not_exceed_max(self) -> None:
        monitor = PipelineHealthMonitor(max_history=5)

        for i in range(10):
            run = monitor.start_run(f"r-{i}")
            run.record_stage(PipelineStage.INIT, success=True, duration_ms=10)
            run.finish()

        assert len(monitor.get_run_history()) == 5


class TestPipelineStageTimer:
    """Test PipelineStageTimer context manager."""

    def _create_run(self) -> PipelineRun:
        monitor = PipelineHealthMonitor()
        return monitor.start_run("timer-test")

    def test_successful_stage_timing(self) -> None:
        run = self._create_run()

        with PipelineStageTimer(run, PipelineStage.INIT) as timer:
            time.sleep(0.01)

        assert timer.result is not None
        assert timer.result.success is True
        assert timer.result.duration_ms >= 10
        assert timer.result.error is None

    def test_failed_stage_timing(self) -> None:
        run = self._create_run()

        with pytest.raises(ValueError, match="scan error"):
            with PipelineStageTimer(run, PipelineStage.SCAN) as timer:
                raise ValueError("scan error")

        assert timer.result is not None
        assert timer.result.success is False
        assert "scan error" in timer.result.error

    def test_mark_success(self) -> None:
        run = self._create_run()

        with PipelineStageTimer(run, PipelineStage.DATA_FETCH) as timer:
            timer.mark_success(metadata={"rows": "100"})

        assert timer.result is not None
        assert timer.result.success is True
        assert timer.result.metadata["rows"] == "100"

    def test_mark_failure(self) -> None:
        run = self._create_run()

        with PipelineStageTimer(run, PipelineStage.SENTIMENT) as timer:
            timer.mark_failure("model load failed")

        assert timer.result is not None
        assert timer.result.success is False
        assert timer.result.error == "model load failed"

    def test_mark_without_start_raises(self) -> None:
        run = self._create_run()
        timer = PipelineStageTimer(run, PipelineStage.INIT)

        with pytest.raises(ConfigError, match="Timer not started"):
            timer.mark_success()

    def test_mark_failure_without_start_raises(self) -> None:
        run = self._create_run()
        timer = PipelineStageTimer(run, PipelineStage.INIT)

        with pytest.raises(ConfigError, match="Timer not started"):
            timer.mark_failure("err")


class TestCheckpointData:
    """Test CheckpointData serialization."""

    def test_round_trip_serialization(self) -> None:
        original = CheckpointData(
            pipeline_id="test-001",
            version=1,
            created_at_utc=datetime(2026, 4, 27, 6, 0, 0, tzinfo=UTC),
            completed_stages=[PipelineStage.INIT, PipelineStage.SCAN],
            failed_stages=[PipelineStage.SENTIMENT],
            last_successful_stage=PipelineStage.SCAN,
            metadata={"key": "value"},
            is_complete=False,
        )

        data = original.to_dict()
        restored = CheckpointData.from_dict(data)

        assert restored.pipeline_id == original.pipeline_id
        assert restored.version == original.version
        assert restored.completed_stages == original.completed_stages
        assert restored.failed_stages == original.failed_stages
        assert restored.last_successful_stage == original.last_successful_stage
        assert restored.metadata == original.metadata
        assert restored.is_complete == original.is_complete

    def test_naive_datetime_gets_utc(self) -> None:
        data = {
            "pipeline_id": "test",
            "version": 1,
            "created_at_utc": "2026-04-27T06:00:00",
            "completed_stages": [],
            "failed_stages": [],
            "last_successful_stage": None,
            "metadata": {},
            "is_complete": False,
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.created_at_utc.tzinfo is not None

    def test_invalid_data_raises(self) -> None:
        with pytest.raises(ConfigError, match="Invalid checkpoint"):
            CheckpointData.from_dict({})

    def test_invalid_stage_raises(self) -> None:
        data = {
            "pipeline_id": "test",
            "version": 1,
            "created_at_utc": "2026-04-27T06:00:00+00:00",
            "completed_stages": ["INVALID_STAGE"],
            "failed_stages": [],
            "last_successful_stage": None,
            "metadata": {},
            "is_complete": False,
        }
        with pytest.raises(ConfigError, match="Invalid checkpoint"):
            CheckpointData.from_dict(data)


class TestPipelineCheckpoint:
    """Test PipelineCheckpoint file operations."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = CheckpointData(
            pipeline_id="cycle-001",
            version=1,
            created_at_utc=datetime.now(UTC),
            completed_stages=[PipelineStage.INIT, PipelineStage.SCAN],
            failed_stages=[],
            last_successful_stage=PipelineStage.SCAN,
            metadata={},
            is_complete=False,
        )

        checkpoint_mgr.save(data)
        loaded = checkpoint_mgr.load("cycle-001")

        assert loaded is not None
        assert loaded.pipeline_id == "cycle-001"
        assert len(loaded.completed_stages) == 2

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        assert checkpoint_mgr.load("nonexistent") is None

    def test_delete(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("del-test", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        assert checkpoint_mgr.delete("del-test") is True
        assert checkpoint_mgr.load("del-test") is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        assert checkpoint_mgr.delete("nonexistent") is False

    def test_list_checkpoints(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)

        for i in range(3):
            data = create_checkpoint_from_stages(f"list-{i}", [PipelineStage.INIT], [])
            checkpoint_mgr.save(data)

        ids = checkpoint_mgr.list_checkpoints()
        assert len(ids) == 3
        assert "list-0" in ids
        assert "list-1" in ids
        assert "list-2" in ids

    def test_list_checkpoints_empty_dir(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        assert checkpoint_mgr.list_checkpoints() == []

    def test_cleanup_old(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)

        data = create_checkpoint_from_stages("old-checkpoint", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        old_file = tmp_path / "pipeline_old-checkpoint.json"
        import os

        modification_time = time.time() - 48 * 3600
        os.utime(old_file, (modification_time, modification_time))

        removed = checkpoint_mgr.cleanup_old(max_age_hours=24)
        assert removed == 1
        assert checkpoint_mgr.load("old-checkpoint") is None

    def test_cleanup_keeps_recent(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)

        data = create_checkpoint_from_stages("recent", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        removed = checkpoint_mgr.cleanup_old(max_age_hours=24)
        assert removed == 0
        assert checkpoint_mgr.load("recent") is not None

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        checkpoint_mgr = PipelineCheckpoint(nested)

        data = create_checkpoint_from_stages("nested-test", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        assert checkpoint_mgr.load("nested-test") is not None

    def test_corrupted_file_returns_none(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        corrupted = tmp_path / "pipeline_bad.json"
        corrupted.write_text("not valid json{{{{", encoding="utf-8")

        assert checkpoint_mgr.load("bad") is None

    def test_empty_checkpoint_dir_raises(self) -> None:
        with pytest.raises(ConfigError, match="checkpoint_dir"):
            PipelineCheckpoint(Path("  "))


class TestCreateCheckpointFromStages:
    """Test checkpoint factory function."""

    def test_successful_pipeline(self) -> None:
        completed = [PipelineStage.INIT, PipelineStage.SCAN, PipelineStage.COMPLETE]
        checkpoint = create_checkpoint_from_stages("ok-run", completed, [])

        assert checkpoint.pipeline_id == "ok-run"
        assert checkpoint.last_successful_stage == PipelineStage.COMPLETE
        assert checkpoint.is_complete is True

    def test_failed_pipeline(self) -> None:
        completed = [PipelineStage.INIT]
        failed = [PipelineStage.SCAN]

        checkpoint = create_checkpoint_from_stages("fail-run", completed, failed)

        assert checkpoint.is_complete is False
        assert checkpoint.failed_stages == [PipelineStage.SCAN]

    def test_empty_stages(self) -> None:
        checkpoint = create_checkpoint_from_stages("empty", [], [])
        assert checkpoint.last_successful_stage is None
        assert checkpoint.is_complete is False

    def test_with_metadata(self) -> None:
        checkpoint = create_checkpoint_from_stages(
            "meta",
            [PipelineStage.INIT],
            [],
            metadata={"env": "test"},
        )
        assert checkpoint.metadata["env"] == "test"


class TestScanCycleIntegration:
    """Test integration of health monitor with scan_cycle module."""

    def test_run_scan_cycle_has_pipeline_id(self) -> None:
        from iatb.scanner.scan_cycle import run_scan_cycle

        with patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_result.pipeline_id = None
            mock_run.return_value = mock_result

            result = run_scan_cycle()

            assert result.pipeline_id is not None
            assert result.pipeline_id.startswith("scan-")

    def test_module_health_monitor_accessible(self) -> None:
        from iatb.scanner.scan_cycle import get_pipeline_health_monitor

        monitor = get_pipeline_health_monitor()
        assert isinstance(monitor, PipelineHealthMonitor)

    def test_custom_health_monitor(self) -> None:
        from iatb.scanner.scan_cycle import run_scan_cycle

        custom_monitor = PipelineHealthMonitor()

        with patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params") as mock_run:
            mock_result = MagicMock()
            mock_result.scanner_result = None
            mock_result.trades_executed = 0
            mock_result.total_pnl = Decimal("0")
            mock_result.errors = []
            mock_result.timestamp_utc = datetime.now(UTC)
            mock_result.pipeline_id = None
            mock_run.return_value = mock_result

            run_scan_cycle(health_monitor=custom_monitor)

        latest = custom_monitor.get_latest_run()
        assert latest is not None
        assert latest.is_healthy is True

    def test_pipeline_error_still_records(self) -> None:
        from iatb.scanner.scan_cycle import run_scan_cycle

        custom_monitor = PipelineHealthMonitor()

        with patch("iatb.scanner.scan_cycle._run_scan_cycle_with_params") as mock_run:
            mock_run.side_effect = RuntimeError("pipeline crash")

            with pytest.raises(RuntimeError, match="pipeline crash"):
                run_scan_cycle(health_monitor=custom_monitor)

        latest = custom_monitor.get_latest_run()
        assert latest is not None
        assert latest.is_healthy is False


class TestPipelineSnapshot:
    """Test PipelineSnapshot dataclass."""

    def test_snapshot_fields(self) -> None:
        now = datetime.now(UTC)
        snapshot = PipelineSnapshot(
            pipeline_id="snap-001",
            started_at_utc=now,
            stages_completed=[PipelineStage.INIT],
            current_stage=PipelineStage.SCAN,
            total_duration_ms=50,
            error_count=0,
            is_healthy=True,
            stage_results=[],
        )
        assert snapshot.pipeline_id == "snap-001"
        assert snapshot.is_healthy is True

    def test_snapshot_with_errors(self) -> None:
        snapshot = PipelineSnapshot(
            pipeline_id="snap-002",
            started_at_utc=datetime.now(UTC),
            stages_completed=[],
            current_stage=PipelineStage.SCAN,
            total_duration_ms=100,
            error_count=2,
            is_healthy=False,
            stage_results=[],
        )
        assert snapshot.is_healthy is False
        assert snapshot.error_count == 2
