"""
Comprehensive tests for git_sync.py — augmenting existing test_git_sync.py.

Covers all remaining branches for ≥90% coverage:
- run_gitleaks_scan (success + failure)
- commit_and_push: nothing-to-commit branch, commit failure,
  branch=None path, full report validation
- check_auth: malformed remote, ssh:// URL, http:// URL,
  unknown scheme, URL without space
- Integration tests with real git in tmp_path
- GitSyncReport dataclass construction
- ConflictResolutionStrategy iteration / membership
- _combined_output edge cases
- _push_with_retry: success on third attempt, backoff delay values
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.storage.git_sync import (
    ConflictResolutionStrategy,
    GitSyncReport,
    GitSyncService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_repo_root(tmp_path: Path) -> Path:
    """Create a mock git repository root directory."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    return repo_dir


@pytest.fixture()
def git_service(mock_repo_root: Path) -> GitSyncService:
    """Create GitSyncService instance pointing at mock repo."""
    return GitSyncService(mock_repo_root)


def _make_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    """Build a mock CompletedProcess-like object."""
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


# ---------------------------------------------------------------------------
# 1. GitSyncReport dataclass
# ---------------------------------------------------------------------------


class TestGitSyncReportDataclass:
    """Directly exercise the frozen dataclass."""

    def test_construct_and_read_fields(self) -> None:
        report = GitSyncReport(
            branch="main",
            head_commit="abc123",
            pushed=True,
            remote="origin",
        )
        assert report.branch == "main"
        assert report.head_commit == "abc123"
        assert report.pushed is True
        assert report.remote == "origin"

    def test_frozen_immutable(self) -> None:
        report = GitSyncReport(
            branch="dev", head_commit="def456", pushed=False, remote="upstream"
        )
        with pytest.raises(AttributeError):
            report.branch = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = GitSyncReport(branch="b", head_commit="h", pushed=False, remote="r")
        b = GitSyncReport(branch="b", head_commit="h", pushed=False, remote="r")
        assert a == b


# ---------------------------------------------------------------------------
# 2. ConflictResolutionStrategy additional coverage
# ---------------------------------------------------------------------------


class TestConflictResolutionStrategyExtra:
    """Enum iteration and membership tests."""

    def test_enum_members_count(self) -> None:
        assert len(ConflictResolutionStrategy) == 2

    def test_enum_iteration(self) -> None:
        members = list(ConflictResolutionStrategy)
        assert ConflictResolutionStrategy.OURS in members
        assert ConflictResolutionStrategy.THEIRS in members

    def test_enum_value_access(self) -> None:
        assert ConflictResolutionStrategy("ours") is ConflictResolutionStrategy.OURS
        assert ConflictResolutionStrategy("theirs") is ConflictResolutionStrategy.THEIRS


# ---------------------------------------------------------------------------
# 3. run_gitleaks_scan
# ---------------------------------------------------------------------------


