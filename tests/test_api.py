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


def test_broker_status_relogin_required(api_instance: IATBApi) -> None:
    """Test broker_status with expired token."""
    api_instance._token_manager.is_token_fresh.return_value = False
    result = api_instance.broker_status()
    assert result["status"] == "relogin_required"
    assert result["uid"] is None
    assert result["balance"] is None


def test_broker_status_connected(api_instance: IATBApi) -> None:
    """Test broker_status with valid connection."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.profile.return_value = {"user_id": "ABC123"}
    mock_kite.margins.return_value = {"equity": {"net": 100000.0}}

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.broker_status()
            assert result["status"] == "connected"
            assert result["uid"] == "ABC123"
            assert result["balance"] == 100000.0


def test_broker_status_error(api_instance: IATBApi) -> None:
    """Test broker_status with error."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.profile.side_effect = Exception("Network error")

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.broker_status()
            assert result["status"] == "error"
            assert result["uid"] is None
            assert result["balance"] is None


def test_get_ohlcv_relogin_required(api_instance: IATBApi) -> None:
    """Test get_ohlcv with expired token."""
    api_instance._token_manager.is_token_fresh.return_value = False
    result = api_instance.get_ohlcv("RELIANCE")
    assert result["status"] == "error"
    assert result["ticker"] == "RELIANCE"
    assert result["data"] is None


def test_get_ohlcv_success(api_instance: IATBApi) -> None:
    """Test get_ohlcv with valid data."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = [
        {
            "date": "2026-01-01",
            "open": 1000,
            "high": 1100,
            "low": 950,
            "close": 1050,
            "volume": 100000,
        }
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.get_ohlcv("RELIANCE")
            assert result["status"] == "success"
            assert result["ticker"] == "RELIANCE"
            assert result["data"] is not None
            assert result["count"] == 1


def test_get_ohlcv_instrument_not_found(api_instance: IATBApi) -> None:
    """Test get_ohlcv when instrument not found."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = []

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.get_ohlcv("RELIANCE")
            assert result["status"] == "error"
            assert "not found" in result["message"].lower()


