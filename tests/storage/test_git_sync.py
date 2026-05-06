"""Tests for GitSyncService with enhanced functionality."""

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


@pytest.fixture
def mock_repo_root(tmp_path: Path) -> Path:
    """Create a mock git repository root."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()
    git_dir = repo_dir / ".git"
    git_dir.mkdir()
    return repo_dir


@pytest.fixture
def git_service(mock_repo_root: Path) -> GitSyncService:
    """Create GitSyncService instance."""
    return GitSyncService(mock_repo_root)


class TestConflictResolutionStrategy:
    """Test ConflictResolutionStrategy enum."""

    def test_ours_value(self) -> None:
        assert ConflictResolutionStrategy.OURS.value == "ours"

    def test_theirs_value(self) -> None:
        assert ConflictResolutionStrategy.THEIRS.value == "theirs"


class TestGitSyncServiceInit:
    """Test GitSyncService initialization."""

    def test_init_sets_repo_root(self, mock_repo_root: Path) -> None:
        service = GitSyncService(mock_repo_root)
        assert service._repo_root == mock_repo_root

    def test_init_sets_max_retries(self, mock_repo_root: Path) -> None:
        service = GitSyncService(mock_repo_root)
        assert service._max_retries == 3

    def test_init_sets_base_delay(self, mock_repo_root: Path) -> None:
        service = GitSyncService(mock_repo_root)
        assert service._base_delay_seconds == 1.0


class TestRun:
    """Test _run method."""

    def test_run_executes_command(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        result = git_service._run(("git", "--version"))
        assert isinstance(result, subprocess.CompletedProcess)


class TestEnsureSuccess:
    """Test _ensure_success static method."""

    def test_success_returns_none(self) -> None:
        result = MagicMock()
        result.returncode = 0
        GitSyncService._ensure_success(result, "test action")

    def test_failure_raises_config_error(self) -> None:
        result = MagicMock()
        result.returncode = 1
        result.stderr = "error message"
        result.stdout = ""

        with pytest.raises(ConfigError, match="test action failed: error message"):
            GitSyncService._ensure_success(result, "test action")

    def test_failure_with_stdout(self) -> None:
        result = MagicMock()
        result.returncode = 1
        result.stderr = ""
        result.stdout = "stdout error"

        with pytest.raises(ConfigError, match="test action failed: stdout error"):
            GitSyncService._ensure_success(result, "test action")

    def test_failure_no_output(self) -> None:
        result = MagicMock()
        result.returncode = 1
        result.stderr = ""
        result.stdout = ""

        with pytest.raises(ConfigError, match="test action failed: no output"):
            GitSyncService._ensure_success(result, "test action")


class TestCurrentBranch:
    """Test current_branch method."""

    def test_returns_branch_name(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="main\n", stderr="")
            branch = git_service.current_branch()
            assert branch == "main"
            mock_run.assert_called_once()


class TestHeadCommit:
    """Test head_commit method."""

    def test_returns_commit_hash(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
            commit = git_service.head_commit()
            assert commit == "abc123"


class TestPullRebase:
    """Test pull_rebase method."""

    def test_pull_rebase_success(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="main\n", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]

            git_service.pull_rebase(remote="origin")

            assert mock_run.call_count == 3

    def test_pull_rebase_fetch_fails(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="main\n", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="fetch failed"),
            ]

            with pytest.raises(ConfigError, match="git fetch failed"):
                git_service.pull_rebase(remote="origin")

    def test_pull_rebase_rebase_fails(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="main\n", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="rebase failed"),
            ]

            with pytest.raises(ConfigError, match="git rebase"):
                git_service.pull_rebase(remote="origin")


class TestStatus:
    """Test status method."""

    def test_status_success(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" M file.txt\n", stderr="")

            status = git_service.status()

            assert status == "M file.txt"

    def test_status_empty_when_no_changes(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            status = git_service.status()

            assert status == ""

    def test_status_failure(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")

            with pytest.raises(ConfigError, match="git status failed"):
                git_service.status()


class TestResolveConflicts:
    """Test resolve_conflicts method."""

    def test_resolve_with_ours(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            git_service.resolve_conflicts(ConflictResolutionStrategy.OURS)

            mock_run.assert_called_once_with(("git", "checkout", "--ours", "."))

    def test_resolve_with_theirs(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            git_service.resolve_conflicts(ConflictResolutionStrategy.THEIRS)

            mock_run.assert_called_once_with(("git", "checkout", "--theirs", "."))

    def test_resolve_failure(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="checkout failed")

            with pytest.raises(ConfigError, match="git checkout --ours failed"):
                git_service.resolve_conflicts(ConflictResolutionStrategy.OURS)


class TestCheckAuth:
    """Test check_auth method."""

    def test_check_auth_ssh_success(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="origin\tgit@github.com:user/repo.git (fetch)\n",
                    stderr="",
                ),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is True
            assert auth_type == "ssh"

    def test_check_auth_no_remote(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is False
            assert auth_type == "none"

    def test_check_auth_error(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is False
            assert auth_type == "error"

    def test_check_auth_token_success(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        """Test token authentication when credential helper is configured."""
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="origin\thttps://github.com/user/repo.git (fetch)\n",
                    stderr="",
                ),
                MagicMock(returncode=0, stdout="store\n", stderr=""),
            ]

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is True
            assert auth_type == "token"

    def test_check_auth_ssh_failure(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="origin\tgit@github.com:user/repo.git (fetch)\n",
                    stderr="",
                ),
                MagicMock(returncode=255, stdout="", stderr="permission denied"),
            ]

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is False
            assert auth_type == "ssh"

    def test_check_auth_token_missing_helper(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout="origin\thttps://github.com/user/repo.git (fetch)\n",
                    stderr="",
                ),
                MagicMock(returncode=1, stdout="", stderr="no helper"),
            ]

            authenticated, auth_type = git_service.check_auth()

            assert authenticated is False
            assert auth_type == "token"


class TestPushWithRetry:
    """Test _push_with_retry method."""

    def test_push_success_first_attempt(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            git_service._push_with_retry("origin", "main")

            assert mock_run.call_count == 1

    def test_push_success_on_second_attempt(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            with patch("time.sleep"):
                mock_run.side_effect = [
                    MagicMock(returncode=1, stdout="", stderr="fail"),
                    MagicMock(returncode=0, stdout="", stderr=""),
                ]

                git_service._push_with_retry("origin", "main")

                assert mock_run.call_count == 2

    def test_push_exhausts_retries(self, git_service: GitSyncService, mock_repo_root: Path) -> None:
        with patch.object(git_service, "_run") as mock_run:
            with patch("time.sleep"):
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")

                with pytest.raises(ConfigError, match="git push failed"):
                    git_service._push_with_retry("origin", "main")

                assert mock_run.call_count == 3

    def test_push_exponential_backoff(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            with patch("time.sleep") as mock_sleep:
                mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")

                with pytest.raises(ConfigError):
                    git_service._push_with_retry("origin", "main")

                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(1.0)
                mock_sleep.assert_any_call(2.0)


class TestCommitAndPush:
    """Test commit_and_push method with retry logic."""

    def test_commit_and_push_success(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with patch.object(git_service, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            ]

            report = git_service.commit_and_push(
                commit_message="test commit", remote="origin", branch="main"
            )

            assert isinstance(report, GitSyncReport)
            assert report.pushed is True
            assert report.remote == "origin"

    def test_commit_and_push_empty_message(
        self, git_service: GitSyncService, mock_repo_root: Path
    ) -> None:
        with pytest.raises(ConfigError, match="commit_message cannot be empty"):
            git_service.commit_and_push(commit_message="  ")


class TestCombinedOutput:
    """Test _combined_output static method."""

    def test_combined_output(self) -> None:
        result = MagicMock()
        result.stdout = "stdout message"
        result.stderr = "stderr message"

        combined = GitSyncService._combined_output(result)

        assert "stdout message" in combined
        assert "stderr message" in combined