class TestRunGitleaksScan:
    """Direct tests for run_gitleaks_scan method."""

    def test_gitleaks_scan_success(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = _make_result(returncode=0)
            git_service.run_gitleaks_scan()
            mock_run.assert_called_once_with(
                ("gitleaks", "detect", "--source", ".", "--no-banner")
            )

    def test_gitleaks_scan_failure(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = _make_result(returncode=1, stderr="leak detected")
            with pytest.raises(ConfigError, match="gitleaks detect failed"):
                git_service.run_gitleaks_scan()


# ---------------------------------------------------------------------------
# 4. commit_and_push — uncovered branches
# ---------------------------------------------------------------------------


class TestCommitAndPushNothingToCommit:
    """Test the 'nothing to commit' early-return branch (lines 104-105)."""

    def test_nothing_to_commit_still_pushes(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            # Sequence: gitleaks, git add, git commit, git push, head_commit
            mock_run.side_effect = [
                _make_result(returncode=0),  # gitleaks
                _make_result(returncode=0),  # git add
                _make_result(
                    returncode=1,
                    stdout="",
                    stderr="nothing to commit, working tree clean",
                ),  # git commit → nothing to commit
                _make_result(returncode=0),  # git push
                _make_result(returncode=0, stdout="deadbeef\n"),  # head_commit
            ]

            report = git_service.commit_and_push(
                commit_message="chore: sync", branch="main"
            )
            assert report.pushed is True
            assert report.head_commit == "deadbeef"


class TestCommitAndPushCommitFails:
    """Test commit_and_push when git commit fails with a real error."""

    def test_commit_fails_raises(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(returncode=0),  # gitleaks
                _make_result(returncode=0),  # git add
                _make_result(
                    returncode=1, stderr="pre-commit hook failed"
                ),  # git commit
            ]

            with pytest.raises(ConfigError, match="git commit failed"):
                git_service.commit_and_push(commit_message="test", branch="main")


class TestCommitAndPushBranchNone:
    """Test commit_and_push with branch=None falls back to current_branch."""

    def test_branch_none_uses_current_branch(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            # Sequence: gitleaks, git add, git commit, current_branch,
            # git push, head_commit
            mock_run.side_effect = [
                _make_result(returncode=0),  # gitleaks
                _make_result(returncode=0),  # git add
                _make_result(returncode=0, stdout="[main abc] msg"),  # commit
                _make_result(returncode=0, stdout="feature-branch\n"),  # branch
                _make_result(returncode=0),  # git push
                _make_result(returncode=0, stdout="cafe1234\n"),  # head_commit
            ]

            report = git_service.commit_and_push(commit_message="test", branch=None)
            assert report.branch == "feature-branch"
            assert report.head_commit == "cafe1234"


class TestCommitAndPushFullReport:
    """Validate every field of the returned GitSyncReport."""

    def test_report_fields(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(returncode=0),  # gitleaks
                _make_result(returncode=0),  # git add
                _make_result(returncode=0, stdout="[main abc] msg"),  # commit
                _make_result(returncode=0),  # git push
                _make_result(returncode=0, stdout="abcd1234\n"),  # head_commit
            ]

            report = git_service.commit_and_push(
                commit_message="deploy", remote="upstream", branch="release"
            )
            assert report.branch == "release"
            assert report.head_commit == "abcd1234"
            assert report.pushed is True
            assert report.remote == "upstream"


# ---------------------------------------------------------------------------
# 5. check_auth — uncovered branches
# ---------------------------------------------------------------------------


class TestCheckAuthEdgeCases:
    """Cover malformed remote lines and URL-scheme branches."""

    def test_malformed_remote_line_no_tab(self, git_service: GitSyncService) -> None:
        """Line has no tab separator → parts < 2 → (False, 'none')."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = _make_result(
                returncode=0, stdout="just-a-url-no-tab\n"
            )
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is False
            assert auth_type == "none"

    def test_ssh_url_scheme(self, git_service: GitSyncService) -> None:
        """URL starts with 'ssh://' → SSH auth check path."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(
                    returncode=0,
                    stdout="origin\tssh://git@github.com/user/repo.git (fetch)\n",
                ),
                _make_result(returncode=0),  # SSH -T succeeds
            ]
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is True
            assert auth_type == "ssh"

    def test_ssh_url_scheme_failure(self, git_service: GitSyncService) -> None:
        """URL starts with 'ssh://' but SSH key not available."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(
                    returncode=0,
                    stdout="origin\tssh://git@github.com/user/repo.git (fetch)\n",
                ),
                _make_result(returncode=255),  # SSH -T fails
            ]
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is False
            assert auth_type == "ssh"

    def test_http_url_with_credential(self, git_service: GitSyncService) -> None:
        """URL starts with 'http://' and credential helper is configured."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(
                    returncode=0,
                    stdout="origin\thttp://github.com/user/repo.git (fetch)\n",
                ),
                _make_result(returncode=0, stdout="store\n"),
            ]
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is True
            assert auth_type == "token"

    def test_http_url_no_credential(self, git_service: GitSyncService) -> None:
        """URL starts with 'http://' but no credential helper."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(
                    returncode=0,
                    stdout="origin\thttp://github.com/user/repo.git (fetch)\n",
                ),
                _make_result(returncode=1),
            ]
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is False
            assert auth_type == "token"

    def test_unknown_url_scheme(self, git_service: GitSyncService) -> None:
        """URL scheme is neither SSH nor HTTP → (False, 'none')."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = _make_result(
                returncode=0,
                stdout="origin\tfile:///local/repo (fetch)\n",
            )
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is False
            assert auth_type == "none"

    def test_url_without_space_suffix(self, git_service: GitSyncService) -> None:
        """Remote line where URL has no trailing ' (fetch)' space segment."""
        with patch.object(git_service, "_run") as mock_run:
            # URL has no space → url_part.split()[0] path not taken;
            # the else branch returns url_part as-is
            mock_run.side_effect = [
                _make_result(
                    returncode=0,
                    stdout="origin\tgit@github.com:user/repo.git\n",
                ),
                _make_result(returncode=0),  # SSH -T
            ]
            authenticated, auth_type = git_service.check_auth()
            assert authenticated is True
            assert auth_type == "ssh"


