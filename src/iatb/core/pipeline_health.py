"""
Pipeline health monitor for IATB trading pipeline.

Tracks timing, success/failure, and health of each pipeline stage,
enabling observability, diagnostics, and alerting for the full
scan-to-trade lifecycle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from iatb.core.exceptions import ConfigError

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class PipelineStage(StrEnum):
    """Enumeration of pipeline stages in execution order."""

    INIT = "INIT"
    ML_READINESS = "ML_READINESS"
    DATA_FETCH = "DATA_FETCH"
    SENTIMENT = "SENTIMENT"
    STRENGTH = "STRENGTH"
    SCAN = "SCAN"
    TRADE_EXECUTION = "TRADE_EXECUTION"
    AUDIT = "AUDIT"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class StageResult:
    """Immutable record of a single pipeline stage execution."""

    stage: PipelineStage
    success: bool
    duration_ms: int
    timestamp_utc: datetime
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineSnapshot:
    """Point-in-time snapshot of pipeline health."""

    pipeline_id: str
    started_at_utc: datetime
    stages_completed: list[PipelineStage]
    current_stage: PipelineStage | None
    total_duration_ms: int
    error_count: int
    is_healthy: bool
    stage_results: list[StageResult]


class PipelineHealthMonitor:
    """Tracks health, timing, and errors across pipeline stages.

    Thread-safe for single-pipeline use. Each pipeline run should
    create its own monitor instance via ``start_run()``.
    """

    def __init__(
        self,
        *,
        max_history: int = 100,
        unhealthy_threshold: int = 3,
    ) -> None:
        if max_history <= 0:
            msg = "max_history must be positive"
            raise ConfigError(msg)
        if unhealthy_threshold <= 0:
            msg = "unhealthy_threshold must be positive"
            raise ConfigError(msg)

        self._max_history = max_history
        self._unhealthy_threshold = unhealthy_threshold
        self._run_history: list[PipelineSnapshot] = []

    def start_run(self, pipeline_id: str) -> PipelineRun:
        """Create a new tracked pipeline run.

        Args:
            pipeline_id: Unique identifier for this pipeline run.

        Returns:
            PipelineRun instance for tracking stage execution.
        """
        return PipelineRun(
            pipeline_id=pipeline_id,
            monitor=self,
        )

    def record_run(self, snapshot: PipelineSnapshot) -> None:
        """Record a completed pipeline run snapshot.

        Maintains bounded history by dropping oldest entries.

        Args:
            snapshot: Completed pipeline snapshot to record.
        """
        self._run_history.append(snapshot)
        if len(self._run_history) > self._max_history:
            self._run_history = self._run_history[-self._max_history :]

    def get_run_history(self) -> list[PipelineSnapshot]:
        """Get list of recorded pipeline run snapshots."""
        return list(self._run_history)

    def get_latest_run(self) -> PipelineSnapshot | None:
        """Get the most recent pipeline run snapshot."""
        return self._run_history[-1] if self._run_history else None

    def get_consecutive_failures(self) -> int:
        """Count consecutive failed runs from most recent."""
        count = 0
        for snapshot in reversed(self._run_history):
            if snapshot.error_count > 0:
                count += 1
            else:
                break
        return count

    def is_healthy(self) -> bool:
        """Determine overall pipeline health.

        Returns:
            False if consecutive failures exceed threshold.
        """
        return self.get_consecutive_failures() < self._unhealthy_threshold

    def get_stage_stats(self, stage: PipelineStage) -> dict[str, Any]:
        """Compute aggregate statistics for a specific stage.

        Args:
            stage: Pipeline stage to compute stats for.

        Returns:
            Dictionary with avg_duration_ms, success_rate, total_runs.
        """
        durations: list[int] = []
        successes = 0
        total = 0

        for snapshot in self._run_history:
            for result in snapshot.stage_results:
                if result.stage == stage:
                    total += 1
                    durations.append(result.duration_ms)
                    if result.success:
                        successes += 1

        if total == 0:
            return {
                "avg_duration_ms": 0,
                "success_rate": Decimal("0"),
                "total_runs": 0,
            }

        avg_duration = sum(durations) // len(durations)
        success_rate = (Decimal(str(successes)) / Decimal(str(total))) * Decimal("100")

        return {
            "avg_duration_ms": avg_duration,
            "success_rate": success_rate,
            "total_runs": total,
        }


class PipelineRun:
    """Tracks a single pipeline run execution.

    Created via ``PipelineHealthMonitor.start_run()``. Call
    ``record_stage()`` at each stage completion and ``finish()``
    when the pipeline ends.
    """

    def __init__(
        self,
        pipeline_id: str,
        monitor: PipelineHealthMonitor,
    ) -> None:
        self._pipeline_id = pipeline_id
        self._monitor = monitor
        self._started_at_utc = datetime.now(UTC)
        self._stage_results: list[StageResult] = []
        self._completed_stages: list[PipelineStage] = []
        self._current_stage: PipelineStage | None = None
        self._finished = False

    @property
    def pipeline_id(self) -> str:
        return self._pipeline_id

    @property
    def current_stage(self) -> PipelineStage | None:
        return self._current_stage

    @property
    def stages_completed(self) -> list[PipelineStage]:
        return list(self._completed_stages)

    def record_stage(
        self,
        stage: PipelineStage,
        success: bool,
        duration_ms: int,
        error: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StageResult:
        """Record completion of a pipeline stage.

        Args:
            stage: The pipeline stage that completed.
            success: Whether the stage succeeded.
            duration_ms: Duration in milliseconds.
            error: Optional error message if stage failed.
            metadata: Optional stage-specific metadata.

        Returns:
            Immutable StageResult recording this stage execution.
        """
        result = StageResult(
            stage=stage,
            success=success,
            duration_ms=duration_ms,
            timestamp_utc=datetime.now(UTC),
            error=error,
            metadata=metadata or {},
        )

        self._stage_results.append(result)
        if success:
            self._completed_stages.append(stage)
        self._current_stage = stage

        _LOGGER.debug(
            "Pipeline %s stage %s: success=%s duration=%dms",
            self._pipeline_id,
            stage.value,
            success,
            duration_ms,
        )

        return result

    def get_snapshot(self) -> PipelineSnapshot:
        """Create a snapshot of current pipeline state.

        Returns:
            PipelineSnapshot capturing current state.
        """
        total_ms = sum(r.duration_ms for r in self._stage_results)
        error_count = sum(1 for r in self._stage_results if not r.success)

        return PipelineSnapshot(
            pipeline_id=self._pipeline_id,
            started_at_utc=self._started_at_utc,
            stages_completed=list(self._completed_stages),
            current_stage=self._current_stage,
            total_duration_ms=total_ms,
            error_count=error_count,
            is_healthy=error_count == 0,
            stage_results=list(self._stage_results),
        )

    def finish(self) -> PipelineSnapshot:
        """Finalize the pipeline run and record in monitor history.

        Returns:
            Final PipelineSnapshot of the completed run.

        Raises:
            ConfigError: If called more than once.
        """
        if self._finished:
            msg = f"Pipeline run {self._pipeline_id} already finished"
            raise ConfigError(msg)

        snapshot = self.get_snapshot()
        self._monitor.record_run(snapshot)
        self._finished = True

        _LOGGER.info(
            "Pipeline %s completed: %d stages, %d errors, %dms",
            self._pipeline_id,
            len(self._completed_stages),
            snapshot.error_count,
            snapshot.total_duration_ms,
        )

        return snapshot


class PipelineStageTimer:
    """Context manager for timing pipeline stage execution.

    Usage::

        run = monitor.start_run("cycle-001")
        with PipelineStageTimer(run, PipelineStage.SCAN) as timer:
            scanner_result = scanner.scan()
        # timer.result available after block
    """

    def __init__(
        self,
        pipeline_run: PipelineRun,
        stage: PipelineStage,
    ) -> None:
        self._run = pipeline_run
        self._stage = stage
        self._start_time: datetime | None = None
        self.result: StageResult | None = None

    def __enter__(self) -> PipelineStageTimer:
        self._start_time = datetime.now(UTC)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        if self._start_time is None:
            return False

        if self.result is not None:
            return False

        end_time = datetime.now(UTC)
        duration_ms = int((end_time - self._start_time).total_seconds() * 1000)
        success = exc_type is None
        error = str(exc_val) if exc_val else None

        self.result = self._run.record_stage(
            stage=self._stage,
            success=success,
            duration_ms=duration_ms,
            error=error,
        )

        return False

    def mark_success(self, metadata: dict[str, str] | None = None) -> StageResult:
        """Explicitly mark stage as successful with optional metadata.

        Args:
            metadata: Optional metadata dict to attach.

        Returns:
            StageResult for this successful stage.
        """
        if self._start_time is None:
            msg = "Timer not started"
            raise ConfigError(msg)

        end_time = datetime.now(UTC)
        duration_ms = int((end_time - self._start_time).total_seconds() * 1000)

        self.result = self._run.record_stage(
            stage=self._stage,
            success=True,
            duration_ms=duration_ms,
            metadata=metadata,
        )
        return self.result

    def mark_failure(self, error: str, metadata: dict[str, str] | None = None) -> StageResult:
        """Explicitly mark stage as failed with error message.

        Args:
            error: Error description.
            metadata: Optional metadata dict to attach.

        Returns:
            StageResult for this failed stage.
        """
        if self._start_time is None:
            msg = "Timer not started"
            raise ConfigError(msg)

        end_time = datetime.now(UTC)
        duration_ms = int((end_time - self._start_time).total_seconds() * 1000)

        self.result = self._run.record_stage(
            stage=self._stage,
            success=False,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata,
        )
        return self.result
