"""Tests for ZerodhaTokenManager."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

import keyring
import pytest
from iatb.broker.token_manager import ZerodhaTokenManager, _get_next_expiry_utc


@pytest.fixture
def mock_http_post() -> MagicMock:
    """Mock HTTP POST function."""
    return MagicMock(return_value={"data": {"access_token": "test_access_token"}})


@pytest.fixture
def token_manager(mock_http_post: MagicMock) -> ZerodhaTokenManager:
    """Create token manager with mocked HTTP."""
    return ZerodhaTokenManager(
        api_key="test_api_key",
        api_secret="test_api_secret",  # noqa: S106
        totp_secret="JBSWY3DPEHPK3PXP",  # noqa: S106
        http_post=mock_http_post,
    )


def test_init_token_manager(token_manager: ZerodhaTokenManager) -> None:
    """Test token manager initialization."""
    assert token_manager._api_key == "test_api_key"
    assert token_manager._api_secret == "test_api_secret"  # noqa: S105
    assert token_manager._totp_secret == "JBSWY3DPEHPK3PXP"  # noqa: S105


def test_is_token_fresh_no_token(token_manager: ZerodhaTokenManager) -> None:
    """Test is_token_fresh returns False when no token stored."""
    with patch.object(keyring, "get_password", return_value=None):
        assert token_manager.is_token_fresh() is False


def test_is_token_fresh_no_timestamp(token_manager: ZerodhaTokenManager) -> None:
    """Test is_token_fresh returns False when no timestamp stored."""
    with patch.object(keyring, "get_password", side_effect=["test_token", None]):
        assert token_manager.is_token_fresh() is False


def test_is_token_fresh_invalid_timestamp(token_manager: ZerodhaTokenManager) -> None:
    """Test is_token_fresh returns False with invalid timestamp."""
    with patch.object(keyring, "get_password", side_effect=["test_token", "invalid"]):
        assert token_manager.is_token_fresh() is False


def test_is_token_fresh_expired(token_manager: ZerodhaTokenManager) -> None:
    """Test is_token_fresh returns False for expired token."""
    old_time = datetime.now(UTC) - timedelta(days=2)
    with patch.object(
        keyring,
        "get_password",
        side_effect=["test_token", old_time.isoformat()],
    ):
        assert token_manager.is_token_fresh() is False


def test_is_token_fresh_valid(token_manager: ZerodhaTokenManager) -> None:
    """Test is_token_fresh returns True for valid token."""
    # Create token time that's recent and should be fresh
    # Use a fixed time to ensure consistency across test runs
    # Token created at 0:00 AM UTC (5:30 AM IST), before 6 AM IST expiry
    token_time = datetime(2026, 4, 12, 0, 0, 0, tzinfo=UTC)  # 0:00 AM UTC = 5:30 AM IST
    with patch.object(
        keyring,
        "get_password",
        side_effect=["test_token", token_time.isoformat()],
    ):
        # Now time is 0:20 AM UTC (5:50 AM IST), still before 6 AM IST expiry
        now_time = datetime(2026, 4, 12, 0, 20, 0, tzinfo=UTC)
        with patch("iatb.broker.token_manager.datetime") as mock_dt:
            # Only mock now(), preserve other datetime methods
            mock_dt.now.return_value = now_time
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.combine = datetime.combine
            assert token_manager.is_token_fresh() is True


def test_get_login_url(token_manager: ZerodhaTokenManager) -> None:
    """Test get_login_url returns correct URL."""
    url = token_manager.get_login_url()
    assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=test_api_key"


def test_exchange_request_token_success(
    token_manager: ZerodhaTokenManager,
    mock_http_post: MagicMock,
) -> None:
    """Test successful request token exchange."""
    result = token_manager.exchange_request_token("test_request_token")
    assert result == "test_access_token"
    mock_http_post.assert_called_once()


def test_exchange_request_token_no_access_token(
    token_manager: ZerodhaTokenManager,
) -> None:
    """Test exchange_request_token raises error when no access token in response."""
    mock_http_post = MagicMock(return_value={"data": {}})
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        http_post=mock_http_post,
    )
    with pytest.raises(ValueError, match="No access_token in API response"):
        manager.exchange_request_token("test_request_token")


def test_store_access_token(token_manager: ZerodhaTokenManager) -> None:
    """Test storing access token."""
    with patch.object(keyring, "set_password") as mock_set:
        token_manager.store_access_token("new_token")
        assert mock_set.call_count == 2


def test_generate_totp_success(token_manager: ZerodhaTokenManager) -> None:
    """Test TOTP generation."""
    totp = token_manager._generate_totp()
    assert isinstance(totp, str)
    assert len(totp) == 6
    assert totp.isdigit()


def test_generate_totp_no_secret() -> None:
    """Test TOTP generation fails without secret."""
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        totp_secret=None,
    )
    with pytest.raises(ValueError, match="TOTP secret not configured"):
        manager._generate_totp()


def test_get_totp(token_manager: ZerodhaTokenManager) -> None:
    """Test get_totp wrapper."""
    totp = token_manager.get_totp()
    assert isinstance(totp, str)
    assert len(totp) == 6


def test_clear_token(token_manager: ZerodhaTokenManager) -> None:
    """Test clearing stored token."""
    with patch.object(keyring, "delete_password") as mock_delete:
        token_manager.clear_token()
        assert mock_delete.call_count == 2


def test_clear_token_handles_error(token_manager: ZerodhaTokenManager) -> None:
    """Test clear_token handles keyring errors gracefully."""
    with patch.object(
        keyring,
        "delete_password",
        side_effect=keyring.errors.PasswordDeleteError(),
    ):
        # Should not raise exception
        token_manager.clear_token()


def test_get_next_expiry_utc_same_day() -> None:
    """Test expiry calculation for same day before 6 AM."""
    # 0:00 UTC = 5:30 AM IST (before 6 AM)
    token_time = datetime(2026, 4, 11, 0, 0, tzinfo=UTC)
    expiry = _get_next_expiry_utc(token_time)
    expected = datetime(2026, 4, 11, 0, 30, tzinfo=UTC)  # 6 AM IST = 0:30 UTC
    assert expiry == expected


def test_get_next_expiry_utc_next_day() -> None:
    """Test expiry calculation for after 6 AM."""
    token_time = datetime(2026, 4, 11, 8, 0, tzinfo=UTC)
    expiry = _get_next_expiry_utc(token_time)
    expected = datetime(2026, 4, 12, 0, 30, tzinfo=UTC)  # Next day 6 AM IST
    assert expiry == expected


def test_default_http_post() -> None:
    """Test default HTTP POST implementation."""
    from iatb.broker.token_manager import _default_http_post

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"access_token": "test"}}'
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _default_http_post(
            "https://test.com",
            {"Content-Type": "application/json"},
            b"test_body",
        )
        assert result == {"data": {"access_token": "test"}}


def test_exchange_request_token_url_encodes_payload() -> None:
    """Test that exchange_request_token properly URL-encodes the payload."""
    # Test with special characters that need encoding
    mock_http_post = MagicMock(return_value={"data": {"access_token": "test_token"}})

    # API key with special characters
    api_key = "test+key=with special&chars"
    api_secret = "secret+value=with&spaces"  # noqa: S105
    request_token = "token+with=special&chars"  # noqa: S105

    manager = ZerodhaTokenManager(
        api_key=api_key,
        api_secret=api_secret,
        http_post=mock_http_post,
    )

    manager.exchange_request_token(request_token)

    # Verify HTTP POST was called
    assert mock_http_post.called

    # Get the body that was passed to http_post
    call_args = mock_http_post.call_args
    body = call_args[0][2]  # Third argument is the body

    # Decode and verify proper URL encoding
    body_str = body.decode("utf-8")
    parsed = parse_qs(body_str)

    # Verify all parameters are present and properly decoded
    assert "api_key" in parsed
    assert parsed["api_key"][0] == api_key

    assert "request_token" in parsed
    assert parsed["request_token"][0] == request_token

    # The checksum should be present (it's a hash, so just check it exists)
    assert "checksum" in parsed
    assert len(parsed["checksum"][0]) == 64  # SHA256 hex digest length


def test_exchange_request_token_handles_plus_equals() -> None:
    """Test that + and = characters are properly encoded in the payload."""
    mock_http_post = MagicMock(return_value={"data": {"access_token": "test_token"}})

    # Values that specifically test + and = encoding
    api_key = "key+test=value"
    request_token = "token+request=code"  # noqa: S105

    manager = ZerodhaTokenManager(
        api_key=api_key,
        api_secret="test_secret",  # noqa: S106
        http_post=mock_http_post,
    )

    manager.exchange_request_token(request_token)

    # Get the body
    call_args = mock_http_post.call_args
    body = call_args[0][2]
    body_str = body.decode("utf-8")

    # Verify + is encoded as %2B and = is encoded as %3D (except the delimiter =)
    # The body should have proper encoding
    parsed = parse_qs(body_str)

    # The values should be correctly decoded back
    assert parsed["api_key"][0] == api_key
    assert parsed["request_token"][0] == request_token


def test_exchange_request_token_handles_spaces() -> None:
    """Test that spaces are properly encoded as + or %20."""
    mock_http_post = MagicMock(return_value={"data": {"access_token": "test_token"}})

    api_key = "key with spaces"
    request_token = "token with spaces"  # noqa: S105

    manager = ZerodhaTokenManager(
        api_key=api_key,
        api_secret="test_secret",  # noqa: S106
        http_post=mock_http_post,
    )

    manager.exchange_request_token(request_token)

    # Get the body
    call_args = mock_http_post.call_args
    body = call_args[0][2]
    body_str = body.decode("utf-8")
    parsed = parse_qs(body_str)

    # Spaces should be preserved when decoded
    assert parsed["api_key"][0] == api_key
    assert parsed["request_token"][0] == request_token


def test_exchange_request_token_body_is_bytes() -> None:
    """Test that the body is properly encoded as bytes."""
    mock_http_post = MagicMock(return_value={"data": {"access_token": "test_token"}})

    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        http_post=mock_http_post,
    )

    manager.exchange_request_token("test_token")

    # Get the body
    call_args = mock_http_post.call_args
    body = call_args[0][2]

    # Verify body is bytes
    assert isinstance(body, bytes)

    # Verify it can be decoded
    body_str = body.decode("utf-8")
    assert isinstance(body_str, str)


# Tests for new methods added in unification


def test_get_access_token_from_keyring(token_manager: ZerodhaTokenManager) -> None:
    """Test get_access_token retrieves fresh token from keyring."""
    token_time = datetime(2026, 4, 16, 0, 0, 0, tzinfo=UTC)
    with patch.object(
        keyring,
        "get_password",
        side_effect=["fresh_token", token_time.isoformat(), "fresh_token"],
    ):
        with patch("iatb.broker.token_manager.datetime") as mock_dt:
            now_time = datetime(2026, 4, 16, 0, 20, 0, tzinfo=UTC)
            mock_dt.now.return_value = now_time
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.combine = datetime.combine

            token = token_manager.get_access_token()
            assert token == "fresh_token"  # noqa: S105


def test_get_access_token_from_env_var_zerodha() -> None:
    """Test get_access_token retrieves from ZERODHA_ACCESS_TOKEN env var."""
    with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": "env_token"}):  # noqa: S105
        with patch.object(keyring, "get_password", return_value=None):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            token = manager.get_access_token()
            assert token == "env_token"  # noqa: S105


def test_get_access_token_from_env_var_kite_alias() -> None:
    """Test get_access_token retrieves from KITE_ACCESS_TOKEN env var (alias)."""
    with patch.dict(os.environ, {"KITE_ACCESS_TOKEN": "kite_token"}):  # noqa: S105
        with patch.object(keyring, "get_password", return_value=None):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            token = manager.get_access_token()
            assert token == "kite_token"  # noqa: S105


def test_get_access_token_from_env_file(tmp_path: Path) -> None:
    """Test get_access_token retrieves from .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("ZERODHA_ACCESS_TOKEN=env_file_token\n")  # noqa: S105

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with patch.object(keyring, "get_password", return_value=None):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            token = manager.get_access_token()
            assert token == "env_file_token"  # noqa: S105


