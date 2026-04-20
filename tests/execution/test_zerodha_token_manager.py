from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from iatb.broker.token_manager import ZerodhaTokenManager, _load_env_file

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_resolve_saved_access_token_reuses_same_day_value(tmp_path: Path) -> None:
    """Test that resolve_saved_access_token reuses token from same day."""
    today = datetime.now(UTC).date()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=access-today",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_path,
        env_values=_load_env_file(env_path),
        today_utc=today,
    )
    # Mock keyring to return None, forcing fallback to .env file
    with patch("iatb.broker.token_manager.keyring.get_password", return_value=None):
        assert manager.resolve_saved_access_token() == "access-today"  # noqa: S105


def test_resolve_saved_access_token_rejects_stale_date(tmp_path: Path) -> None:
    """Test that resolve_saved_access_token rejects stale token."""
    today = datetime.now(UTC).date()
    stale = today - timedelta(days=1)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=access-stale",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={stale.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_path,
        env_values=_load_env_file(env_path),
        today_utc=today,
    )
    # Mock keyring to return None, forcing fallback to .env file
    with patch("iatb.broker.token_manager.keyring.get_password", return_value=None):
        assert manager.resolve_saved_access_token() is None


def test_resolve_saved_request_token_reads_dotenv_store_for_example_file(tmp_path: Path) -> None:
    """Test that request token is read from .env when using .env.example."""
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            (
                "ZERODHA_REQUEST_TOKEN=req-fresh",
                f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_example_path,
        env_values=_load_env_file(env_example_path),
        today_utc=today,
    )
    # Mock keyring to return None, forcing fallback to .env file
    with patch("iatb.broker.token_manager.keyring.get_password", return_value=None):
        assert manager.resolve_saved_request_token() == "req-fresh"  # noqa: S105


def test_resolve_saved_request_token_ignores_example_file_token_values(tmp_path: Path) -> None:
    """Test that request token ignores values in .env.example."""
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_REQUEST_TOKEN=req-stale-example",
                f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_example_path,
        env_values=_load_env_file(env_example_path),
        today_utc=today,
    )
    # Mock keyring to return None, forcing fallback to .env file
    with patch("iatb.broker.token_manager.keyring.get_password", return_value=None):
        assert manager.resolve_saved_request_token() is None


def test_persist_session_tokens_writes_to_dotenv_when_env_file_is_example(tmp_path: Path) -> None:
    """Test that persist_session_tokens writes to .env when using .env.example."""
    today = datetime.now(UTC).date()
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_example_path,
        env_values=_load_env_file(env_example_path),
        today_utc=today,
    )
    with patch.object(manager, "store_access_token"):
        with patch("iatb.broker.token_manager.keyring.set_password"):
            written_path = manager.persist_session_tokens(
                access_token="access-new",  # noqa: S106
                request_token="req-new",  # noqa: S106
            )
            assert written_path == tmp_path / ".env"
            persisted = written_path.read_text(encoding="utf-8")
            assert "ZERODHA_ACCESS_TOKEN=access-new" in persisted
            assert f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today.isoformat()}" in persisted
            assert "ZERODHA_REQUEST_TOKEN=req-new" in persisted
            assert f"ZERODHA_REQUEST_TOKEN_DATE_UTC={today.isoformat()}" in persisted
            assert "BROKER_OAUTH_2FA_VERIFIED=true" in persisted


def test_resolve_saved_access_token_prioritizes_keyring_over_env(tmp_path: Path) -> None:
    """Test that resolve_saved_access_token prioritizes keyring storage."""
    today = datetime.now(UTC).date()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=env-token",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today.isoformat()}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        env_path=env_path,
        env_values=_load_env_file(env_path),
        today_utc=today,
    )

    # Mock keyring to return a fresh token
    token_time = datetime(2026, 4, 16, 0, 0, 0, tzinfo=UTC)
    with patch("iatb.broker.token_manager.keyring.get_password") as mock_get:
        mock_get.side_effect = [
            "keyring-token",  # access_token
            token_time.isoformat(),  # timestamp
            "keyring-token",  # for is_token_fresh check
        ]
        with patch("iatb.broker.token_manager.datetime") as mock_dt:
            now_time = datetime(2026, 4, 16, 0, 20, 0, tzinfo=UTC)
            mock_dt.now.return_value = now_time
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.combine = datetime.combine

            result = manager.resolve_saved_access_token()
            assert result == "keyring-token"  # Should prefer keyring over env


def test_persist_session_tokens_only_keyring(tmp_path: Path) -> None:
    """Test that persist_session_tokens works with only keyring (no env_path)."""
    today = datetime.now(UTC).date()
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        today_utc=today,
    )

    with patch.object(manager, "store_access_token") as mock_store:
        with patch("iatb.broker.token_manager.keyring.set_password") as mock_set:
            result = manager.persist_session_tokens(
                access_token="access-test",  # noqa: S106
                request_token="req-test",  # noqa: S106
            )
            # Should return None when no env_path is configured
            assert result is None
            # Should still store in keyring
            mock_store.assert_called_once_with("access-test")  # noqa: S105
            # Should set request token and date
            assert mock_set.call_count >= 2  # At least request token and date
