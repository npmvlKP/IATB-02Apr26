"""Tests for IATBApi."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from iatb.api import IATBApi, create_api
from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError


@pytest.fixture
def mock_token_manager() -> ZerodhaTokenManager:
    """Create mock token manager."""
    manager = MagicMock(spec=ZerodhaTokenManager)
    manager._api_key = "test_key"
    manager.is_token_fresh.return_value = True
    return manager


@pytest.fixture
def api_instance(mock_token_manager: ZerodhaTokenManager) -> IATBApi:
    """Create API instance with mocked token manager."""
    return IATBApi(token_manager=mock_token_manager)


def test_api_init_no_token_manager() -> None:
    """Test API initialization without token manager."""
    api = IATBApi()
    assert api._token_manager is None


def test_api_init_with_token_manager(api_instance: IATBApi) -> None:
    """Test API initialization with token manager."""
    assert api_instance._token_manager is not None


def test_init_kite_no_token_manager() -> None:
    """Test _init_kite without token manager."""
    api = IATBApi()
    with pytest.raises(ConfigError, match="Token manager not configured"):
        api._init_kite()


def test_init_kite_expired_token(api_instance: IATBApi) -> None:
    """Test _init_kite with expired token."""
    api_instance._token_manager.is_token_fresh.return_value = False
    result = api_instance._init_kite()
    assert result["status"] == "error"
    assert result["detail"] == "relogin_required"
    assert "expired" in result["message"]


def test_init_kite_no_stored_token(api_instance: IATBApi) -> None:
    """Test _init_kite with no stored token."""
    api_instance._token_manager.is_token_fresh.return_value = True
    with patch("keyring.get_password", return_value=None):
        result = api_instance._init_kite()
        assert result["status"] == "error"
        assert "No access token found" in result["message"]


def test_init_kite_success(api_instance: IATBApi) -> None:
    """Test successful _init_kite."""
    api_instance._token_manager.is_token_fresh.return_value = True
    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect") as mock_kite:
            result = api_instance._init_kite()
            assert result["status"] == "success"
            assert result["detail"] == "kite_initialized"
            mock_kite.assert_called_once()


def test_create_kite_client_no_token_manager() -> None:
    """Test _create_kite_client without token manager."""
    api = IATBApi()
    with pytest.raises(ConfigError, match="Token manager not configured"):
        api._create_kite_client("test_token")


def test_create_kite_client_success(api_instance: IATBApi) -> None:
    """Test successful KiteConnect client creation."""
    with patch("kiteconnect.KiteConnect") as mock_kite:
        mock_instance = MagicMock()
        mock_kite.return_value = mock_instance
        result = api_instance._create_kite_client("test_token")  # noqa: S106
        assert result == mock_instance
        mock_kite.assert_called_once_with(
            api_key="test_key",
            access_token="test_token",  # noqa: S106
        )


def test_get_kite_client_not_initialized(api_instance: IATBApi) -> None:
    """Test get_kite_client when client not initialized."""
    with pytest.raises(ConfigError, match="KiteConnect client not initialized"):
        api_instance.get_kite_client()


def test_get_kite_client_success(api_instance: IATBApi) -> None:
    """Test successful get_kite_client."""
    mock_client = MagicMock()
    api_instance._kite_client = mock_client
    result = api_instance.get_kite_client()
    assert result == mock_client


def test_health_check_unhealthy(api_instance: IATBApi) -> None:
    """Test health_check returns unhealthy."""
    api_instance._token_manager.is_token_fresh.return_value = False
    result = api_instance.health_check()
    assert result["status"] == "unhealthy"
    assert result["detail"] == "relogin_required"


def test_health_check_healthy(api_instance: IATBApi) -> None:
    """Test health_check returns healthy."""
    api_instance._token_manager.is_token_fresh.return_value = True
    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect"):
            result = api_instance.health_check()
            assert result["status"] == "healthy"
            assert result["detail"] == "operational"


def test_create_api() -> None:
    """Test create_api factory function."""
    api = create_api(
        api_key="test_key",
        api_secret="test_secret",  # noqa: S106
        totp_secret="test_totp",  # noqa: S106
    )
    assert isinstance(api, IATBApi)
    assert api._token_manager is not None
