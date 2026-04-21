"""
Financial invariant tests for OHLCV data.

Tests verify that all OHLCV data satisfies fundamental financial invariants.
These are property-based tests that must hold true for all valid market data.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.data.ccxt_provider import CCXTProvider
from iatb.data.kite_provider import KiteProvider


class TestKiteFinancialInvariants:
    """Test financial invariants for Kite provider data."""

    @pytest.fixture
    def mock_kite_client(self):
        """Mock Kite client returning realistic data."""
        client = MagicMock()
        client.historical_data.return_value = [
            {
                "date": datetime(2024, 4, 20, 9, 15, tzinfo=UTC),
                "open": 1000.50,
                "high": 1025.75,
                "low": 995.00,
                "close": 1020.25,
                "volume": 1500000,
            },
            {
                "date": datetime(2024, 4, 21, 9, 15, tzinfo=UTC),
                "open": 1020.25,
                "high": 1035.50,
                "low": 1015.00,
                "close": 1030.75,
                "volume": 1800000,
            },
            {
                "date": datetime(2024, 4, 22, 9, 15, tzinfo=UTC),
                "open": 1030.75,
                "high": 1045.00,
                "low": 1025.50,
                "close": 1040.00,
                "volume": 2000000,
            },
        ]
        return client

    @pytest.mark.asyncio
    async def test_invariant_high_ge_low(self, mock_kite_client):
        """Invariant: High price must be >= Low price."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.high >= bar.low, f"High {bar.high} < Low {bar.low} at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_invariant_open_within_range(self, mock_kite_client):
        """Invariant: Open price must be within [Low, High]."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert (
                bar.low <= bar.open <= bar.high
            ), f"Open {bar.open} not in [{bar.low}, {bar.high}] at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_invariant_close_within_range(self, mock_kite_client):
        """Invariant: Close price must be within [Low, High]."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert (
                bar.low <= bar.close <= bar.high
            ), f"Close {bar.close} not in [{bar.low}, {bar.high}] at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_invariant_volume_non_negative(self, mock_kite_client):
        """Invariant: Volume must be >= 0."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.volume >= Decimal("0"), f"Volume {bar.volume} < 0 at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_invariant_prices_are_decimal(self, mock_kite_client):
        """Invariant: All price fields must be Decimal, not float."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert isinstance(bar.open, Decimal), f"Open is not Decimal: {type(bar.open)}"
            assert isinstance(bar.high, Decimal), f"High is not Decimal: {type(bar.high)}"
            assert isinstance(bar.low, Decimal), f"Low is not Decimal: {type(bar.low)}"
            assert isinstance(bar.close, Decimal), f"Close is not Decimal: {type(bar.close)}"
            assert isinstance(bar.volume, Decimal), f"Volume is not Decimal: {type(bar.volume)}"

    @pytest.mark.asyncio
    async def test_invariant_timestamp_utc_aware(self, mock_kite_client):
        """Invariant: All timestamps must be UTC-aware."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.timestamp.tzinfo is not None, f"Timestamp has no timezone at {bar.timestamp}"
            assert bar.timestamp.tzinfo == UTC, f"Timestamp not in UTC at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_invariant_source_populated(self, mock_kite_client):
        """Invariant: Source field must be populated."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.source, f"Source is empty at {bar.timestamp}"
            assert bar.source == "kiteconnect", f"Source {bar.source} != 'kiteconnect'"

    @pytest.mark.asyncio
    async def test_invariant_symbol_and_exchange_consistent(self, mock_kite_client):
        """Invariant: Symbol and exchange must be consistent across all bars."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.symbol == "RELIANCE", f"Symbol mismatch: {bar.symbol}"
            assert bar.exchange == Exchange.NSE, f"Exchange mismatch: {bar.exchange}"

    @pytest.mark.asyncio
    async def test_invariant_timeframe_consistent(self, mock_kite_client):
        """Invariant: Timeframe must be consistent across all bars."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.timeframe == "1d", f"Timeframe mismatch: {bar.timeframe}"

    @pytest.mark.asyncio
    async def test_invariant_no_extreme_price_anomalies(self, mock_kite_client):
        """Invariant: No extreme price anomalies (e.g., negative, zero)."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=100
        )

        for bar in bars:
            assert bar.open > Decimal("0"), f"Open <= 0: {bar.open}"
            assert bar.high > Decimal("0"), f"High <= 0: {bar.high}"
            assert bar.low > Decimal("0"), f"Low <= 0: {bar.low}"
            assert bar.close > Decimal("0"), f"Close <= 0: {bar.close}"


class TestCCXTFinancialInvariants:
    """Test financial invariants for CCXT provider data."""

    @pytest.fixture
    def mock_ccxt_client(self):
        """Mock CCXT client returning realistic data."""
        client = MagicMock()
        client.fetch_ohlcv.return_value = [
            [1735722900000, 50000.0, 50500.0, 49500.0, 50200.0, 1000.0],
            [1735722960000, 50200.0, 50800.0, 50000.0, 50500.0, 1200.0],
            [1735723020000, 50500.0, 51000.0, 50200.0, 50800.0, 1500.0],
        ]
        return client

    @pytest.mark.asyncio
    async def test_ccxt_invariant_high_ge_low(self, mock_ccxt_client):
        """Invariant: High price must be >= Low price (CCXT)."""
        provider = CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT", exchange=Exchange.BINANCE, timeframe="1m", limit=100
        )

        for bar in bars:
            assert bar.high >= bar.low, f"High {bar.high} < Low {bar.low} at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_ccxt_invariant_prices_are_decimal(self, mock_ccxt_client):
        """Invariant: All price fields must be Decimal, not float (CCXT)."""
        provider = CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT", exchange=Exchange.BINANCE, timeframe="1m", limit=100
        )

        for bar in bars:
            assert isinstance(bar.open, Decimal), f"Open is not Decimal: {type(bar.open)}"
            assert isinstance(bar.high, Decimal), f"High is not Decimal: {type(bar.high)}"
            assert isinstance(bar.low, Decimal), f"Low is not Decimal: {type(bar.low)}"
            assert isinstance(bar.close, Decimal), f"Close is not Decimal: {type(bar.close)}"
            assert isinstance(bar.volume, Decimal), f"Volume is not Decimal: {type(bar.volume)}"

    @pytest.mark.asyncio
    async def test_ccxt_invariant_timestamp_utc_aware(self, mock_ccxt_client):
        """Invariant: All timestamps must be UTC-aware (CCXT)."""
        provider = CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT", exchange=Exchange.BINANCE, timeframe="1m", limit=100
        )

        for bar in bars:
            assert bar.timestamp.tzinfo is not None, f"Timestamp has no timezone at {bar.timestamp}"
            assert bar.timestamp.tzinfo == UTC, f"Timestamp not in UTC at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_ccxt_invariant_source_populated(self, mock_ccxt_client):
        """Invariant: Source field must be populated (CCXT)."""
        provider = CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT", exchange=Exchange.BINANCE, timeframe="1m", limit=100
        )

        for bar in bars:
            assert bar.source, f"Source is empty at {bar.timestamp}"
            assert bar.source == "ccxt:binance", f"Source {bar.source} != 'ccxt:binance'"


class TestTickerFinancialInvariants:
    """Test financial invariants for ticker data."""

    @pytest.fixture
    def mock_kite_client(self):
        """Mock Kite client for ticker tests."""
        client = MagicMock()
        client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 1040.00,
                "bid": 1040.00,
                "ask": 1041.00,
                "volume": 2000000,
            }
        }
        return client

    @pytest.mark.asyncio
    async def test_invariant_ask_ge_bid(self, mock_kite_client):
        """Invariant: Ask price must be >= Bid price."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.ask >= ticker.bid, f"Ask {ticker.ask} < Bid {ticker.bid}"

    @pytest.mark.asyncio
    async def test_invariant_last_within_spread(self, mock_kite_client):
        """Invariant: Last price should be within [Bid, Ask] range."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        # Allow some tolerance for fast-moving markets
        assert ticker.last >= ticker.bid * Decimal(
            "0.99"
        ), f"Last {ticker.last} too low vs Bid {ticker.bid}"
        assert ticker.last <= ticker.ask * Decimal(
            "1.01"
        ), f"Last {ticker.last} too high vs Ask {ticker.ask}"

    @pytest.mark.asyncio
    async def test_invariant_ticker_volume_non_negative(self, mock_kite_client):
        """Invariant: Ticker volume must be >= 0."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.volume_24h >= Decimal("0"), f"Volume {ticker.volume_24h} < 0"

    @pytest.mark.asyncio
    async def test_invariant_ticker_prices_are_decimal(self, mock_kite_client):
        """Invariant: Ticker price fields must be Decimal."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert isinstance(ticker.bid, Decimal), f"Bid is not Decimal: {type(ticker.bid)}"
        assert isinstance(ticker.ask, Decimal), f"Ask is not Decimal: {type(ticker.ask)}"
        assert isinstance(ticker.last, Decimal), f"Last is not Decimal: {type(ticker.last)}"
        assert isinstance(
            ticker.volume_24h, Decimal
        ), f"Volume is not Decimal: {type(ticker.volume_24h)}"
