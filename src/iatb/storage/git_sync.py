"""
Git synchronization workflow with mandatory gitleaks pre-check.
"""

import subprocess  # nosec B404
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class GitSyncReport:
    """Result metadata for a git commit and push workflow."""

    branch: str
    head_commit: str
    pushed: bool
    remote: str


class GitSyncService:
    """Run safe git sync operations with secret scan enforcement."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def _run(self, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603
            list(args),
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _ensure_success(result: subprocess.CompletedProcess[str], action: str) -> None:
        if result.returncode == 0:
            return
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        details = stderr or stdout or "no output"
        msg = f"{action} failed: {details}"
        raise ConfigError(msg)

    def current_branch(self) -> str:
        result = self._run(("git", "--no-pager", "rev-parse", "--abbrev-ref", "HEAD"))
        self._ensure_success(result, "Resolve current branch")
        return result.stdout.strip()

    def head_commit(self) -> str:
        result = self._run(("git", "--no-pager", "rev-parse", "HEAD"))
        self._ensure_success(result, "Resolve head commit")
        return result.stdout.strip()

    def run_gitleaks_scan(self) -> None:
        result = self._run(("gitleaks", "detect", "--source", ".", "--no-banner"))
        self._ensure_success(result, "gitleaks detect")

    def commit_and_push(
        self,
        *,
        commit_message: str,
        remote: str = "origin",
        branch: str | None = None,
    ) -> GitSyncReport:
        if not commit_message.strip():
            msg = "commit_message cannot be empty"
            raise ConfigError(msg)
        self.run_gitleaks_scan()
        self._ensure_success(self._run(("git", "add", "-A")), "git add")
        commit_result = self._run(("git", "commit", "-m", commit_message))
        has_nothing_to_commit = "nothing to commit" in self._combined_output(commit_result)
        if commit_result.returncode != 0 and not has_nothing_to_commit:
            self._ensure_success(commit_result, "git commit")
        target_branch = branch if branch is not None else self.current_branch()
        self._ensure_success(self._run(("git", "push", remote, target_branch)), "git push")
        return GitSyncReport(
            branch=target_branch,
            head_commit=self.head_commit(),
            pushed=True,
            remote=remote,
        )

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
        return f"{result.stdout}\n{result.stderr}".lower()
