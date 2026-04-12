"""Tests for ZerodhaTokenManager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

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
