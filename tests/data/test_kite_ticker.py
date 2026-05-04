# ruff: noqa: S106, S105 - Test values are not real credentials
"""
Tests for KiteTicker WebSocket feed integration.
Note: KiteTickerFeed is deprecated. This file tests only basic initialization
and connection handling for the deprecated alias.
"""

from unittest.mock import patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity
from iatb.data.base import TickerSnapshot
from iatb.data.kite_ticker import ConnectionStats, KiteTickerFeed, TickBuffer


class _FakeKiteTicker:
    """Mock KiteTicker for testing."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False


class TestTickBuffer:
    def test_buffer_initialization(self) -> None:
        """Test TickBuffer initialization."""
        buffer = TickBuffer(max_size=10)
        assert buffer.size() == 0
        assert len(buffer.get_all()) == 0

    def test_put_and_get(self) -> None:
        """Test putting and getting ticker snapshots."""
        buffer = TickBuffer(max_size=10)

        snapshot = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        buffer.put(snapshot)
        assert buffer.size() == 1

        retrieved = buffer.get("RELIANCE", Exchange.NSE)
        assert retrieved is not None
        assert retrieved.symbol == "RELIANCE"
        assert retrieved.last == create_price("1000.50")

    def test_put_updates_existing(self) -> None:
        """Test putting updates existing symbol."""
        buffer = TickBuffer(max_size=10)

        snapshot1 = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        snapshot2 = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1001.00"),
            ask=create_price("1002.00"),
            last=create_price("1001.50"),
            volume_24h=create_quantity("2000"),
            source="test",
        )

        buffer.put(snapshot1)
        buffer.put(snapshot2)

        assert buffer.size() == 1

        retrieved = buffer.get("RELIANCE", Exchange.NSE)
        assert retrieved is not None
        assert retrieved.last == create_price("1001.50")

    def test_get_all(self) -> None:
        """Test getting all snapshots."""
        buffer = TickBuffer(max_size=10)

        snapshot1 = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        snapshot2 = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="TCS",
            bid=create_price("3000.00"),
            ask=create_price("3001.00"),
            last=create_price("3000.50"),
            volume_24h=create_quantity("500"),
            source="test",
        )

        buffer.put(snapshot1)
        buffer.put(snapshot2)

        all_snapshots = buffer.get_all()
        assert len(all_snapshots) == 2

    def test_clear(self) -> None:
        """Test clearing the buffer."""
        buffer = TickBuffer(max_size=10)

        snapshot = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        buffer.put(snapshot)
        assert buffer.size() == 1

        buffer.clear()
        assert buffer.size() == 0

    def test_lru_eviction(self) -> None:
        """Test LRU eviction when buffer is full."""
        buffer = TickBuffer(max_size=3)

        for i in range(5):
            snapshot = TickerSnapshot(
                exchange=Exchange.NSE,
                symbol=f"SYMBOL{i}",
                bid=create_price(str(1000 + i)),
                ask=create_price(str(1001 + i)),
                last=create_price(str(1000.5 + i)),
                volume_24h=create_quantity(str(1000 + i)),
                source="test",
            )
            buffer.put(snapshot)

        assert buffer.size() == 3
        assert buffer.get("SYMBOL0", Exchange.NSE) is None
        assert buffer.get("SYMBOL1", Exchange.NSE) is None
        assert buffer.get("SYMBOL2", Exchange.NSE) is not None

    def test_get_nonexistent(self) -> None:
        """Test getting non-existent symbol returns None."""
        buffer = TickBuffer(max_size=10)
        retrieved = buffer.get("NONEXISTENT", Exchange.NSE)
        assert retrieved is None


class TestConnectionStats:
    def test_stats_initialization(self) -> None:
        """Test ConnectionStats initialization."""
        stats = ConnectionStats()
        assert stats.connected_at is None
        assert stats.last_tick_at is None
        assert stats.ticks_received == 0
        assert stats.reconnect_attempts == 0
        assert stats.last_reconnect_at is None


class TestKiteTickerFeedBasic:
    """Basic tests for deprecated KiteTickerFeed alias."""

    @pytest.mark.asyncio
    async def test_feed_initialization(self) -> None:
        """Test feed initialization with valid parameters."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )
        assert feed._api_key == "test_api_key"
        assert feed._access_token == "test_access_token"
        assert not feed.is_connected()
        assert not feed.is_running()

    @pytest.mark.asyncio
    async def test_empty_api_key_raises(self) -> None:
        """Test empty API key raises ConfigError."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteTickerFeed(api_key="", access_token="test_access_token")

    @pytest.mark.asyncio
    async def test_empty_access_token_raises(self) -> None:
        """Test empty access token raises ConfigError."""
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteTickerFeed(api_key="test_api_key", access_token="")

    @pytest.mark.asyncio
    async def test_invalid_max_reconnect_raises(self) -> None:
        """Test invalid max_reconnect_attempts raises ConfigError."""
        with pytest.raises(ConfigError, match="max_reconnect_attempts must be positive"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                max_reconnect_attempts=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_initial_reconnect_delay_raises(self) -> None:
        """Test invalid retry_delay_seconds raises ConfigError."""
        with pytest.raises(ConfigError, match="retry_delay_seconds must be non-negative"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                retry_delay_seconds=-1.0,
            )

    @pytest.mark.asyncio
    async def test_invalid_max_reconnect_delay_raises(self) -> None:
        """Test invalid reconnect_backoff_max raises ConfigError."""
        with pytest.raises(ConfigError, match="reconnect_backoff_max must be positive"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                reconnect_backoff_max=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_reconnect_backoff_raises(self) -> None:
        """Test invalid reconnect_backoff_base raises ConfigError."""
        with pytest.raises(ConfigError, match="reconnect_backoff_base must be greater than 1.0"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                reconnect_backoff_base=1.0,
            )

    @pytest.mark.asyncio
    async def test_connect_establishes_connection(self) -> None:
        """Test connect establishes WebSocket connection."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        assert feed.is_connected()
        assert feed._ticker_instance is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected_noops(self) -> None:
        """Test connect when already connected is a no-op."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        first_instance = feed._ticker_instance
        await feed.connect()
        assert feed._ticker_instance is first_instance

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self) -> None:
        """Test disconnect cleans up resources."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.disconnect()
        assert not feed.is_connected()

    @pytest.mark.asyncio
    async def test_set_callback(self) -> None:
        """Test setting callback function."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def callback(snapshot: TickerSnapshot) -> None:
            pass

        feed.set_callback(callback)
        assert feed._callback is callback

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        """Test get_stats returns connection statistics."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        stats = feed.get_stats()
        assert isinstance(stats, ConnectionStats)

    @pytest.mark.asyncio
    async def test_from_env_missing_api_key(self) -> None:
        """Test from_env with missing API key raises ConfigError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigError, match="ZERODHA_API_KEY.*required"):
                KiteTickerFeed.from_env()

    @pytest.mark.asyncio
    async def test_from_env_missing_access_token(self) -> None:
        """Test from_env with missing access token raises ConfigError."""
        with patch.dict("os.environ", {"ZERODHA_API_KEY": "test_key"}, clear=True):
            with pytest.raises(ConfigError, match="ZERODHA_ACCESS_TOKEN.*required"):
                KiteTickerFeed.from_env()

    @pytest.mark.asyncio
    async def test_from_env_creates_instance(self) -> None:
        """Test from_env creates feed instance."""
        env_vars = {
            "ZERODHA_API_KEY": "test_key",
            "ZERODHA_ACCESS_TOKEN": "test_token",
        }
        with patch.dict("os.environ", env_vars, clear=True):
            feed = KiteTickerFeed.from_env()
            assert feed._api_key == "test_key"
            assert feed._access_token == "test_token"
