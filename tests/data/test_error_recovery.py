"""
Tests for improved error recovery in kite_provider.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.kite_provider import KiteProvider


class _FakeKiteConnect:
    """Mock KiteConnect for testing."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self._call_count = 0

    def historical_data(self, instrument_token, from_date, to_date, interval):
        self._call_count += 1
        if self._call_count == 1:
            raise Exception("Rate limit exceeded")
        return []

    def quote(self, instruments):
        self._call_count += 1
        if self._call_count == 1:
            raise Exception("Server error")
        return {"NSE:RELIANCE": {"last_price": 1000.50}}

    def ltp(self, instruments):
        self._call_count += 1
        if self._call_count == 1:
            raise Exception("Timeout")
        return {"NSE:RELIANCE": {"last_price": 1000.50}}


class TestErrorRecovery:
    """Test error recovery improvements."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error(self) -> None:
        """Test retry on rate limit error (429)."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("429 Too Many Requests"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self) -> None:
        """Test retry on server error (5xx)."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("500 Internal Server Error"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_retry_on_timeout_error(self) -> None:
        """Test retry on server error (503 Service Unavailable)."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("503 Service Unavailable"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self) -> None:
        """Test retry on server error (502 Bad Gateway)."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("502 Bad Gateway"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self) -> None:
        """Test no retry on non-retryable error."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("401 Unauthorized"),
        ):
            with pytest.raises(ConfigError, match="Non-retryable error: 401 Unauthorized"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_circuit_breaker_on_consecutive_failures(self) -> None:
        """Test circuit breaker triggers on consecutive failures."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("500 Internal Server Error"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_exponential_backoff_delay(self) -> None:
        """Test exponential backoff delay increases."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        call_count = 0

        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("500 Internal Server Error")
            return []

        with patch.object(provider, "_fetch_historical_data", side_effect=mock_fetch):
            result = await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
            )

            assert call_count == 3
            assert result == []

    @pytest.mark.asyncio
    async def test_successful_request_resets_failure_counter(self) -> None:
        """Test successful request resets consecutive failure counter."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        call_count = 0

        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("500 Internal Server Error")
            return []

        with patch.object(provider, "_fetch_historical_data", side_effect=mock_fetch):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
            )

            assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self) -> None:
        """Test retry on server error (503 Service Unavailable)."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        with patch.object(
            provider,
            "_fetch_historical_data",
            side_effect=Exception("503 Service Unavailable"),
        ):
            with pytest.raises(ConfigError, match="failed after 3 retries"):
                await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

    @pytest.mark.asyncio
    async def test_retry_with_backoff_respects_rate_limiter(self) -> None:
        """Test retry with backoff respects rate limiter."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        call_count = 0

        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("500 Internal Server Error")
            return []

        with patch.object(provider, "_fetch_historical_data", side_effect=mock_fetch):
            with patch.object(provider._rate_limiter, "acquire", new_callable=AsyncMock):
                result = await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

                assert call_count == 3
                assert result == []
                assert provider._rate_limiter.acquire.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_with_backoff_exponential_delay(self) -> None:
        """Test retry with backoff uses exponential delay."""
        provider = KiteProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_connect_factory=lambda k, t: _FakeKiteConnect(k, t),
        )

        call_count = 0
        delays = []

        async def mock_fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("500 Internal Server Error")
            return []

        with patch.object(provider, "_fetch_historical_data", side_effect=mock_fetch):
            with patch("asyncio.sleep") as mock_sleep:

                async def mock_sleep_side_effect(delay):
                    delays.append(delay)

                mock_sleep.side_effect = mock_sleep_side_effect

                result = await provider.get_ohlcv(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    timeframe="1d",
                )

                assert call_count == 3
                assert result == []
                assert len(delays) == 2
                assert delays[0] < delays[1]
