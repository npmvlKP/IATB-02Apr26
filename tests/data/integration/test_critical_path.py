"""
Critical path integration tests for data providers.

Tests cover end-to-end data flow from provider to consumption.
These tests use mocked clients to simulate real-world scenarios.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.data.base import OHLCVBar
from iatb.data.ccxt_provider import CCXTProvider
from iatb.data.kite_provider import KiteProvider
from iatb.data.market_data_cache import MarketDataCache
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    MarketData,
    create_mock_sentiment_analyzer,
)


@pytest.mark.integration
class TestKiteProviderCriticalPath:
    """Test critical path for Kite provider data flow."""

    @pytest.fixture
    def mock_kite_client(self):
        """Mock Kite client for integration test."""
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
    async def test_end_to_end_kite_data_flow(self, mock_kite_client):
        """Test data flow from Kite provider to cache and retrieval."""
        # Step 1: Create provider
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )

        # Step 2: Fetch OHLCV data
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(bars) == 3
        assert all(isinstance(bar, OHLCVBar) for bar in bars)

        # Step 3: Verify data normalization
        for bar in bars:
            assert bar.symbol == "RELIANCE"
            assert bar.exchange == Exchange.NSE
            assert bar.timeframe == "1d"
            assert bar.source == "kiteconnect"
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.tzinfo == UTC

        # Step 4: Verify price invariants
        for bar in bars:
            assert bar.high >= bar.low
            assert bar.low <= bar.open <= bar.high
            assert bar.low <= bar.close <= bar.high
            assert bar.volume >= 0

        # Step 5: Fetch ticker
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.symbol == "RELIANCE"
        assert ticker.exchange == Exchange.NSE
        assert ticker.source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_kite_provider_with_cache_integration(self, mock_kite_client):
        """Test Kite provider integration with market data cache."""
        # Create provider and cache
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )
        cache = MarketDataCache(default_ttl_seconds=60)

        # Fetch data
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        # Store in cache
        test_data = MarketData(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=bars[-1].close,
            prev_close_price=bars[-2].close if len(bars) > 1 else Decimal("0"),
            volume=bars[-1].volume,
            avg_volume=Decimal("1500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=bars[-1].high,
            low_price=bars[-1].low,
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("RELIANCE", "2024-04-20", "2024-04-22", test_data)

        # Retrieve from cache
        cached = cache.get("RELIANCE", "2024-04-20", "2024-04-22")
        assert cached is not None
        assert cached.symbol == "RELIANCE"
        assert cached.close_price == bars[-1].close


@pytest.mark.integration
class TestCCXTProviderCriticalPath:
    """Test critical path for CCXT provider data flow."""

    @pytest.fixture
    def mock_ccxt_client(self):
        """Mock CCXT client for integration test."""
        client = MagicMock()
        client.fetch_ohlcv.return_value = [
            [1735722900000, 50000.0, 50500.0, 49500.0, 50200.0, 1000.0],
            [1735722960000, 50200.0, 50800.0, 50000.0, 50500.0, 1200.0],
            [1735723020000, 50500.0, 51000.0, 50200.0, 50800.0, 1500.0],
        ]
        client.fetch_ticker.return_value = {
            "bid": 50800.0,
            "ask": 50801.0,
            "last": 50800.50,
            "baseVolume": 1500.0,
            "quoteVolume": 76200750.0,
            "high": 51000.0,
            "low": 50200.0,
            "close": 50800.50,
        }
        return client

    @pytest.mark.asyncio
    async def test_end_to_end_ccxt_data_flow(self, mock_ccxt_client):
        """Test data flow from CCXT provider to cache and retrieval."""
        # Step 1: Create provider
        provider = CCXTProvider(exchange_factory=lambda _: mock_ccxt_client)

        # Step 2: Fetch OHLCV data
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            limit=10,
        )

        assert len(bars) == 3
        assert all(isinstance(bar, OHLCVBar) for bar in bars)

        # Step 3: Verify data normalization
        for bar in bars:
            assert bar.symbol == "BTCUSDT"
            assert bar.exchange == Exchange.BINANCE
            assert bar.timeframe == "1m"
            assert bar.source == "ccxt:binance"
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.tzinfo == UTC

        # Step 4: Verify price invariants
        for bar in bars:
            assert bar.high >= bar.low
            assert bar.low <= bar.open <= bar.high
            assert bar.low <= bar.close <= bar.high
            assert bar.volume >= 0

        # Step 5: Fetch ticker
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.symbol == "BTCUSDT"
        assert ticker.exchange == Exchange.BINANCE
        assert ticker.source == "ccxt:binance"


@pytest.mark.integration
class TestProviderToScannerIntegration:
    """Test integration between data providers and scanner."""

    @pytest.fixture
    def mock_kite_client(self):
        """Mock Kite client for scanner integration."""
        client = MagicMock()
        client.historical_data.return_value = [
            {
                "date": datetime.now(UTC),
                "open": 3500.0,
                "high": 3550.0,
                "low": 3450.0,
                "close": 3520.0,
                "volume": 2000000.0,
            }
        ]
        return client

    @pytest.mark.asyncio
    async def test_provider_to_scanner_data_flow(self, mock_kite_client):
        """Test data flow from provider to scanner."""
        from iatb.scanner.instrument_scanner import InstrumentScanner, create_mock_rl_predictor

        # Create provider
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )

        # Fetch data
        bars = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        # Create scanner with custom data
        scanner = InstrumentScanner(
            sentiment_analyzer=create_mock_sentiment_analyzer({"TCS": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
            symbols=[],
            cache_ttl_seconds=60,
        )

        # Convert bars to MarketData
        custom_data = [
            MarketData(
                symbol=bar.symbol,
                exchange=bar.exchange,
                category=InstrumentCategory.STOCK,
                close_price=bar.close,
                prev_close_price=bar.open,  # Simplified
                volume=bar.volume,
                avg_volume=bar.volume,
                timestamp_utc=bar.timestamp,
                high_price=bar.high,
                low_price=bar.low,
                adx=Decimal("30"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
            for bar in bars
        ]

        # Run scan
        result = scanner.scan(custom_data=custom_data)

        assert result.total_scanned == 1
        assert scanner._cache.get_stats()["total_entries"] == 0  # Custom data bypasses cache
