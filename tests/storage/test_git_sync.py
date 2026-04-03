"""
Tests for git sync service.
"""

import subprocess
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.storage.git_sync import GitSyncService


def _result(
    args: list[str],
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _Runner:
    def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        _ = cwd, capture_output, text, check
        self.calls.append(args)
        return self._responses.pop(0)


class TestGitSyncService:
    """Test git sync workflows with deterministic subprocess mocking."""

    def test_current_branch_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = _Runner([_result(["git"], stdout="production\n")])
        monkeypatch.setattr("iatb.storage.git_sync.subprocess.run", runner)
        service = GitSyncService(tmp_path)
        assert service.current_branch() == "production"

    def test_current_branch_failure_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runner = _Runner([_result(["git"], returncode=1, stderr="fatal")])
        monkeypatch.setattr("iatb.storage.git_sync.subprocess.run", runner)
        service = GitSyncService(tmp_path)
        with pytest.raises(ConfigError, match="Resolve current branch failed"):
            service.current_branch()

    def test_run_gitleaks_scan_failure_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runner = _Runner([_result(["gitleaks"], returncode=1, stderr="leak found")])
        monkeypatch.setattr("iatb.storage.git_sync.subprocess.run", runner)
        service = GitSyncService(tmp_path)
        with pytest.raises(ConfigError, match="gitleaks detect failed"):
            service.run_gitleaks_scan()

    def test_commit_and_push_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        responses = [
            _result(["gitleaks"]),
            _result(["git", "add"]),
            _result(["git", "commit"]),
            _result(["git", "rev-parse"], stdout="production\n"),
            _result(["git", "push"]),
            _result(["git", "rev-parse"], stdout="abc123\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("iatb.storage.git_sync.subprocess.run", runner)
        service = GitSyncService(tmp_path)
        report = service.commit_and_push(commit_message="feat: storage")
        assert report.branch == "production"
        assert report.head_commit == "abc123"
        assert report.pushed is True

    def test_commit_and_push_allows_nothing_to_commit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        responses = [
            _result(["gitleaks"]),
            _result(["git", "add"]),
            _result(["git", "commit"], returncode=1, stderr="nothing to commit"),
            _result(["git", "rev-parse"], stdout="production\n"),
            _result(["git", "push"]),
            _result(["git", "rev-parse"], stdout="def456\n"),
        ]
        runner = _Runner(responses)
        monkeypatch.setattr("iatb.storage.git_sync.subprocess.run", runner)
        service = GitSyncService(tmp_path)
        report = service.commit_and_push(commit_message="feat: storage")
        assert report.head_commit == "def456"

    def test_commit_and_push_rejects_empty_message(self, tmp_path: Path) -> None:
        service = GitSyncService(tmp_path)
        with pytest.raises(ConfigError, match="commit_message cannot be empty"):
            service.commit_and_push(commit_message="   ")
