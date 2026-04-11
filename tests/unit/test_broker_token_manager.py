"""Unit tests for ZerodhaTokenManager."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz
from iatb.broker.token_manager import ZerodhaTokenManager

_IST = pytz.timezone("Asia/Kolkata")

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_keyring() -> Iterator[MagicMock]:
    """Mock keyring module."""
    with patch("iatb.broker.token_manager.keyring") as mock:
        yield mock


@pytest.fixture
def mock_kite_connect() -> Iterator[MagicMock]:
    """Mock KiteConnect class."""
    with patch("iatb.broker.token_manager.KiteConnect") as mock:
        yield mock


@pytest.fixture
def mock_pyotp() -> Iterator[MagicMock]:
    """Mock pyotp module."""
    with patch("iatb.broker.token_manager.pyotp") as mock:
        yield mock


@pytest.fixture
def token_manager(mock_keyring: MagicMock) -> ZerodhaTokenManager:
    """Create token manager instance."""
    return ZerodhaTokenManager()


def test_init(token_manager: ZerodhaTokenManager) -> None:
    """Test token manager initialization."""
    assert token_manager._api_key is None
    assert token_manager._api_secret is None
    assert token_manager._totp_secret is None


def test_load_credentials(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test loading credentials from keyring."""
    mock_keyring.get_password.side_effect = [
        "test_api_key",
        "test_api_secret",
        "test_totp_secret",
    ]

    token_manager._load_credentials()

    assert token_manager._api_key == "test_api_key"
    assert token_manager._api_secret == "test_api_secret"
    assert token_manager._totp_secret == "test_totp_secret"

    mock_keyring.get_password.assert_any_call("iatb", "zerodha_api_key")
    mock_keyring.get_password.assert_any_call("iatb", "zerodha_api_secret")
    mock_keyring.get_password.assert_any_call("iatb", "zerodha_totp_secret")


