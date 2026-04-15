# ruff: noqa: S106, S105 - Test values are not real credentials
"""
Tests for Kite WebSocket provider integration.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.kite_ws_provider import CandleBuilder, KiteWebSocketProvider, Tick


class _FakeKiteTicker:
    """Mock KiteTicker for testing."""

    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self._connected = False
        self._subscribed = []

    def connect(self) -> None:
        self._connected = True

    def close(self) -> None:
        self._connected = False

    def subscribe(self, instruments: list[str]) -> None:
        self._subscribed.extend(instruments)


class TestTick:
    def test_tick_creation(self) -> None:
        """Test Tick dataclass creation with all fields."""
        tick = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("1000"),
            mode="quote",
        )
        assert tick.event_id == "12345"
        assert tick.symbol == "RELIANCE"
        assert tick.last_price == create_price("1000.50")
        assert tick.volume == create_quantity("1000")

    def test_tick_defaults(self) -> None:
        """Test Tick with default mode."""
        tick = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("1000"),
        )
        assert tick.mode == "quote"


class TestCandleBuilder:
    def test_candle_builder_initialization(self) -> None:
        """Test CandleBuilder initialization."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )
        assert builder.symbol == "RELIANCE"
        assert builder.exchange == Exchange.NSE
        assert builder.timeframe == "1m"
        assert len(builder.candle_queue) == 0

    def test_add_tick_creates_candle(self) -> None:
        """Test adding a tick creates a new candle."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        tick = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        builder.add_tick(tick)
        assert builder.current_candle is not None
        assert builder.current_candle["open"] == create_price("1000.50")

    def test_add_tick_updates_candle(self) -> None:
        """Test adding multiple ticks updates the same candle."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        tick1 = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        tick2 = Tick(
            event_id="12346",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 45, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1005.75"),
            volume=create_quantity("200"),
        )

        builder.add_tick(tick1)
        builder.add_tick(tick2)

        assert builder.current_candle["high"] == create_price("1005.75")
        assert builder.current_candle["low"] == create_price("1000.50")
        assert builder.current_candle["close"] == create_price("1005.75")
        assert builder.current_candle["volume"] == create_quantity("300")

    def test_candle_timestamp_1m(self) -> None:
        """Test candle timestamp calculation for 1m timeframe."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        timestamp = builder._candle_timestamp(datetime(2026, 1, 1, 10, 30, 45, tzinfo=UTC))
        assert timestamp == datetime(2026, 1, 1, 10, 30, 0, tzinfo=UTC)

    def test_candle_timestamp_5m(self) -> None:
        """Test candle timestamp calculation for 5m timeframe."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="5m",
        )

        timestamp = builder._candle_timestamp(datetime(2026, 1, 1, 10, 33, 45, tzinfo=UTC))
        assert timestamp == datetime(2026, 1, 1, 10, 30, 0, tzinfo=UTC)

    def test_candle_timestamp_15m(self) -> None:
        """Test candle timestamp calculation for 15m timeframe."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="15m",
        )

        timestamp = builder._candle_timestamp(datetime(2026, 1, 1, 10, 40, 45, tzinfo=UTC))
        assert timestamp == datetime(2026, 1, 1, 10, 30, 0, tzinfo=UTC)

    def test_candle_timestamp_1h(self) -> None:
        """Test candle timestamp calculation for 1h timeframe."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1h",
        )

        timestamp = builder._candle_timestamp(datetime(2026, 1, 1, 10, 30, 45, tzinfo=UTC))
        assert timestamp == datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)

    def test_candle_timestamp_1d(self) -> None:
        """Test candle timestamp calculation for 1d timeframe."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
        )

        timestamp = builder._candle_timestamp(datetime(2026, 1, 1, 10, 30, 45, tzinfo=UTC))
        assert timestamp == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_unsupported_timeframe_raises(self) -> None:
        """Test unsupported timeframe raises ConfigError."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="3m",
        )

        tick = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        with pytest.raises(ConfigError, match="Unsupported timeframe"):
            builder.add_tick(tick)

    def test_new_candle_on_minute_boundary(self) -> None:
        """Test new candle is created on minute boundary."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        tick1 = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        tick2 = Tick(
            event_id="12346",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1005.75"),
            volume=create_quantity("200"),
        )

        builder.add_tick(tick1)
        builder.add_tick(tick2)

        candles = builder.get_candles()
        assert len(candles) == 1
        assert candles[0].open == create_price("1000.50")

    def test_get_candles_clears_queue(self) -> None:
        """Test get_candles clears the internal queue."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        tick1 = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        tick2 = Tick(
            event_id="12346",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 1, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1005.75"),
            volume=create_quantity("200"),
        )

        builder.add_tick(tick1)
        builder.add_tick(tick2)

        candles = builder.get_candles()
        assert len(candles) == 1
        assert len(builder.candle_queue) == 0

    def test_finalize_current_candle(self) -> None:
        """Test finalizing the current incomplete candle."""
        builder = CandleBuilder(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        tick = Tick(
            event_id="12345",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            last_price=create_price("1000.50"),
            volume=create_quantity("100"),
        )

        builder.add_tick(tick)
        candle = builder.finalize_current_candle()

        assert candle is not None
        assert candle.open == create_price("1000.50")
        assert candle.close == create_price("1000.50")


class TestKiteWebSocketProvider:
    @pytest.mark.asyncio
    async def test_provider_initialization(self) -> None:
        """Test provider initialization with valid parameters."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )
        assert provider._api_key == "test_api_key"
        assert provider._access_token == "test_access_token"
        assert not provider._is_connected

    @pytest.mark.asyncio
    async def test_empty_api_key_raises(self) -> None:
        """Test empty API key raises ConfigError."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="",
                access_token="test_access_token",
            )

    @pytest.mark.asyncio
    async def test_empty_access_token_raises(self) -> None:
        """Test empty access token raises ConfigError."""
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="",
            )

    @pytest.mark.asyncio
    async def test_invalid_max_retries_raises(self) -> None:
        """Test invalid max_retries raises ConfigError."""
        with pytest.raises(ConfigError, match="max_retries must be positive"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                max_retries=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_retry_delay_raises(self) -> None:
        """Test invalid retry_delay_seconds raises ConfigError."""
        with pytest.raises(ConfigError, match="retry_delay_seconds must be non-negative"):
            KiteWebSocketProvider(  # noqa: S106
                api_key="test_api_key",
                access_token="test_access_token",
                retry_delay_seconds=-1.0,
            )

    @pytest.mark.asyncio
    async def test_connect_establishes_connection(self) -> None:
        """Test connect establishes WebSocket connection."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        assert provider._is_connected
        assert provider._ticker_instance is not None

    @pytest.mark.asyncio
    async def test_connect_already_connected_noops(self) -> None:
        """Test connect when already connected is a no-op."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        first_instance = provider._ticker_instance
        await provider.connect()
        assert provider._ticker_instance is first_instance

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self) -> None:
        """Test disconnect cleans up resources."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        await provider.disconnect()
        assert not provider._is_connected
        assert len(provider._tickers) == 0
        assert len(provider._latest_tickers) == 0

    @pytest.mark.asyncio
    async def test_subscribe_creates_candle_builder(self) -> None:
        """Test subscribe creates a CandleBuilder for the symbol."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        await provider.subscribe("RELIANCE", Exchange.NSE, "1m")
        assert "RELIANCE" in provider._tickers
        assert provider._tickers["RELIANCE"].timeframe == "1m"

    @pytest.mark.asyncio
    async def test_subscribe_without_connect_raises(self) -> None:
        """Test subscribe without connect raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with pytest.raises(ConfigError, match="Provider not connected"):
            await provider.subscribe("RELIANCE", Exchange.NSE, "1m")

    @pytest.mark.asyncio
    async def test_get_ohlcv_without_connect_raises(self) -> None:
        """Test get_ohlcv without connect raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with pytest.raises(ConfigError, match="Provider not connected"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_without_subscribe_raises(self) -> None:
        """Test get_ohlcv without subscribe raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        with pytest.raises(ConfigError, match="not subscribed"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_invalid_limit_raises(self) -> None:
        """Test get_ohlcv with invalid limit raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        await provider.subscribe("RELIANCE", Exchange.NSE, "1m")

        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=0,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_without_connect_raises(self) -> None:
        """Test get_ticker without connect raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        with pytest.raises(ConfigError, match="Provider not connected"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_ticker_no_data_raises(self) -> None:
        """Test get_ticker without data raises ConfigError."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        with pytest.raises(ConfigError, match="No ticker data available"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_parse_tick_valid_data(self) -> None:
        """Test parsing valid tick data."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "instrument_token": "RELIANCE",
            "last_price": 1000.50,
            "volume_traded": 1000,
            "mode": "quote",
        }

        tick = provider._parse_tick(tick_data)
        assert tick is not None
        assert tick.symbol == "RELIANCE"
        assert tick.last_price == create_price("1000.50")
        assert tick.volume == create_quantity("1000")

    @pytest.mark.asyncio
    async def test_parse_tick_missing_symbol(self) -> None:
        """Test parsing tick with missing symbol returns None."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "instrument_token": "",
            "last_price": 1000.50,
            "volume_traded": 1000,
        }

        tick = provider._parse_tick(tick_data)
        assert tick is None

    @pytest.mark.asyncio
    async def test_parse_tick_missing_price(self) -> None:
        """Test parsing tick with missing price returns None."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        tick_data = {
            "instrument_token": "RELIANCE",
            "volume_traded": 1000,
        }

        tick = provider._parse_tick(tick_data)
        assert tick is None

    @pytest.mark.asyncio
    async def test_from_env_missing_api_key(self) -> None:
        """Test from_env with missing API key raises ConfigError."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ConfigError, match="ZERODHA_API_KEY.*required"):
                KiteWebSocketProvider.from_env()

    @pytest.mark.asyncio
    async def test_from_env_missing_access_token(self) -> None:
        """Test from_env with missing access token raises ConfigError."""
        with patch.dict("os.environ", {"ZERODHA_API_KEY": "test_key"}, clear=True):
            with pytest.raises(ConfigError, match="ZERODHA_ACCESS_TOKEN.*required"):
                KiteWebSocketProvider.from_env()

    @pytest.mark.asyncio
    async def test_get_ohlcv_batch(self) -> None:
        """Test get_ohlcv_batch for multiple symbols."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()
        await provider.subscribe("RELIANCE", Exchange.NSE, "1m")
        await provider.subscribe("TCS", Exchange.NSE, "1m")

        results = await provider.get_ohlcv_batch(
            symbols=["RELIANCE", "TCS"],
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        assert "RELIANCE" in results
        assert "TCS" in results

    @pytest.mark.asyncio
    async def test_disconnect_handles_runtime_error(self) -> None:
        """Test disconnect handles RuntimeError when event loop is closed."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        # Simulate RuntimeError when event loop is closed
        original_task = provider._tick_processor_task

        async def mock_await_raises_runtime() -> None:
            msg = "Event loop is closed"
            raise RuntimeError(msg)

        # Patch the task's __await__ to raise RuntimeError
        if original_task:
            original_task.__await__ = lambda: mock_await_raises_runtime().__await__()

        # Should not raise despite RuntimeError
        await provider.disconnect()
        assert not provider._is_connected
        assert len(provider._tickers) == 0
        assert len(provider._latest_tickers) == 0

    @pytest.mark.asyncio
    async def test_disconnect_handles_cancelled_error(self) -> None:
        """Test disconnect handles CancelledError during task cancellation."""
        provider = KiteWebSocketProvider(  # noqa: S106
            api_key="test_api_key",
            access_token="test_access_token",
            kite_ticker_factory=lambda k, t: _FakeKiteTicker(k, t),
        )

        await provider.connect()

        # Normal disconnect - task cancellation should work cleanly
        await provider.disconnect()
        assert not provider._is_connected
        assert len(provider._tickers) == 0
        assert len(provider._latest_tickers) == 0