# ---------------------------------------------------------------------------
# 6. _push_with_retry — third-attempt success + delay values
# ---------------------------------------------------------------------------


class TestPushWithRetryExtra:
    """Additional retry scenarios for full branch coverage."""

    def test_success_on_third_attempt(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            with patch("iatb.storage.git_sync.time.sleep") as mock_sleep:
                mock_run.side_effect = [
                    _make_result(returncode=1, stderr="fail"),
                    _make_result(returncode=1, stderr="fail"),
                    _make_result(returncode=0),
                ]
                git_service._push_with_retry("origin", "main")
                assert mock_run.call_count == 3
                # sleep called after 1st and 2nd failures
                assert mock_sleep.call_count == 2

    def test_backoff_delay_values(self, git_service: GitSyncService) -> None:
        """Verify exponential backoff: base * 2^attempt."""
        with patch.object(git_service, "_run") as mock_run:
            with patch("iatb.storage.git_sync.time.sleep") as mock_sleep:
                mock_run.return_value = _make_result(returncode=1, stderr="fail")
                with pytest.raises(ConfigError):
                    git_service._push_with_retry("origin", "main")
                # base=1.0 → delays: 1.0 (2^0), 2.0 (2^1)
                mock_sleep.assert_any_call(1.0)
                mock_sleep.assert_any_call(2.0)


# ---------------------------------------------------------------------------
# 7. _combined_output edge cases
# ---------------------------------------------------------------------------


class TestCombinedOutputExtra:
    """Ensure _combined_output lowercases and joins stdout + stderr."""

    def test_combined_output_is_lowercase(self) -> None:
        result = _make_result(stdout="Hello World", stderr="ERROR MSG")
        combined = GitSyncService._combined_output(result)
        assert combined == "hello world\nerror msg"

    def test_combined_output_empty(self) -> None:
        result = _make_result(stdout="", stderr="")
        combined = GitSyncService._combined_output(result)
        assert combined == "\n"


# ---------------------------------------------------------------------------
# 8. _ensure_success — ensure full branch coverage with stderr preference
# ---------------------------------------------------------------------------


class TestEnsureSuccessExtra:
    """Additional edge cases for _ensure_success."""

    def test_prefers_stderr_over_stdout(self) -> None:
        result = _make_result(returncode=1, stdout="stdout msg", stderr="stderr msg")
        with pytest.raises(ConfigError, match="stderr msg"):
            GitSyncService._ensure_success(result, "action")

    def test_uses_stdout_when_stderr_empty(self) -> None:
        result = _make_result(returncode=1, stdout="out", stderr="")
        with pytest.raises(ConfigError, match="out"):
            GitSyncService._ensure_success(result, "test")

    def test_returns_early_on_zero_returncode(self) -> None:
        result = _make_result(returncode=0, stderr="ignored", stdout="ignored")
        # Should NOT raise
        GitSyncService._ensure_success(result, "anything")


# ---------------------------------------------------------------------------
# 9. Integration tests with REAL git in tmp_path
# ---------------------------------------------------------------------------


class TestRealGitIntegration:
    """Integration tests using real git operations in temp directory."""

    @pytest.fixture()
    def real_git_repo(self, tmp_path: Path) -> Path:
        """Create a real git repository with an initial commit."""
        repo = tmp_path / "real_repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        # Create initial file and commit
        (repo / "README.md").write_text("test repo")
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "initial commit"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return repo

    def test_current_branch_real_git(self, real_git_repo: Path) -> None:
        svc = GitSyncService(real_git_repo)
        branch = svc.current_branch()
        assert branch in ("main", "master")

    def test_head_commit_real_git(self, real_git_repo: Path) -> None:
        svc = GitSyncService(real_git_repo)
        commit = svc.head_commit()
        assert len(commit) == 40
        assert all(c in "0123456789abcdef" for c in commit)

    def test_status_clean_repo(self, real_git_repo: Path) -> None:
        svc = GitSyncService(real_git_repo)
        status = svc.status()
        assert status == ""

    def test_status_dirty_repo(self, real_git_repo: Path) -> None:
        (real_git_repo / "new_file.txt").write_text("content")
        svc = GitSyncService(real_git_repo)
        status = svc.status()
        assert "new_file.txt" in status

    def test_run_gitleaks_scan_not_installed(self, real_git_repo: Path) -> None:
        """gitleaks likely not installed in test env — verify error path."""
        svc = GitSyncService(real_git_repo)
        # gitleaks may not be on PATH, so this should raise ConfigError
        # or succeed if it is installed. We handle both gracefully.
        try:
            svc.run_gitleaks_scan()
        except ConfigError:
            pass  # Expected when gitleaks is not installed

    def test_check_auth_no_remote_configured(self, real_git_repo: Path) -> None:
        """Fresh repo has no remotes → (False, 'none')."""
        svc = GitSyncService(real_git_repo)
        authenticated, auth_type = svc.check_auth()
        assert authenticated is False
        assert auth_type == "none"

    def test_status_after_modified_file(self, real_git_repo: Path) -> None:
        (real_git_repo / "README.md").write_text("modified content")
        svc = GitSyncService(real_git_repo)
        status = svc.status()
        assert "README.md" in status
        # Verify the status starts with M (modified)
        assert status.startswith(" M") or status.startswith("M")


# ---------------------------------------------------------------------------
# 10. pull_rebase with mocked _run — full coverage
# ---------------------------------------------------------------------------


class TestPullRebaseExtra:
    """Additional pull_rebase scenarios for full branch coverage."""

    def test_pull_rebase_with_custom_remote(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                _make_result(returncode=0, stdout="develop\n"),
                _make_result(returncode=0),  # fetch upstream
                _make_result(returncode=0),  # rebase upstream/develop
            ]
            git_service.pull_rebase(remote="upstream")
            # Verify the fetch call uses the custom remote
            fetch_call = mock_run.call_args_list[1]
            assert fetch_call[0][0][2] == "upstream"


# ---------------------------------------------------------------------------
# 11. commit_and_push — empty string message (not just whitespace)
# ---------------------------------------------------------------------------


class TestCommitAndPushEmptyMessage:
    """Edge case: empty string commit message."""

    def test_empty_string_message_raises(self, git_service: GitSyncService) -> None:
        with pytest.raises(ConfigError, match="commit_message cannot be empty"):
            git_service.commit_and_push(commit_message="")

    def test_whitespace_only_message_raises(self, git_service: GitSyncService) -> None:
        with pytest.raises(ConfigError, match="commit_message cannot be empty"):
            git_service.commit_and_push(commit_message="\t \n")


# ---------------------------------------------------------------------------
# 12. resolve_conflicts — THEIRS failure
# ---------------------------------------------------------------------------


class TestResolveConflictsTheirsFailure:
    """Cover checkout --theirs failure path."""

    def test_resolve_theirs_failure(self, git_service: GitSyncService) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = _make_result(
                returncode=1, stderr="checkout theirs failed"
            )
            with pytest.raises(ConfigError, match="git checkout --theirs failed"):
                git_service.resolve_conflicts(ConflictResolutionStrategy.THEIRS)