def test_get_ohlcv_error(api_instance: IATBApi) -> None:
    """Test get_ohlcv with error."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.side_effect = Exception("Network error")

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.get_ohlcv("RELIANCE")
            assert result["status"] == "error"
            assert result["data"] is None


def test_instrument_cache_populated_on_first_lookup(api_instance: IATBApi) -> None:
    """Test that instrument cache is populated on first lookup."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
        {"tradingsymbol": "TCS", "instrument_token": "789012"},
    ]

    with patch("keyring.get_password", return_value="mock_access_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite
            result = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert result == "123456"
            assert len(api_instance._instrument_cache) == 2
            assert api_instance._instrument_cache["RELIANCE"] == "123456"
            assert api_instance._instrument_cache["TCS"] == "789012"


def test_instrument_cache_used_on_subsequent_lookups(api_instance: IATBApi) -> None:
    """Test that cache is used on subsequent lookups."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite
            # First lookup - should call instruments()
            lookup1 = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert lookup1 == "123456"
            assert mock_kite.instruments.call_count == 1

            # Second lookup - should use cache, not call instruments() again
            lookup2 = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert lookup2 == "123456"
            assert mock_kite.instruments.call_count == 1


def test_instrument_cache_clear(api_instance: IATBApi) -> None:
    """Test that instrument cache can be cleared."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]

    with patch("keyring.get_password", return_value="mock_access_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite
            # Populate cache
            _ = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert len(api_instance._instrument_cache) == 1

            # Clear cache
            api_instance.clear_instrument_cache()
            assert len(api_instance._instrument_cache) == 0

            # Next lookup should repopulate cache
            _ = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert len(api_instance._instrument_cache) == 1
            assert mock_kite.instruments.call_count == 2


def test_instrument_cache_handles_missing_tokens(api_instance: IATBApi) -> None:
    """Test that cache handles instruments with None tokens."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
        {"tradingsymbol": "INVALID", "instrument_token": None},
        {"tradingsymbol": "NO_TOKEN", "instrument_token": ""},
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite
            cached_result = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert cached_result == "123456"
            # Only valid instruments should be cached
            assert "RELIANCE" in api_instance._instrument_cache
            assert "INVALID" not in api_instance._instrument_cache
            assert "NO_TOKEN" not in api_instance._instrument_cache


def test_instrument_cache_returns_none_for_not_found(api_instance: IATBApi) -> None:
    """Test that cache returns None for instruments not in cache."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite
            lookup_result = api_instance._ensure_instrument_token(mock_kite, "NOTFOUND", None)
            assert lookup_result is None
            assert "NOTFOUND" not in api_instance._instrument_cache


def test_get_ohlcv_uses_cached_instrument_token(api_instance: IATBApi) -> None:
    """Test that get_ohlcv uses cached instrument token."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = [
        {
            "date": "2026-01-01",
            "open": 1000,
            "high": 1100,
            "low": 950,
            "close": 1050,
            "volume": 100000,
        }
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            # First call - populates cache
            result1 = api_instance.get_ohlcv("RELIANCE")
            assert result1["status"] == "success"
            assert mock_kite.instruments.call_count == 1

            # Second call - uses cache
            result2 = api_instance.get_ohlcv("RELIANCE")
            assert result2["status"] == "success"
            # instruments() should not be called again
            assert mock_kite.instruments.call_count == 1


def test_get_ohlcv_with_custom_date_range(api_instance: IATBApi) -> None:
    """Test get_ohlcv with custom date range."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = [
        {
            "date": "2026-01-01",
            "open": 1000,
            "high": 1100,
            "low": 950,
            "close": 1050,
            "volume": 100000,
        }
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.get_ohlcv(
                "RELIANCE",
                from_date="2026-01-01",
                to_date="2026-01-31",
            )
            assert result["status"] == "success"
            mock_kite.historical_data.assert_called_once_with(
                instrument_token="123456",
                from_date="2026-01-01",
                to_date="2026-01-31",
                interval="day",
            )


def test_get_ohlcv_with_instrument_token_provided(api_instance: IATBApi) -> None:
    """Test get_ohlcv when instrument token is provided directly."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.historical_data.return_value = [
        {
            "date": "2026-01-01",
            "open": 1000,
            "high": 1100,
            "low": 950,
            "close": 1050,
            "volume": 100000,
        }
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            # Provide token directly - should not call instruments()
            result = api_instance.get_ohlcv("RELIANCE", instrument_token="789012")
            assert result["status"] == "success"
            mock_kite.instruments.assert_not_called()
            mock_kite.historical_data.assert_called_once()


def test_get_ohlcv_with_different_intervals(api_instance: IATBApi) -> None:
    """Test get_ohlcv with different candle intervals."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = []

    intervals = ["day", "5minute", "15minute", "30minute", "60minute", "week"]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            for interval in intervals:
                result = api_instance.get_ohlcv("RELIANCE", interval=interval)
                assert result["status"] == "success"
                # Verify interval was passed correctly
                call_kwargs = mock_kite.historical_data.call_args[1]
                assert call_kwargs["interval"] == interval


def test_broker_status_with_no_margin_data(api_instance: IATBApi) -> None:
    """Test broker_status when margins returns None."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.profile.return_value = {"user_id": "ABC123"}
    mock_kite.margins.return_value = None

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.broker_status()
            assert result["status"] == "connected"
            assert result["uid"] == "ABC123"
            # Should return 0 when margins is None
            assert result["balance"] == 0


def test_broker_status_with_empty_margins(api_instance: IATBApi) -> None:
    """Test broker_status when margins returns empty dict."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.profile.return_value = {"user_id": "ABC123"}
    mock_kite.margins.return_value = {}

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.broker_status()
            assert result["status"] == "connected"
            assert result["uid"] == "ABC123"
            assert result["balance"] == 0  # Default value when empty


def test_get_ohlcv_empty_data_response(api_instance: IATBApi) -> None:
    """Test get_ohlcv when historical_data returns empty list."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = None

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            result = api_instance.get_ohlcv("RELIANCE")
            assert result["status"] == "success"
            assert result["data"] == []
            assert result["count"] == 0


def test_default_date_range_uses_utc(api_instance: IATBApi) -> None:
    """Test that _default_date_range uses UTC for dates."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = []

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            # Call with no date range - should use default
            result = api_instance.get_ohlcv("RELIANCE")
            assert result["status"] == "success"

            # Verify historical_data was called
            assert mock_kite.historical_data.called


def test_instrument_cache_case_sensitive(api_instance: IATBApi) -> None:
    """Test that instrument cache is case-sensitive."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
        {"tradingsymbol": "reliance", "instrument_token": "789012"},  # Different case
    ]

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            api_instance._kite_client = mock_kite

            # Uppercase lookup
            token1 = api_instance._ensure_instrument_token(mock_kite, "RELIANCE", None)
            assert token1 == "123456"

            # Lowercase lookup - should get different token
            token2 = api_instance._ensure_instrument_token(mock_kite, "reliance", None)
            assert token2 == "789012"


def test_get_ohlcv_with_ticker_whitespace(api_instance: IATBApi) -> None:
    """Test get_ohlcv handles ticker with leading/trailing whitespace."""
    api_instance._token_manager.is_token_fresh.return_value = True
    mock_kite = MagicMock()
    mock_kite.instruments.return_value = [
        {"tradingsymbol": "RELIANCE", "instrument_token": "123456"},
    ]
    mock_kite.historical_data.return_value = []

    with patch("keyring.get_password", return_value="test_token"):
        with patch("kiteconnect.KiteConnect", return_value=mock_kite):
            # Ticker with whitespace should not be trimmed
            result = api_instance.get_ohlcv("  RELIANCE  ")
            assert result["status"] == "error"
            # Should not find instrument with whitespace
            assert "not found" in result["message"].lower()
