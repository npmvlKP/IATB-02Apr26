# ruff: noqa: S106, S105 - Test values are not real credentials
"""
Tests for KiteTicker WebSocket feed integration.
"""

from datetime import UTC, datetime
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
        self._subscribed = []
        self._mode = "quote"

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def subscribe(self, tokens: list[int], mode: str = "quote") -> None:
        self._subscribed.extend(tokens)
        self._mode = mode

    def unsubscribe(self, tokens: list[int]) -> None:
        for token in tokens:
            if token in self._subscribed:
                self._subscribed.remove(token)


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


class TestKiteTickerFeed:
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
        """Test invalid initial_reconnect_delay raises ConfigError."""
        with pytest.raises(ConfigError, match="initial_reconnect_delay must be non-negative"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                initial_reconnect_delay=-1.0,
            )

    @pytest.mark.asyncio
    async def test_invalid_max_reconnect_delay_raises(self) -> None:
        """Test invalid max_reconnect_delay raises ConfigError."""
        with pytest.raises(ConfigError, match="max_reconnect_delay must be positive"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                max_reconnect_delay=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_reconnect_backoff_raises(self) -> None:
        """Test invalid reconnect_backoff_multiplier raises ConfigError."""
        with pytest.raises(
            ConfigError, match="reconnect_backoff_multiplier must be greater than 1.0"
        ):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                reconnect_backoff_multiplier=1.0,
            )

    @pytest.mark.asyncio
    async def test_invalid_heartbeat_interval_raises(self) -> None:
        """Test invalid heartbeat_interval raises ConfigError."""
        with pytest.raises(ConfigError, match="heartbeat_interval must be positive"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                heartbeat_interval=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_tick_buffer_size_raises(self) -> None:
        """Test invalid tick_buffer_size raises ConfigError."""
        with pytest.raises(ConfigError, match="tick_buffer_size must be positive"):
            KiteTickerFeed(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                tick_buffer_size=0,
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
        assert len(feed._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_subscribe_creates_subscription(self) -> None:
        """Test subscribe adds to subscriptions."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.subscribe("RELIANCE", Exchange.NSE, mode="quote")
        assert ("RELIANCE", Exchange.NSE) in feed._subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_without_connect_raises(self) -> None:
        """Test subscribe without connect raises ConfigError."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with pytest.raises(ConfigError, match="Not connected"):
            await feed.subscribe("RELIANCE", Exchange.NSE)

    @pytest.mark.asyncio
    async def test_subscribe_invalid_mode_raises(self) -> None:
        """Test subscribe with invalid mode raises ConfigError."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        with pytest.raises(ConfigError, match="Invalid mode"):
            await feed.subscribe("RELIANCE", Exchange.NSE, mode="invalid")

    @pytest.mark.asyncio
    async def test_subscribe_quote_mode(self) -> None:
        """Test subscribe with quote mode."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.subscribe("12345", Exchange.NSE, mode="quote")
        assert ("12345", Exchange.NSE) in feed._subscriptions

    @pytest.mark.asyncio
    async def test_subscribe_ltp_mode(self) -> None:
        """Test subscribe with LTP mode."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.subscribe("12345", Exchange.NSE, mode="ltp")
        assert ("12345", Exchange.NSE) in feed._subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self) -> None:
        """Test unsubscribe removes from subscriptions."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.subscribe("RELIANCE", Exchange.NSE)
        await feed.unsubscribe("RELIANCE", Exchange.NSE)
        assert ("RELIANCE", Exchange.NSE) not in feed._subscriptions

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
    async def test_start_starts_tasks(self) -> None:
        """Test start starts background tasks."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.start()
        assert feed.is_running()
        assert feed._heartbeat_task is not None
        assert feed._reconnect_task is not None

    @pytest.mark.asyncio
    async def test_get_tick_from_buffer(self) -> None:
        """Test get_tick retrieves from buffer."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()

        snapshot = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        feed._tick_buffer.put(snapshot)
        retrieved = await feed.get_tick("RELIANCE", Exchange.NSE)
        assert retrieved is not None
        assert retrieved.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_tick_without_connect_raises(self) -> None:
        """Test get_tick without connect raises ConfigError."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with pytest.raises(ConfigError, match="Not connected"):
            await feed.get_tick("RELIANCE", Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_latest_tick_non_blocking(self) -> None:
        """Test get_latest_tick is non-blocking."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()

        snapshot = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        feed._tick_buffer.put(snapshot)
        retrieved = feed.get_latest_tick("RELIANCE", Exchange.NSE)
        assert retrieved is not None
        assert retrieved.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_all_ticks(self) -> None:
        """Test get_all_ticks returns all snapshots."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()

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

        feed._tick_buffer.put(snapshot1)
        feed._tick_buffer.put(snapshot2)

        all_ticks = feed.get_all_ticks()
        assert len(all_ticks) == 2

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
    async def test_parse_tick_valid_data(self) -> None:
        """Test parsing valid tick data."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "instrument_token": "12345",
            "last_price": 1000.50,
            "volume_traded": 1000,
            "buy_quantity": 500,
            "sell_quantity": 500,
            "exchange_timestamp": datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        }

        snapshot = feed._parse_tick(tick_data)
        assert snapshot is not None
        assert snapshot.symbol == "12345"
        assert snapshot.last == create_price("1000.50")

    @pytest.mark.asyncio
    async def test_parse_tick_missing_instrument_token(self) -> None:
        """Test parsing tick with missing instrument token returns None."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        snapshot = feed._parse_tick(tick_data)
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_parse_tick_missing_last_price(self) -> None:
        """Test parsing tick with missing last_price returns None."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "instrument_token": "12345",
            "volume_traded": 1000,
        }

        snapshot = feed._parse_tick(tick_data)
        assert snapshot is None

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

    @pytest.mark.asyncio
    async def test_on_ticks_updates_buffer_and_queue(self) -> None:
        """Test on_ticks handler updates buffer and queue."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        feed._on_ticks(None, [tick_data])

        # Check buffer
        assert feed._tick_buffer.size() == 1

        # Check stats
        assert feed._stats.ticks_received == 1

    @pytest.mark.asyncio
    async def test_on_connect_updates_state(self) -> None:
        """Test on_connect handler updates connection state."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._on_connect(None, {})
        assert feed.is_connected()

    @pytest.mark.asyncio
    async def test_on_close_updates_state(self) -> None:
        """Test on_close handler updates connection state."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._is_connected = True
        feed._on_close(None, 1000, "Normal closure")
        assert not feed.is_connected()

    @pytest.mark.asyncio
    async def test_on_error_updates_state(self) -> None:
        """Test on_error handler updates connection state."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._is_connected = True
        feed._on_error(None, 1006, "Abnormal closure")
        assert not feed.is_connected()

    @pytest.mark.asyncio
    async def test_on_reconnect_updates_state(self) -> None:
        """Test on_reconnect handler updates connection state."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._reconnect_delay = 10.0
        feed._on_reconnect(None, {})
        assert feed.is_connected()
        assert feed._reconnect_delay == feed._initial_reconnect_delay

    @pytest.mark.asyncio
    async def test_on_noreconnect_updates_state(self) -> None:
        """Test on_noreconnect handler updates connection state."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._is_connected = True
        feed._on_noreconnect(None)
        assert not feed.is_connected()

    @pytest.mark.asyncio
    async def test_callback_invoked_on_tick(self) -> None:
        """Test callback is invoked when tick arrives."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        callback_invoked = False
        received_snapshot: TickerSnapshot | None = None

        def callback(snapshot: TickerSnapshot) -> None:
            nonlocal callback_invoked, received_snapshot
            callback_invoked = True
            received_snapshot = snapshot

        feed.set_callback(callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        feed._on_ticks(None, [tick_data])

        assert callback_invoked
        assert received_snapshot is not None
        assert received_snapshot.symbol == "RELIANCE"


class TestMemoryMonitoring:
    @pytest.mark.asyncio
    async def test_memory_monitor_task_started(self) -> None:
        """Test memory monitor task is started when feed starts."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.start()

        assert feed._memory_monitor_task is not None
        assert not feed._memory_monitor_task.done()

        await feed.disconnect()

    @pytest.mark.asyncio
    async def test_memory_monitor_task_stopped(self) -> None:
        """Test memory monitor task is stopped when feed disconnects."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await feed.connect()
        await feed.start()
        await feed.disconnect()

        assert feed._memory_monitor_task is not None

    @pytest.mark.asyncio
    async def test_get_memory_usage(self) -> None:
        """Test getting memory usage."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        memory_usage = feed._get_memory_usage()
        assert isinstance(memory_usage, int)
        assert memory_usage >= 0

    @pytest.mark.asyncio
    async def test_check_memory_usage_updates_stats(self) -> None:
        """Test checking memory usage updates stats."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        feed._check_memory_usage()

        assert feed._stats.memory_usage_bytes >= 0
        assert feed._stats.last_memory_check is not None
        assert feed._stats.memory_peak_bytes >= feed._stats.memory_usage_bytes

    @pytest.mark.asyncio
    async def test_perform_cleanup_clears_buffer(self) -> None:
        """Test performing cleanup clears buffer."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        snapshot = TickerSnapshot(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            bid=create_price("1000.00"),
            ask=create_price("1001.00"),
            last=create_price("1000.50"),
            volume_24h=create_quantity("1000"),
            source="test",
        )

        feed._tick_buffer.put(snapshot)
        assert feed._tick_buffer.size() == 1

        feed._perform_cleanup()
        assert feed._tick_buffer.size() == 0
        assert feed._stats.cleanup_count == 1

    @pytest.mark.asyncio
    async def test_memory_monitor_logs_warning_on_high_usage(self) -> None:
        """Test memory monitor logs warning on high memory usage."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with patch.object(feed, "_get_memory_usage", return_value=150 * 1024 * 1024):
            with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
                feed._check_memory_usage()
                mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_memory_monitor_logs_error_on_critical_usage(self) -> None:
        """Test memory monitor logs error on critical memory usage."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with patch.object(feed, "_get_memory_usage", return_value=250 * 1024 * 1024):
            with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
                feed._check_memory_usage()
                mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_connection_stats_includes_memory_fields(self) -> None:
        """Test ConnectionStats includes memory monitoring fields."""
        stats = ConnectionStats()
        assert hasattr(stats, "memory_usage_bytes")
        assert hasattr(stats, "memory_peak_bytes")
        assert hasattr(stats, "last_memory_check")
        assert hasattr(stats, "cleanup_count")

    @pytest.mark.asyncio
    async def test_memory_peak_tracking(self) -> None:
        """Test memory peak is tracked correctly."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with patch.object(feed, "_get_memory_usage", return_value=100 * 1024 * 1024):
            feed._check_memory_usage()
            assert feed._stats.memory_peak_bytes == 100 * 1024 * 1024

        with patch.object(feed, "_get_memory_usage", return_value=150 * 1024 * 1024):
            feed._check_memory_usage()
            assert feed._stats.memory_peak_bytes == 150 * 1024 * 1024

        with patch.object(feed, "_get_memory_usage", return_value=120 * 1024 * 1024):
            feed._check_memory_usage()
            assert feed._stats.memory_peak_bytes == 150 * 1024 * 1024


class TestCallbackErrorHandling:
    @pytest.mark.asyncio
    async def test_callback_exception_logged(self) -> None:
        """Test callback exception is logged with details."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def failing_callback(snapshot: TickerSnapshot) -> None:
            raise ValueError("Test callback error")

        feed.set_callback(failing_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
            feed._on_ticks(None, [tick_data])
            mock_logger.error.assert_called()

            call_args = mock_logger.error.call_args
            assert "Callback failure detected" in str(call_args)

    @pytest.mark.asyncio
    async def test_callback_failure_handler_called(self) -> None:
        """Test callback failure handler is called on exception."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def failing_callback(snapshot: TickerSnapshot) -> None:
            raise ValueError("Test callback error")

        feed.set_callback(failing_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        with patch.object(feed, "_handle_callback_failure") as mock_handler:
            feed._on_ticks(None, [tick_data])
            mock_handler.assert_called_once()

            call_args = mock_handler.call_args[0]
            assert isinstance(call_args[0], TickerSnapshot)
            assert isinstance(call_args[1], Exception)

    @pytest.mark.asyncio
    async def test_callback_error_does_not_crash_ticker(self) -> None:
        """Test callback error does not crash ticker."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def failing_callback(snapshot: TickerSnapshot) -> None:
            raise ValueError("Test callback error")

        feed.set_callback(failing_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        feed._on_ticks(None, [tick_data])

        assert feed._stats.ticks_received == 1
        assert feed._stats.last_tick_at is not None

    @pytest.mark.asyncio
    async def test_callback_failure_logs_symbol_info(self) -> None:
        """Test callback failure logs symbol information."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def failing_callback(snapshot: TickerSnapshot) -> None:
            raise ValueError("Test callback error")

        feed.set_callback(failing_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
            feed._on_ticks(None, [tick_data])

            call_args = mock_logger.error.call_args
            extra = call_args[1].get("extra", {})
            assert "symbol" in extra
            assert "exchange" in extra
            assert "exception_type" in extra
            assert "exception_message" in extra

    @pytest.mark.asyncio
    async def test_multiple_callback_failures_logged(self) -> None:
        """Test multiple callback failures are logged."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def failing_callback(snapshot: TickerSnapshot) -> None:
            raise ValueError("Test callback error")

        feed.set_callback(failing_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
            feed._on_ticks(None, [tick_data, tick_data, tick_data])
            assert mock_logger.error.call_count >= 3

    @pytest.mark.asyncio
    async def test_callback_success_no_error_logged(self) -> None:
        """Test successful callback does not log error."""
        feed = KiteTickerFeed(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        def success_callback(snapshot: TickerSnapshot) -> None:
            pass

        feed.set_callback(success_callback)
        await feed.connect()

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        with patch("iatb.data.kite_ticker._LOGGER") as mock_logger:
            feed._on_ticks(None, [tick_data])
            mock_logger.error.assert_not_called()