def test_is_token_fresh_no_api_key(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test token freshness check when API key is missing."""
    mock_keyring.get_password.side_effect = [None, None, None]

    result = token_manager.is_token_fresh()

    assert result is False


def test_is_token_fresh_no_token(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test token freshness check when token is missing."""
    mock_keyring.get_password.side_effect = [
        "api_key",
        "api_secret",
        "totp_secret",
        None,
        None,
    ]

    result = token_manager.is_token_fresh()

    assert result is False


def test_is_token_fresh_no_timestamp(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test token freshness check when timestamp is missing."""
    mock_keyring.get_password.side_effect = [
        "api_key",
        "api_secret",
        "totp_secret",
        "access_token",
        None,
    ]

    result = token_manager.is_token_fresh()

    assert result is False


def test_is_token_fresh_invalid_timestamp(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test token freshness check with invalid timestamp."""
    mock_keyring.get_password.side_effect = [
        "api_key",
        "api_secret",
        "totp_secret",
        "access_token",
        "invalid-timestamp",
    ]

    result = token_manager.is_token_fresh()

    assert result is False


def test_is_token_fresh_token_expired_yesterday(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test token freshness check when token expired yesterday."""
    now_utc = datetime.now(UTC)
    stored_time = now_utc - timedelta(days=1, hours=8)

    mock_keyring.get_password.side_effect = [
        "api_key",
        "api_secret",
        "totp_secret",
        "access_token",
        stored_time.isoformat(),
    ]

    result = token_manager.is_token_fresh()

    assert result is False


def test_get_login_url(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test getting login URL."""
    mock_keyring.get_password.return_value = "test_api_key"

    url = token_manager.get_login_url()

    assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=test_api_key"
    mock_keyring.get_password.assert_any_call("iatb", "zerodha_api_key")


def test_get_login_url_no_api_key(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test getting login URL when API key is missing."""
    mock_keyring.get_password.return_value = None

    with pytest.raises(RuntimeError, match="API key not found in keyring"):
        token_manager.get_login_url()


def test_exchange_request_token_success(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
    mock_kite_connect: MagicMock,
) -> None:
    """Test successful request token exchange."""
    mock_keyring.get_password.side_effect = ["api_key", "api_secret", "totp_secret"]
    mock_kite_instance = MagicMock()
    mock_kite_instance.generate_session.return_value = {
        "access_token": "test_access_token",
        "user_id": "test_user",
    }
    mock_kite_connect.return_value = mock_kite_instance

    result = token_manager.exchange_request_token("test_request_token")

    assert result == "test_access_token"
    mock_kite_instance.generate_session.assert_called_once_with(
        request_token="test_request_token",
        api_secret="api_secret",
    )


def test_exchange_request_token_no_credentials(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test request token exchange with missing credentials."""
    mock_keyring.get_password.side_effect = [None, None, None]

    with pytest.raises(RuntimeError, match="API credentials not found"):
        token_manager.exchange_request_token("test_request_token")


def test_exchange_request_token_api_error(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
    mock_kite_connect: MagicMock,
) -> None:
    """Test request token exchange with API error."""
    mock_keyring.get_password.side_effect = ["api_key", "api_secret", "totp_secret"]
    mock_kite_instance = MagicMock()
    mock_kite_instance.generate_session.side_effect = Exception("API Error")
    mock_kite_connect.return_value = mock_kite_instance

    with pytest.raises(RuntimeError, match="Token exchange failed"):
        token_manager.exchange_request_token("test_request_token")


def test_exchange_request_token_no_access_token(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
    mock_kite_connect: MagicMock,
) -> None:
    """Test request token exchange with no access token in response."""
    mock_keyring.get_password.side_effect = ["api_key", "api_secret", "totp_secret"]
    mock_kite_instance = MagicMock()
    mock_kite_instance.generate_session.return_value = {}
    mock_kite_connect.return_value = mock_kite_instance

    with pytest.raises(RuntimeError, match="No access_token in KiteConnect response"):
        token_manager.exchange_request_token("test_request_token")


def test_store_access_token(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test storing access token."""
    token_manager.store_access_token("test_token")

    assert mock_keyring.set_password.call_count == 2
    mock_keyring.set_password.assert_any_call("iatb", "zerodha_access_token", "test_token")

    timestamp_call = mock_keyring.set_password.call_args_list[1]
    assert timestamp_call[0][0] == "iatb"
    assert timestamp_call[0][1] == "zerodha_token_timestamp"
    assert "+00:00" in timestamp_call[0][2] or "Z" in timestamp_call[0][2]  # UTC timestamp


def test_generate_totp_success(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
    mock_pyotp: MagicMock,
) -> None:
    """Test successful TOTP generation."""
    mock_keyring.get_password.return_value = "test_totp_secret"
    mock_totp_instance = MagicMock()
    mock_totp_instance.now.return_value = "123456"
    mock_pyotp.TOTP.return_value = mock_totp_instance

    result = token_manager.generate_totp()

    assert result == "123456"
    mock_pyotp.TOTP.assert_called_once_with("test_totp_secret")
    mock_totp_instance.now.assert_called_once()


def test_generate_totp_no_secret(
    token_manager: ZerodhaTokenManager,
    mock_keyring: MagicMock,
) -> None:
    """Test TOTP generation when secret is missing."""
    mock_keyring.get_password.return_value = None

    with pytest.raises(RuntimeError, match="TOTP secret not found in keyring"):
        token_manager.generate_totp()


def test_is_fresh_stored_time_before_expiry_today(
    token_manager: ZerodhaTokenManager,
) -> None:
    """Test _is_fresh when stored time is before today's expiry."""
    now_utc = datetime.now(UTC)
    now_ist = now_utc.astimezone(_IST)

    if now_ist.time() >= time(6, 0):
        # After 6 AM: store at 5 AM today (before today's 6 AM)
        stored_time = now_ist.replace(hour=5, minute=0, second=0, microsecond=0)
    else:
        # Before 6 AM: store at 5 AM yesterday (before yesterday's 6 AM)
        stored_time = now_ist - timedelta(days=1, hours=1)
        stored_time = stored_time.replace(hour=5, minute=0, second=0, microsecond=0)

    result = token_manager._is_fresh(stored_time)

    assert result is False


def test_is_fresh_stored_time_after_expiry_today(
    token_manager: ZerodhaTokenManager,
) -> None:
    """Test _is_fresh when stored time is after today's expiry."""
    now_utc = datetime.now(UTC)
    now_ist = now_utc.astimezone(_IST)
    expiry_today = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)

    stored_time = expiry_today + timedelta(hours=1)

    result = token_manager._is_fresh(stored_time)

    assert result is True


def test_is_fresh_stored_time_naive_datetime(
    token_manager: ZerodhaTokenManager,
) -> None:
    """Test _is_fresh with naive datetime (no timezone)."""
    now_utc = datetime.now(UTC)
    now_ist = now_utc.astimezone(_IST)

    if now_ist.time() >= time(6, 0):
        # After 6 AM: store at 7 AM today (after today's 6 AM)
        stored_time = (now_utc + timedelta(hours=1)).replace(tzinfo=None)
    else:
        # Before 6 AM: store at 7 AM today (will be after today's 6 AM)
        stored_time = now_ist.replace(hour=7, minute=0, second=0, microsecond=0)
        stored_time = stored_time.astimezone(UTC).replace(tzinfo=None)

    result = token_manager._is_fresh(stored_time)

    assert result is True
