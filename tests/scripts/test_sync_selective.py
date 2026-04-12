"""
Tests for sync_selective.py script (Option B: Selective Git Sync)
"""

import random
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _result(
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    """Create a mock subprocess result."""
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _Runner:
    """Mock subprocess runner that returns predefined responses."""

    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(
        self,
        args: list[str],
        *,
        cwd: str = "",
        capture_output: bool = False,
        text: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Mock subprocess.run call."""
        _ = cwd, capture_output, text
        self.calls.append(args)
        return self._responses.pop(0)


class TestSyncSelective:
    """Test selective git sync functionality."""

    def test_stage_specific_files_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Test successful staging of specific file patterns."""
        responses = [
            _result(["git", "add", "fix_*.py"]),
            _result(["git", "status"]),
            _result(["git", "add", "sync_*.py"]),
            _result(["git", "status"]),
            _result(["git", "add", "verify_*.py"]),
            _result(["git", "status"]),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        # Import and test the function
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import stage_specific_files

        result = stage_specific_files(["fix_*.py", "sync_*.py", "verify_*.py"])
        assert result is True
        assert len(runner.calls) == 4  # 3 git add + 1 git status --short

    def test_stage_specific_files_partial_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test staging when some files fail to stage."""
        responses = [
            _result(["git", "add", "fix_*.py"], returncode=1, stderr="pathspec did not match"),
            _result(["git", "add", "sync_*.py"]),
            _result(["git", "status"]),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import stage_specific_files

        result = stage_specific_files(["fix_*.py", "sync_*.py"])
        assert result is True  # Still true because at least one file staged

    def test_stage_specific_files_all_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test staging when all files fail to stage."""
        responses = [
            _result(["git", "add", "fix_*.py"], returncode=1, stderr="pathspec did not match"),
            _result(["git", "add", "sync_*.py"], returncode=1, stderr="pathspec did not match"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import stage_specific_files

        result = stage_specific_files(["fix_*.py", "sync_*.py"])
        assert result is False

    def test_create_commit_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful commit creation."""
        responses = [
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "commit"], returncode=0),
            _result(["git", "log"], stdout="abc123 feat(feature): selective file updates\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import create_commit

        result = create_commit()
        assert result is True

    def test_create_commit_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test commit creation failure."""
        responses = [
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "commit"], returncode=1, stderr="commit failed\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import create_commit

        result = create_commit()
        assert result is False

    def test_push_to_remote_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful push to remote."""
        responses = [
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "push"], returncode=0, stdout="Success\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import push_to_remote

        result = push_to_remote()
        assert result is True

    def test_push_to_remote_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test push to remote failure."""
        responses = [
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "push"], returncode=1, stderr="push failed\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import push_to_remote

        result = push_to_remote()
        assert result is False

    def test_verify_sync_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful sync verification."""
        responses = [
            _result(["git", "rev-parse", "HEAD"], stdout="abc123\n"),
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "fetch"]),
            _result(["git", "rev-parse", "origin/optimize/feature"], stdout="abc123\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import verify_sync

        result = verify_sync()
        assert result is True

    def test_verify_sync_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test sync verification when hashes don't match."""
        responses = [
            _result(["git", "rev-parse", "HEAD"], stdout="abc123\n"),
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="optimize/feature\n"),
            _result(["git", "fetch"]),
            _result(["git", "rev-parse", "origin/optimize/feature"], stdout="def456\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import verify_sync

        result = verify_sync()
        assert result is False

    def test_get_git_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test getting git status summary."""
        responses = [
            _result(["git", "rev-parse", "--abbrev-ref", "HEAD"], stdout="main\n"),
            _result(["git", "config"], stdout="git@github.com:user/repo.git\n"),
            _result(["git", "log"], stdout="abc123 commit message\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("subprocess.run", runner)

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        from sync_selective import get_git_status

        status = get_git_status()
        assert status["branch"] == "main"
        assert status["remote_url"] == "git@github.com:user/repo.git"
        assert status["latest_commit"] == "abc123 commit message"