def test_get_access_token_no_token_available() -> None:
    """Test get_access_token returns None when no token available."""
    with patch.object(keyring, "get_password", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            manager = ZerodhaTokenManager(
                api_key="test_key",
                api_secret="test_secret",  # noqa: S106
            )
            token = manager.get_access_token()
            assert token is None


def test_get_access_token_precedence_keyring_first() -> None:
    """Test that keyring has precedence over env vars."""
    token_time = datetime(2026, 4, 16, 0, 0, 0, tzinfo=UTC)
    with patch.object(
        keyring,
        "get_password",
        side_effect=["keyring_token", token_time.isoformat(), "keyring_token"],
    ):
        with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": "env_token"}):
            with patch("iatb.broker.token_manager.datetime") as mock_dt:
                now_time = datetime(2026, 4, 16, 0, 20, 0, tzinfo=UTC)
                mock_dt.now.return_value = now_time
                mock_dt.fromisoformat = datetime.fromisoformat
                mock_dt.combine = datetime.combine

                manager = ZerodhaTokenManager(
                    api_key="test_key",
                    api_secret="test_secret",  # noqa: S106
                )
                token = manager.get_access_token()
                assert token == "keyring_token"  # noqa: S105


def test_get_kite_client_with_provided_token() -> None:
    """Test get_kite_client with explicitly provided token."""
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )

    mock_kite = MagicMock()
    with patch("builtins.__import__") as mock_import:
        mock_module = MagicMock()
        mock_module.KiteConnect = MagicMock(return_value=mock_kite)
        mock_import.return_value = mock_module

        client = manager.get_kite_client(access_token="provided_token")  # noqa: S106

        assert client == mock_kite
        mock_module.KiteConnect.assert_called_once_with(
            api_key="test_key",
            access_token="provided_token",  # noqa: S106
        )


