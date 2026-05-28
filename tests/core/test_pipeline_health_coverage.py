"""Supplemental coverage tests for pipeline health module.

Covers: PipelineStage enum values, StageResult dataclass, PipelineSnapshot dataclass,
PipelineHealthMonitor init validation, start_run, record_run with bounded history,
get_run_history, get_latest_run, get_consecutive_failures, is_healthy,
get_stage_stats, PipelineRun record_stage, get_snapshot, finish double-call error,
PipelineStageTimer context manager, mark_success, mark_failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.pipeline_health import (
    PipelineHealthMonitor,
    PipelineRun,
    PipelineSnapshot,
    PipelineStage,
    PipelineStageTimer,
    StageResult,
)


class TestPipelineStageEnum:
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
        for name in expected:
            assert hasattr(PipelineStage, name)

    def test_stage_values(self) -> None:
        assert PipelineStage.INIT == "INIT"
        assert PipelineStage.SCAN == "SCAN"
        assert PipelineStage.COMPLETE == "COMPLETE"
        assert PipelineStage.TRADE_EXECUTION == "TRADE_EXECUTION"


class TestStageResultDataclass:
    def test_frozen_immutability(self) -> None:
        result = StageResult(
            stage=PipelineStage.INIT,
            success=True,
            duration_ms=100,
            timestamp_utc=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        result = StageResult(
            stage=PipelineStage.SCAN,
            success=True,
            duration_ms=50,
            timestamp_utc=datetime.now(UTC),
        )
        assert result.error is None
        assert result.metadata == {}

    def test_with_error_and_metadata(self) -> None:
        result = StageResult(
            stage=PipelineStage.DATA_FETCH,
            success=False,
            duration_ms=200,
            timestamp_utc=datetime.now(UTC),
            error="timeout",
            metadata={"retries": "3"},
        )
        assert result.error == "timeout"
        assert result.metadata["retries"] == "3"


class TestPipelineSnapshotDataclass:
    def test_construction(self) -> None:
        snapshot = PipelineSnapshot(
            pipeline_id="test-001",
            started_at_utc=datetime.now(UTC),
            stages_completed=[PipelineStage.INIT],
            current_stage=PipelineStage.SCAN,
            total_duration_ms=150,
            error_count=0,
            is_healthy=True,
            stage_results=[],
        )
        assert snapshot.pipeline_id == "test-001"
        assert snapshot.is_healthy is True


class TestPipelineHealthMonitorInit:
    def test_invalid_max_history_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_history"):
            PipelineHealthMonitor(max_history=0)

    def test_invalid_unhealthy_threshold_raises(self) -> None:
        with pytest.raises(ConfigError, match="unhealthy_threshold"):
            PipelineHealthMonitor(unhealthy_threshold=0)

    def test_valid_init(self) -> None:
        monitor = PipelineHealthMonitor(max_history=50, unhealthy_threshold=2)
        assert monitor.get_run_history() == []
        assert monitor.get_latest_run() is None


class TestPipelineHealthMonitorStartRun:
    def test_start_run_returns_pipeline_run(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("cycle-001")
        assert isinstance(run, PipelineRun)
        assert run.pipeline_id == "cycle-001"
        assert run.current_stage is None


class TestPipelineHealthMonitorRecordRun:
    def test_record_run_maintains_bounded_history(self) -> None:
        monitor = PipelineHealthMonitor(max_history=3)
        for i in range(5):
            snapshot = PipelineSnapshot(
                pipeline_id=f"run-{i}",
                started_at_utc=datetime.now(UTC),
                stages_completed=[PipelineStage.INIT],
                current_stage=PipelineStage.COMPLETE,
                total_duration_ms=100,
                error_count=0,
                is_healthy=True,
                stage_results=[],
            )
            monitor.record_run(snapshot)
        assert len(monitor.get_run_history()) == 3

    def test_get_latest_run(self) -> None:
        monitor = PipelineHealthMonitor()
        snapshot = PipelineSnapshot(
            pipeline_id="latest",
            started_at_utc=datetime.now(UTC),
            stages_completed=[],
            current_stage=None,
            total_duration_ms=0,
            error_count=0,
            is_healthy=True,
            stage_results=[],
        )
        monitor.record_run(snapshot)
        assert monitor.get_latest_run() is not None
        assert monitor.get_latest_run().pipeline_id == "latest"

    def test_get_latest_run_empty(self) -> None:
        monitor = PipelineHealthMonitor()
        assert monitor.get_latest_run() is None


class TestPipelineHealthMonitorConsecutiveFailures:
    def test_no_failures(self) -> None:
        monitor = PipelineHealthMonitor()
        snapshot = PipelineSnapshot(
            pipeline_id="ok",
            started_at_utc=datetime.now(UTC),
            stages_completed=[PipelineStage.INIT],
            current_stage=PipelineStage.COMPLETE,
            total_duration_ms=100,
            error_count=0,
            is_healthy=True,
            stage_results=[],
        )
        monitor.record_run(snapshot)
        assert monitor.get_consecutive_failures() == 0

    def test_consecutive_failures_counted(self) -> None:
        monitor = PipelineHealthMonitor()
        for i in range(3):
            snapshot = PipelineSnapshot(
                pipeline_id=f"fail-{i}",
                started_at_utc=datetime.now(UTC),
                stages_completed=[],
                current_stage=None,
                total_duration_ms=0,
                error_count=1,
                is_healthy=False,
                stage_results=[],
            )
            monitor.record_run(snapshot)
        assert monitor.get_consecutive_failures() == 3

    def test_consecutive_stops_at_success(self) -> None:
        monitor = PipelineHealthMonitor()
        fail = PipelineSnapshot(
            pipeline_id="fail",
            started_at_utc=datetime.now(UTC),
            stages_completed=[],
            current_stage=None,
            total_duration_ms=0,
            error_count=1,
            is_healthy=False,
            stage_results=[],
        )
        ok = PipelineSnapshot(
            pipeline_id="ok",
            started_at_utc=datetime.now(UTC),
            stages_completed=[PipelineStage.INIT],
            current_stage=PipelineStage.COMPLETE,
            total_duration_ms=100,
            error_count=0,
            is_healthy=True,
            stage_results=[],
        )
        monitor.record_run(fail)
        monitor.record_run(ok)
        monitor.record_run(fail)
        assert monitor.get_consecutive_failures() == 1


class TestPipelineHealthMonitorIsHealthy:
    def test_healthy_below_threshold(self) -> None:
        monitor = PipelineHealthMonitor(unhealthy_threshold=3)
        for _ in range(2):
            snapshot = PipelineSnapshot(
                pipeline_id="fail",
                started_at_utc=datetime.now(UTC),
                stages_completed=[],
                current_stage=None,
                total_duration_ms=0,
                error_count=1,
                is_healthy=False,
                stage_results=[],
            )
            monitor.record_run(snapshot)
        assert monitor.is_healthy() is True

    def test_unhealthy_at_threshold(self) -> None:
        monitor = PipelineHealthMonitor(unhealthy_threshold=2)
        for _ in range(2):
            snapshot = PipelineSnapshot(
                pipeline_id="fail",
                started_at_utc=datetime.now(UTC),
                stages_completed=[],
                current_stage=None,
                total_duration_ms=0,
                error_count=1,
                is_healthy=False,
                stage_results=[],
            )
            monitor.record_run(snapshot)
        assert monitor.is_healthy() is False


class TestPipelineHealthMonitorGetStageStats:
    def test_no_data_returns_zeros(self) -> None:
        monitor = PipelineHealthMonitor()
        stats = monitor.get_stage_stats(PipelineStage.SCAN)
        assert stats["total_runs"] == 0
        assert stats["avg_duration_ms"] == 0
        assert stats["success_rate"] == Decimal("0")

    def test_with_data_computes_stats(self) -> None:
        monitor = PipelineHealthMonitor()
        results = [
            StageResult(
                stage=PipelineStage.SCAN,
                success=True,
                duration_ms=100,
                timestamp_utc=datetime.now(UTC),
            ),
            StageResult(
                stage=PipelineStage.SCAN,
                success=True,
                duration_ms=200,
                timestamp_utc=datetime.now(UTC),
            ),
            StageResult(
                stage=PipelineStage.SCAN,
                success=False,
                duration_ms=300,
                timestamp_utc=datetime.now(UTC),
                error="timeout",
            ),
        ]
        snapshot = PipelineSnapshot(
            pipeline_id="stats-test",
            started_at_utc=datetime.now(UTC),
            stages_completed=[PipelineStage.SCAN],
            current_stage=PipelineStage.COMPLETE,
            total_duration_ms=600,
            error_count=1,
            is_healthy=False,
            stage_results=results,
        )
        monitor.record_run(snapshot)
        stats = monitor.get_stage_stats(PipelineStage.SCAN)
        assert stats["total_runs"] == 3
        assert stats["avg_duration_ms"] == 200
        assert stats["success_rate"] == Decimal("66.66666666666666666666666667")

    def test_different_stage_excluded(self) -> None:
        monitor = PipelineHealthMonitor()
        results = [
            StageResult(
                stage=PipelineStage.INIT,
                success=True,
                duration_ms=50,
                timestamp_utc=datetime.now(UTC),
            ),
        ]
        snapshot = PipelineSnapshot(
            pipeline_id="other",
            started_at_utc=datetime.now(UTC),
            stages_completed=[PipelineStage.INIT],
            current_stage=PipelineStage.INIT,
            total_duration_ms=50,
            error_count=0,
            is_healthy=True,
            stage_results=results,
        )
        monitor.record_run(snapshot)
        stats = monitor.get_stage_stats(PipelineStage.SCAN)
        assert stats["total_runs"] == 0


class TestPipelineRunRecordStage:
    def test_successful_stage(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("run-001")
        result = run.record_stage(PipelineStage.INIT, success=True, duration_ms=100)
        assert result.success is True
        assert result.stage == PipelineStage.INIT
        assert run.current_stage == PipelineStage.INIT
        assert PipelineStage.INIT in run.stages_completed

    def test_failed_stage(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("run-002")
        result = run.record_stage(
            PipelineStage.DATA_FETCH, success=False, duration_ms=500, error="timeout"
        )
        assert result.success is False
        assert result.error == "timeout"
        assert PipelineStage.DATA_FETCH not in run.stages_completed
        assert run.current_stage == PipelineStage.DATA_FETCH

    def test_stage_with_metadata(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("run-003")
        result = run.record_stage(
            PipelineStage.SCAN, success=True, duration_ms=50, metadata={"symbols": "5"}
        )
        assert result.metadata == {"symbols": "5"}


class TestPipelineRunGetSnapshot:
    def test_snapshot_reflects_state(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("snap-001")
        run.record_stage(PipelineStage.INIT, success=True, duration_ms=100)
        run.record_stage(PipelineStage.SCAN, success=True, duration_ms=200)
        snapshot = run.get_snapshot()
        assert snapshot.pipeline_id == "snap-001"
        assert snapshot.total_duration_ms == 300
        assert snapshot.error_count == 0
        assert snapshot.is_healthy is True
        assert len(snapshot.stages_completed) == 2

    def test_snapshot_with_errors(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("snap-002")
        run.record_stage(PipelineStage.INIT, success=True, duration_ms=100)
        run.record_stage(
            PipelineStage.SENTIMENT, success=False, duration_ms=50, error="api"
        )
        snapshot = run.get_snapshot()
        assert snapshot.error_count == 1
        assert snapshot.is_healthy is False


class TestPipelineRunFinish:
    def test_finish_records_in_monitor(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("fin-001")
        run.record_stage(PipelineStage.INIT, success=True, duration_ms=100)
        snapshot = run.finish()
        assert monitor.get_latest_run() is snapshot

    def test_finish_twice_raises(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("fin-002")
        run.finish()
        with pytest.raises(ConfigError, match="already finished"):
            run.finish()


class TestPipelineStageTimer:
    def test_context_manager_success(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-001")
        with PipelineStageTimer(run, PipelineStage.SCAN) as timer:
            pass
        assert timer.result is not None
        assert timer.result.success is True
        assert timer.result.stage == PipelineStage.SCAN

    def test_context_manager_failure(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-002")
        with pytest.raises(RuntimeError, match="fetch error"):
            with PipelineStageTimer(run, PipelineStage.DATA_FETCH) as timer:
                raise RuntimeError("fetch error")
        assert timer.result is not None
        assert timer.result.success is False
        assert "fetch error" in (timer.result.error or "")

    def test_mark_success(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-003")
        with PipelineStageTimer(run, PipelineStage.STRENGTH) as timer:
            result = timer.mark_success(metadata={"score": "0.85"})
        assert result.success is True
        assert result.metadata == {"score": "0.85"}

    def test_mark_failure(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-004")
        with PipelineStageTimer(run, PipelineStage.AUDIT) as timer:
            result = timer.mark_failure("audit failed", metadata={"code": "E001"})
        assert result.success is False
        assert result.error == "audit failed"
        assert result.metadata == {"code": "E001"}

    def test_mark_success_without_start_raises(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-005")
        timer = PipelineStageTimer(run, PipelineStage.INIT)
        with pytest.raises(ConfigError, match="Timer not started"):
            timer.mark_success()

    def test_mark_failure_without_start_raises(self) -> None:
        monitor = PipelineHealthMonitor()
        run = monitor.start_run("timer-006")
        timer = PipelineStageTimer(run, PipelineStage.INIT)
        with pytest.raises(ConfigError, match="Timer not started"):
            timer.mark_failure("no start")
