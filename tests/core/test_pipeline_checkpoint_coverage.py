"""Supplemental coverage tests for pipeline checkpoint module.

Covers: empty checkpoint dir for list/cleanup, pipeline ID sanitization (slashes),
save OSError path, delete OSError path, load OSError path, from_dict missing fields,
from_dict default version, from_dict with None last_successful_stage,
create_checkpoint_from_stages with metadata None default, to_dict metadata copy.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.pipeline_checkpoint import (
    CheckpointData,
    PipelineCheckpoint,
    create_checkpoint_from_stages,
)
from iatb.core.pipeline_health import PipelineStage


class TestPipelineCheckpointDirEdgeCases:
    def test_list_checkpoints_nonexistent_dir(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path / "nonexistent")
        assert checkpoint_mgr.list_checkpoints() == []

    def test_cleanup_old_nonexistent_dir(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path / "nonexistent")
        removed = checkpoint_mgr.cleanup_old(max_age_hours=1)
        assert removed == 0

    def test_cleanup_old_oserror_on_stat(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("stat-test", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        mock_file = MagicMock(spec=Path)
        mock_file.stat.side_effect = OSError("stat error")
        mock_file.unlink = MagicMock()
        mock_file.match = MagicMock(return_value=True)
        with patch(
            "iatb.core.pipeline_checkpoint.Path.glob",
            return_value=[mock_file],
        ):
            removed = checkpoint_mgr.cleanup_old(max_age_hours=0)
            assert removed == 0

    def test_cleanup_old_oserror_on_unlink(self, tmp_path: Path) -> None:
        import os
        import time

        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("unlink-test", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        file_path = tmp_path / "pipeline_unlink-test.json"
        modification_time = time.time() - 48 * 3600
        os.utime(file_path, (modification_time, modification_time))

        with patch.object(Path, "unlink", side_effect=OSError("unlink error")):
            removed = checkpoint_mgr.cleanup_old(max_age_hours=24)
            assert removed == 0

    def test_list_checkpoints_sorted(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        for name in ["c", "a", "b"]:
            data = create_checkpoint_from_stages(name, [PipelineStage.INIT], [])
            checkpoint_mgr.save(data)
        ids = checkpoint_mgr.list_checkpoints()
        assert ids == ["a", "b", "c"]

    def test_list_checkpoints_ignores_non_pipeline_files(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        (tmp_path / "other_file.txt").write_text("not a checkpoint", encoding="utf-8")
        data = create_checkpoint_from_stages("real", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        ids = checkpoint_mgr.list_checkpoints()
        assert ids == ["real"]


class TestPipelineCheckpointPipelineIdSanitization:
    def test_forward_slash_sanitized(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("dir/sub", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        loaded = checkpoint_mgr.load("dir/sub")
        assert loaded is not None
        assert loaded.pipeline_id == "dir/sub"

    def test_backslash_sanitized(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("dir\\sub", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        loaded = checkpoint_mgr.load("dir\\sub")
        assert loaded is not None
        assert loaded.pipeline_id == "dir\\sub"

    def test_checkpoint_path_has_safe_filename(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        path = checkpoint_mgr._checkpoint_path("a/b\\c")
        assert path.name == "pipeline_a_b_c.json"


class TestPipelineCheckpointSaveOSError:
    def test_save_oserror_logged(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("save-err", [PipelineStage.INIT], [])
        with patch.object(Path, "write_text", side_effect=OSError("disk full")):
            checkpoint_mgr.save(data)


class TestPipelineCheckpointDeleteOSError:
    def test_delete_oserror_returns_false(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("del-err", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            result = checkpoint_mgr.delete("del-err")
            assert result is False


class TestPipelineCheckpointLoadOSError:
    def test_load_oserror_returns_none(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("load-err", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        with patch.object(Path, "read_text", side_effect=OSError("read error")):
            result = checkpoint_mgr.load("load-err")
            assert result is None


class TestCheckpointDataFromDictEdgeCases:
    def test_from_dict_missing_pipeline_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="Invalid checkpoint"):
            CheckpointData.from_dict(
                {"version": 1, "created_at_utc": "2026-04-27T06:00:00+00:00"}
            )

    def test_from_dict_missing_created_at_raises(self) -> None:
        with pytest.raises(ConfigError, match="Invalid checkpoint"):
            CheckpointData.from_dict({"pipeline_id": "test"})

    def test_from_dict_default_version(self) -> None:
        data = {
            "pipeline_id": "test",
            "created_at_utc": "2026-04-27T06:00:00+00:00",
            "completed_stages": [],
            "failed_stages": [],
            "last_successful_stage": None,
            "metadata": {},
            "is_complete": False,
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.version == 1

    def test_from_dict_utc_timezone_added_to_naive(self) -> None:
        data = {
            "pipeline_id": "test",
            "created_at_utc": "2026-04-27T06:00:00",
            "completed_stages": [],
            "failed_stages": [],
            "last_successful_stage": None,
            "metadata": {},
            "is_complete": False,
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.created_at_utc.tzinfo is not None

    def test_from_dict_preserves_utc_timezone(self) -> None:
        data = {
            "pipeline_id": "test",
            "version": 1,
            "created_at_utc": "2026-04-27T06:00:00+00:00",
            "completed_stages": [],
            "failed_stages": [],
            "last_successful_stage": None,
            "metadata": {},
            "is_complete": False,
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.created_at_utc.tzinfo is not None

    def test_from_dict_with_last_successful_stage(self) -> None:
        data = {
            "pipeline_id": "test",
            "version": 1,
            "created_at_utc": "2026-04-27T06:00:00+00:00",
            "completed_stages": ["INIT", "SCAN"],
            "failed_stages": [],
            "last_successful_stage": "SCAN",
            "metadata": {"key": "value"},
            "is_complete": True,
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.last_successful_stage == PipelineStage.SCAN
        assert checkpoint.metadata == {"key": "value"}
        assert checkpoint.is_complete is True


class TestCheckpointDataToDict:
    def test_to_dict_metadata_is_copy(self) -> None:
        checkpoint = CheckpointData(
            pipeline_id="test",
            version=1,
            created_at_utc=datetime(2026, 4, 27, 6, 0, 0, tzinfo=UTC),
            completed_stages=[PipelineStage.INIT],
            failed_stages=[],
            last_successful_stage=PipelineStage.INIT,
            metadata={"original": "value"},
            is_complete=False,
        )
        d = checkpoint.to_dict()
        d["metadata"]["mutated"] = "should_not_affect_original"
        assert "mutated" not in checkpoint.metadata

    def test_to_dict_none_last_stage(self) -> None:
        checkpoint = CheckpointData(
            pipeline_id="test",
            version=1,
            created_at_utc=datetime(2026, 4, 27, 6, 0, 0, tzinfo=UTC),
            completed_stages=[],
            failed_stages=[],
            last_successful_stage=None,
            metadata={},
            is_complete=False,
        )
        d = checkpoint.to_dict()
        assert d["last_successful_stage"] is None

    def test_to_dict_stage_values(self) -> None:
        checkpoint = CheckpointData(
            pipeline_id="test",
            version=1,
            created_at_utc=datetime(2026, 4, 27, 6, 0, 0, tzinfo=UTC),
            completed_stages=[PipelineStage.INIT, PipelineStage.SCAN],
            failed_stages=[PipelineStage.SENTIMENT],
            last_successful_stage=PipelineStage.SCAN,
            metadata={},
            is_complete=False,
        )
        d = checkpoint.to_dict()
        assert d["completed_stages"] == ["INIT", "SCAN"]
        assert d["failed_stages"] == ["SENTIMENT"]
        assert d["last_successful_stage"] == "SCAN"


class TestCreateCheckpointFromStagesEdgeCases:
    def test_metadata_defaults_to_empty(self) -> None:
        checkpoint = create_checkpoint_from_stages("no-meta", [PipelineStage.INIT], [])
        assert checkpoint.metadata == {}

    def test_is_complete_false_with_failed_stages(self) -> None:
        checkpoint = create_checkpoint_from_stages(
            "partial", [PipelineStage.INIT], [PipelineStage.SCAN]
        )
        assert checkpoint.is_complete is False

    def test_is_complete_false_with_empty_completed(self) -> None:
        checkpoint = create_checkpoint_from_stages("empty", [], [])
        assert checkpoint.is_complete is False

    def test_version_is_one(self) -> None:
        checkpoint = create_checkpoint_from_stages("ver", [PipelineStage.INIT], [])
        assert checkpoint.version == 1

    def test_created_at_is_utc(self) -> None:
        checkpoint = create_checkpoint_from_stages("utc-test", [PipelineStage.INIT], [])
        assert checkpoint.created_at_utc.tzinfo is not None

    def test_is_complete_true_all_stages_no_failures(self) -> None:
        checkpoint = create_checkpoint_from_stages(
            "complete",
            [PipelineStage.INIT, PipelineStage.SCAN, PipelineStage.SENTIMENT],
            [],
        )
        assert checkpoint.is_complete is True

    def test_last_successful_stage_is_last_completed(self) -> None:
        checkpoint = create_checkpoint_from_stages(
            "multi",
            [PipelineStage.INIT, PipelineStage.SCAN],
            [],
        )
        assert checkpoint.last_successful_stage == PipelineStage.SCAN

    def test_custom_metadata(self) -> None:
        checkpoint = create_checkpoint_from_stages(
            "meta-test", [PipelineStage.INIT], [], metadata={"key": "val"}
        )
        assert checkpoint.metadata == {"key": "val"}


class TestPipelineCheckpointDeleteSuccess:
    def test_delete_existing_checkpoint(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("del-ok", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        assert checkpoint_mgr.delete("del-ok") is True

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        assert checkpoint_mgr.delete("no-such") is False


class TestPipelineCheckpointLoadJsonDecodeError:
    def test_load_invalid_json_returns_none(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        file_path = tmp_path / "pipeline_bad-json.json"
        file_path.write_text("{invalid json", encoding="utf-8")
        result = checkpoint_mgr.load("bad-json")
        assert result is None


class TestCheckpointDataFromDictInvalidStage:
    def test_from_dict_invalid_completed_stage_raises(self) -> None:
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

    def test_from_dict_invalid_last_successful_stage_raises(self) -> None:
        data = {
            "pipeline_id": "test",
            "version": 1,
            "created_at_utc": "2026-04-27T06:00:00+00:00",
            "completed_stages": [],
            "failed_stages": [],
            "last_successful_stage": "NONEXISTENT_STAGE",
            "metadata": {},
            "is_complete": False,
        }
        with pytest.raises(ConfigError, match="Invalid checkpoint"):
            CheckpointData.from_dict(data)


class TestPipelineCheckpointInit:
    def test_empty_checkpoint_dir_raises(self) -> None:
        with pytest.raises(ConfigError, match="non-empty path"):
            PipelineCheckpoint(Path("  "))


class TestPipelineCheckpointCleanupSuccessful:
    def test_cleanup_removes_old_checkpoints(self, tmp_path: Path) -> None:
        import os
        import time

        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("old-checkpoint", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)

        file_path = tmp_path / "pipeline_old-checkpoint.json"
        modification_time = time.time() - 48 * 3600
        os.utime(file_path, (modification_time, modification_time))

        removed = checkpoint_mgr.cleanup_old(max_age_hours=24)
        assert removed == 1

    def test_cleanup_keeps_recent_checkpoints(self, tmp_path: Path) -> None:
        checkpoint_mgr = PipelineCheckpoint(tmp_path)
        data = create_checkpoint_from_stages("recent", [PipelineStage.INIT], [])
        checkpoint_mgr.save(data)
        removed = checkpoint_mgr.cleanup_old(max_age_hours=24)
        assert removed == 0
        assert checkpoint_mgr.load("recent") is not None
