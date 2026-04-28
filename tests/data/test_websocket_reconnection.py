"""
Tests for WebSocket reconnection logic and heartbeat monitoring.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from iatb.core.exceptions import ConfigError
from iatb.data.kite_ws_provider import (
    ConnectionState,
    KiteWebSocketProvider,
)


class _FakeKiteTicker:
    """Mock KiteTicker for testing."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self._connected = False
        self._subscribed = []
        self.on_ticks = None
        self.on_connect = None
        self.on_close = None
        self.on_error = None

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def subscribe(self, instruments: list[str]) -> None:
        self._subscribed.extend(instruments)


class TestWebSocketReconnection:
    """Test WebSocket reconnection logic."""

    @pytest.mark.asyncio
    async def test_connection_state_tracking(self) -> None:
        """Test connection state transitions."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        assert provider._connection_state == ConnectionState.DISCONNECTED

        await provider.connect()
        assert provider._connection_state == ConnectionState.CONNECTED

        await provider.disconnect()
        assert provider._connection_state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self) -> None:
        """Test exponential backoff delay calculation."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
            reconnect_backoff_base=2.0,
            reconnect_backoff_max=60.0,
        )

        assert provider._reconnect_backoff_base == 2.0
        assert provider._reconnect_backoff_max == 60.0

    @pytest.mark.asyncio
    async def test_heartbeat_monitor_initialization(self) -> None:
        """Test heartbeat monitor is started on connection."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
            heartbeat_interval_seconds=30.0,
            heartbeat_timeout_seconds=90.0,
        )

        await provider.connect()
        assert provider._heartbeat_task is not None
        assert not provider._heartbeat_task.done()

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_detection(self) -> None:
        """Test heartbeat timeout triggers reconnection."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
            heartbeat_interval_seconds=1.0,
            heartbeat_timeout_seconds=2.0,
        )

        await provider.connect()

        provider._last_heartbeat_utc = datetime.now(UTC) - timedelta(seconds=10)

        await asyncio.sleep(3)

        assert not provider._is_connected

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_connection_close_triggers_reconnection(self) -> None:
        """Test connection close event triggers reconnection."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        provider._on_close(None, 1000, "Normal closure")

        assert provider._connection_state == ConnectionState.DISCONNECTED
        assert provider._reconnect_task is not None

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_connection_error_triggers_reconnection(self) -> None:
        """Test connection error event triggers reconnection."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        provider._on_error(None, 1006, "Connection error")

        assert provider._reconnect_task is not None

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_max_reconnect_attempts(self) -> None:
        """Test max reconnect attempts limit."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
            max_reconnect_attempts=3,
        )

        await provider.connect()

        provider._reconnect_attempt = 3
        provider._on_close(None, 1000, "Test closure")

        await asyncio.sleep(0.1)

        assert provider._connection_state == ConnectionState.FAILED

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_reconnect_backoff_max_limit(self) -> None:
        """Test reconnect backoff is capped at max value."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
            reconnect_backoff_base=10.0,
            reconnect_backoff_max=30.0,
        )

        await provider.connect()

        provider._reconnect_attempt = 10

        backoff_delay = min(
            provider._reconnect_backoff_base**provider._reconnect_attempt,
            provider._reconnect_backoff_max,
        )

        assert backoff_delay == 30.0

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_stops_reconnection(self) -> None:
        """Test disconnect stops reconnection attempts."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        provider._on_close(None, 1000, "Test closure")

        await provider.disconnect()

        assert provider._should_stop is True

    @pytest.mark.asyncio
    async def test_invalid_heartbeat_interval_raises(self) -> None:
        """Test invalid heartbeat interval raises ConfigError."""
        with pytest.raises(ConfigError, match="heartbeat_interval_seconds must be positive"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                heartbeat_interval_seconds=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_heartbeat_timeout_raises(self) -> None:
        """Test invalid heartbeat timeout raises ConfigError."""
        with pytest.raises(ConfigError, match="heartbeat_timeout_seconds must be positive"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                heartbeat_timeout_seconds=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_reconnect_backoff_base_raises(self) -> None:
        """Test invalid reconnect backoff base raises ConfigError."""
        with pytest.raises(ConfigError, match="reconnect_backoff_base must be greater than 1.0"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                reconnect_backoff_base=1.0,
            )

    @pytest.mark.asyncio
    async def test_invalid_reconnect_backoff_max_raises(self) -> None:
        """Test invalid reconnect backoff max raises ConfigError."""
        with pytest.raises(ConfigError, match="reconnect_backoff_max must be positive"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                reconnect_backoff_max=0,
            )

    @pytest.mark.asyncio
    async def test_on_connect_updates_heartbeat(self) -> None:
        """Test on_connect updates heartbeat timestamp."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        provider._on_connect(None, {})

        assert provider._last_heartbeat_utc is not None

        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_on_ticks_updates_heartbeat(self) -> None:
        """Test on_ticks updates heartbeat timestamp."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        provider._on_ticks(None, [tick_data])

        assert provider._last_heartbeat_utc is not None

        await provider.disconnect()
