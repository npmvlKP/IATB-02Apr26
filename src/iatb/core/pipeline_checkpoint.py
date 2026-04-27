"""
Pipeline checkpoint for crash recovery and state persistence.

Saves pipeline execution state after each stage, enabling resume
from the last completed stage on process restart.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iatb.core.exceptions import ConfigError
from iatb.core.pipeline_health import PipelineStage

_LOGGER = logging.getLogger(__name__)

_CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class CheckpointData:
    """Immutable checkpoint capturing pipeline state at a point in time."""

    pipeline_id: str
    version: int
    created_at_utc: datetime
    completed_stages: list[PipelineStage]
    failed_stages: list[PipelineStage]
    last_successful_stage: PipelineStage | None
    metadata: dict[str, str]
    is_complete: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to JSON-compatible dict."""
        return {
            "pipeline_id": self.pipeline_id,
            "version": self.version,
            "created_at_utc": self.created_at_utc.isoformat(),
            "completed_stages": [s.value for s in self.completed_stages],
            "failed_stages": [s.value for s in self.failed_stages],
            "last_successful_stage": (
                self.last_successful_stage.value if self.last_successful_stage else None
            ),
            "metadata": dict(self.metadata),
            "is_complete": self.is_complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointData:
        """Deserialize checkpoint from dict.

        Args:
            data: Dictionary with checkpoint fields.

        Returns:
            CheckpointData instance.

        Raises:
            ConfigError: If data is invalid.
        """
        try:
            created_at = datetime.fromisoformat(data["created_at_utc"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)

            completed = [PipelineStage(v) for v in data.get("completed_stages", [])]
            failed = [PipelineStage(v) for v in data.get("failed_stages", [])]

            last_raw = data.get("last_successful_stage")
            last_stage = PipelineStage(last_raw) if last_raw else None

            return cls(
                pipeline_id=data["pipeline_id"],
                version=data.get("version", _CHECKPOINT_VERSION),
                created_at_utc=created_at,
                completed_stages=completed,
                failed_stages=failed,
                last_successful_stage=last_stage,
                metadata=data.get("metadata", {}),
                is_complete=data.get("is_complete", False),
            )
        except (KeyError, ValueError) as exc:
            msg = f"Invalid checkpoint data: {exc}"
            raise ConfigError(msg) from exc


class PipelineCheckpoint:
    """Manages pipeline state persistence for crash recovery.

    Saves checkpoint after each stage completion to a JSON file.
    On restart, loads the latest checkpoint to determine where
    to resume execution.
    """

    def __init__(self, checkpoint_dir: Path) -> None:
        if not str(checkpoint_dir).strip():
            msg = "checkpoint_dir must be a non-empty path"
            raise ConfigError(msg)
        self._checkpoint_dir = checkpoint_dir

    def _ensure_dir(self) -> None:
        """Create checkpoint directory if it doesn't exist."""
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _checkpoint_path(self, pipeline_id: str) -> Path:
        """Get checkpoint file path for a pipeline run."""
        safe_id = pipeline_id.replace("/", "_").replace("\\", "_")
        return self._checkpoint_dir / f"pipeline_{safe_id}.json"

    def save(self, checkpoint: CheckpointData) -> None:
        """Save checkpoint to disk.

        Args:
            checkpoint: CheckpointData to persist.
        """
        self._ensure_dir()
        path = self._checkpoint_path(checkpoint.pipeline_id)
        payload = checkpoint.to_dict()

        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            _LOGGER.debug(
                "Checkpoint saved: %s (stage: %s)",
                checkpoint.pipeline_id,
                checkpoint.last_successful_stage,
            )
        except OSError as exc:
            _LOGGER.error("Failed to save checkpoint: %s", exc)

    def load(self, pipeline_id: str) -> CheckpointData | None:
        """Load latest checkpoint for a pipeline run.

        Args:
            pipeline_id: Pipeline identifier to load checkpoint for.

        Returns:
            CheckpointData if found, None otherwise.
        """
        path = self._checkpoint_path(pipeline_id)
        if not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            checkpoint = CheckpointData.from_dict(data)
            _LOGGER.debug(
                "Checkpoint loaded: %s (stage: %s)",
                checkpoint.pipeline_id,
                checkpoint.last_successful_stage,
            )
            return checkpoint
        except (json.JSONDecodeError, OSError, ConfigError) as exc:
            _LOGGER.warning("Failed to load checkpoint for %s: %s", pipeline_id, exc)
            return None

    def delete(self, pipeline_id: str) -> bool:
        """Delete checkpoint file for a pipeline run.

        Args:
            pipeline_id: Pipeline identifier.

        Returns:
            True if deleted, False if not found.
        """
        path = self._checkpoint_path(pipeline_id)
        if path.exists():
            try:
                path.unlink()
                _LOGGER.debug("Checkpoint deleted: %s", pipeline_id)
                return True
            except OSError as exc:
                _LOGGER.error("Failed to delete checkpoint: %s", exc)
                return False
        return False

    def list_checkpoints(self) -> list[str]:
        """List all pipeline IDs with saved checkpoints.

        Returns:
            List of pipeline IDs with checkpoint files.
        """
        if not self._checkpoint_dir.exists():
            return []

        ids: list[str] = []
        for path in self._checkpoint_dir.glob("pipeline_*.json"):
            name = path.stem
            name = name.removeprefix("pipeline_")
            ids.append(name)
        return sorted(ids)

    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Remove checkpoint files older than max age.

        Args:
            max_age_hours: Maximum age in hours before cleanup.

        Returns:
            Number of checkpoint files removed.
        """
        if not self._checkpoint_dir.exists():
            return 0

        cutoff = datetime.now(UTC).timestamp() - (max_age_hours * 3600)
        removed = 0

        for path in self._checkpoint_dir.glob("pipeline_*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass

        if removed > 0:
            _LOGGER.info("Cleaned up %d old checkpoint(s)", removed)

        return removed


def create_checkpoint_from_stages(
    pipeline_id: str,
    completed_stages: list[PipelineStage],
    failed_stages: list[PipelineStage],
    metadata: dict[str, str] | None = None,
) -> CheckpointData:
    """Factory function to create a CheckpointData from stage lists.

    Args:
        pipeline_id: Pipeline run identifier.
        completed_stages: List of successfully completed stages.
        failed_stages: List of failed stages.
        metadata: Optional metadata dict.

    Returns:
        CheckpointData instance.
    """
    last_successful = completed_stages[-1] if completed_stages else None
    is_complete = len(failed_stages) == 0 and bool(completed_stages)

    return CheckpointData(
        pipeline_id=pipeline_id,
        version=_CHECKPOINT_VERSION,
        created_at_utc=datetime.now(UTC),
        completed_stages=list(completed_stages),
        failed_stages=list(failed_stages),
        last_successful_stage=last_successful,
        metadata=metadata or {},
        is_complete=is_complete,
    )
