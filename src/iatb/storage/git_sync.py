"""
Git synchronization workflow with mandatory gitleaks pre-check.
"""

import subprocess  # nosec B404
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class GitSyncReport:
    """Result metadata for a git commit and push workflow."""

    branch: str
    head_commit: str
    pushed: bool
    remote: str


class ConflictResolutionStrategy(Enum):
    """Strategy for resolving merge conflicts."""

    OURS = "ours"
    THEIRS = "theirs"


class GitSyncService:
    """Run safe git sync operations with secret scan enforcement."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._max_retries = 3
        self._base_delay_seconds = 1.0

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

    def _push_with_retry(self, remote: str, branch: str) -> None:
        """Push to remote with exponential backoff retry logic."""
        last_error: ConfigError | None = None

        for attempt in range(self._max_retries):
            try:
                result = self._run(("git", "push", remote, branch))
                self._ensure_success(result, "git push")
                return
            except ConfigError as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._base_delay_seconds * (2**attempt)
                    time.sleep(delay)

        if last_error:
            raise last_error

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
        self._push_with_retry(remote, target_branch)
        return GitSyncReport(
            branch=target_branch,
            head_commit=self.head_commit(),
            pushed=True,
            remote=remote,
        )

    def pull_rebase(self, remote: str = "origin") -> None:
        """Fetch and rebase current branch onto remote branch.

        Executes: git fetch origin && git rebase origin/<branch>
        """
        branch = self.current_branch()
        self._ensure_success(self._run(("git", "fetch", remote)), "git fetch")
        result = self._run(("git", "rebase", f"{remote}/{branch}"))
        if result.returncode != 0:
            self._ensure_success(result, f"git rebase {remote}/{branch}")

    def status(self) -> str:
        """Get git status in porcelain format.

        Returns:
            Git status output from 'git status --porcelain'
        """
        result = self._run(("git", "status", "--porcelain"))
        self._ensure_success(result, "git status")
        return result.stdout.strip()

    def resolve_conflicts(self, strategy: ConflictResolutionStrategy) -> None:
        """Resolve merge conflicts using specified strategy.

        Args:
            strategy: OURS to keep local changes, THEIRS to accept remote changes
        """
        if strategy == ConflictResolutionStrategy.OURS:
            result = self._run(("git", "checkout", "--ours", "."))
        else:
            result = self._run(("git", "checkout", "--theirs", "."))
        self._ensure_success(result, f"git checkout --{strategy.value}")

    def check_auth(self) -> tuple[bool, str]:
        """Verify SSH key or token availability.

        Returns:
            Tuple of (is_authenticated, auth_type)
            auth_type is one of: 'ssh', 'token', 'none', 'error'
        """
        result = self._run(("git", "remote", "-v"))
        if result.returncode != 0:
            return (False, "error")

        lines = result.stdout.strip().splitlines()
        if not lines:
            return (False, "none")

        # Parse the first remote URL (format: <name>\t<url> (<fetch|push>))
        first_line = lines[0]
        parts = first_line.split("\t")
        if len(parts) < 2:
            return (False, "none")

        url_part = parts[1].strip()
        # Remove the trailing " (fetch)" or " (push)" if present
        url = url_part.split()[0] if " " in url_part else url_part

        # Determine auth type from URL scheme
        if url.startswith("git@") or url.startswith("ssh://"):
            test_result = self._run(
                ("ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "git@github.com")
            )
            if test_result.returncode == 0:
                return (True, "ssh")
            else:
                return (False, "ssh")
        elif url.startswith("https://") or url.startswith("http://"):
            cred_result = self._run(("git", "config", "credential.helper"))
            if cred_result.returncode == 0:
                return (True, "token")
            else:
                return (False, "token")
        else:
            return (False, "none")

    @staticmethod
    def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
        return f"{result.stdout}\n{result.stderr}".lower()