def test_get_kite_client_auto_retrieves_token() -> None:
    """Test get_kite_client automatically retrieves token."""
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )

    mock_kite = MagicMock()
    with patch.dict(os.environ, {"ZERODHA_ACCESS_TOKEN": "auto_token"}):
        with patch.object(keyring, "get_password", return_value=None):
            with patch("builtins.__import__") as mock_import:
                mock_module = MagicMock()
                mock_module.KiteConnect = MagicMock(return_value=mock_kite)
                mock_import.return_value = mock_module

                client = manager.get_kite_client()

                assert client == mock_kite
                mock_module.KiteConnect.assert_called_once_with(
                    api_key="test_key",
                    access_token="auto_token",  # noqa: S106
                )


def test_get_kite_client_no_token_available() -> None:
    """Test get_kite_client raises error when no token available."""
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )

    with patch.object(keyring, "get_password", return_value=None):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Access token not available"):
                manager.get_kite_client()


def test_get_kite_client_kiteconnect_not_installed() -> None:
    """Test get_kite_client raises ImportError when kiteconnect not installed."""
    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )

    with patch("builtins.__import__") as mock_import:
        mock_import.side_effect = ModuleNotFoundError("kiteconnect")

        with pytest.raises(ImportError, match="kiteconnect module is required"):
            manager.get_kite_client(access_token="test_token")  # noqa: S106


def test_resolve_env_path_current_dir(tmp_path: Path) -> None:
    """Test _resolve_env_path finds .env in current directory."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST=value\n")

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = ZerodhaTokenManager._resolve_env_path()
        assert result == env_file


def test_resolve_env_path_parent_dir(tmp_path: Path) -> None:
    """Test _resolve_env_path finds .env in parent directory."""
    env_file = tmp_path / ".env"
    env_file.write_text("TEST=value\n")
    child_dir = tmp_path / "child"
    child_dir.mkdir()

    with patch("pathlib.Path.cwd", return_value=child_dir):
        result = ZerodhaTokenManager._resolve_env_path()
        assert result == env_file


def test_resolve_env_path_not_found(tmp_path: Path) -> None:
    """Test _resolve_env_path returns None when .env not found."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        result = ZerodhaTokenManager._resolve_env_path()
        assert result is None


def test_load_env_file_success(tmp_path: Path) -> None:
    """Test _load_env_file parses .env file correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# Comment
KEY1=value1
KEY2="value2"
KEY3='value3'
KEY4=value with spaces
"""
    )

    result = ZerodhaTokenManager._load_env_file(env_file)

    assert result == {
        "KEY1": "value1",
        "KEY2": "value2",
        "KEY3": "value3",
        "KEY4": "value with spaces",
    }


def test_load_env_file_empty(tmp_path: Path) -> None:
    """Test _load_env_file returns empty dict for non-existent file."""
    env_file = tmp_path / "nonexistent.env"
    result = ZerodhaTokenManager._load_env_file(env_file)
    assert result == {}


def test_clear_env_token(tmp_path: Path) -> None:
    """Test _clear_env_token removes access token from .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
ZERODHA_API_KEY=test_key
ZERODHA_ACCESS_TOKEN=secret_token
ZERODHA_API_SECRET=test_secret
"""
    )

    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )
    manager._clear_env_token(env_file)

    content = env_file.read_text()
    assert "ZERODHA_ACCESS_TOKEN" not in content
    assert "ZERODHA_API_KEY" in content
    assert "ZERODHA_API_SECRET" in content


def test_clear_env_token_kite_alias(tmp_path: Path) -> None:
    """Test _clear_env_token removes KITE_ACCESS_TOKEN from .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
KITE_API_KEY=test_key
KITE_ACCESS_TOKEN=secret_token
KITE_API_SECRET=test_secret
"""
    )

    manager = ZerodhaTokenManager(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
    )
    manager._clear_env_token(env_file)

    content = env_file.read_text()
    assert "KITE_ACCESS_TOKEN" not in content
    assert "KITE_API_KEY" in content
    assert "KITE_API_SECRET" in content


def test_clear_token_removes_from_env_file(tmp_path: Path) -> None:
    """Test clear_token removes token from both keyring and .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("ZERODHA_ACCESS_TOKEN=secret_token\n")

    with patch("pathlib.Path.cwd", return_value=tmp_path):
        manager = ZerodhaTokenManager(
            api_key="test_key",
            api_secret="test_secret",  # noqa: S106
        )

        with patch.object(keyring, "delete_password") as mock_delete:
            manager.clear_token()
            assert mock_delete.call_count == 2  # Two keyring deletes

        # Verify .env file was updated
        content = env_file.read_text()
        assert "ZERODHA_ACCESS_TOKEN" not in content
