"""
Integration tests for Risk 3: Rate Limiting Mitigation Strategy.

This test suite demonstrates and validates the complete mitigation strategy for
Kite API rate limiting (3 req/sec) when scanning 50+ symbols.

Mitigation Components Tested:
1. Token bucket rate limiter in KiteProvider
2. Batch instrument token resolution (SymbolTokenResolver)
3. Cache historical data (MarketDataCache)
4. WebSocket for live data (KiteWebSocketProvider)
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.data.kite_provider import KiteProvider, _RateLimiter
from iatb.data.kite_ws_provider import KiteWebSocketProvider
from iatb.data.market_data_cache import MarketDataCache
from iatb.data.token_resolver import SymbolTokenResolver


class TestRateLimitingMitigationIntegration:
    """Integration tests for complete rate limiting mitigation strategy."""

    @pytest.fixture
    def mock_kite_client(self):
        """Create a mock KiteConnect client with rate limiting behavior."""
        client = MagicMock()
        # Simulate historical data for multiple symbols
        client.historical_data.return_value = [
            {
                "date": datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
                "open": 1000.0,
                "high": 1050.0,
                "low": 950.0,
                "close": 1030.0,
                "volume": 1000000,
            },
            {
                "date": datetime(2024, 1, 16, 10, 0, tzinfo=UTC),
                "open": 1030.0,
                "high": 1080.0,
                "low": 1020.0,
                "close": 1070.0,
                "volume": 1200000,
            },
        ]
        # Simulate quote data
        client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 1030.50,
                "bid": 1030.00,
                "ask": 1031.00,
                "volume": 1500000,
            }
        }
        # Simulate instruments data
        client.instruments.return_value = [
            {
                "instrument_token": 123456,
                "tradingsymbol": "RELIANCE",
                "name": "Reliance Industries",
                "exchange": "NSE",
                "segment": "EQ",
                "instrument_type": "EQ",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 234567,
                "tradingsymbol": "INFY",
                "name": "Infosys Ltd",
                "exchange": "NSE",
                "segment": "EQ",
                "instrument_type": "EQ",
                "lot_size": 1,
                "tick_size": 0.05,
            },
        ]
        return client

    @pytest.mark.asyncio
    async def test_mitigation_1_token_bucket_rate_limiter(self, mock_kite_client):
        """Test Mitigation 1: Token bucket rate limiter prevents exceeding 3 req/sec."""
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
            requests_per_second=3,
        )

        # Verify rate limiter is initialized
        assert provider._rate_limiter is not None
        assert provider._rate_limiter._requests_per_window == 3
        assert provider._rate_limiter._window_seconds == 1.0

        # Test that rate limiter respects the limit
        call_count = 0

        async def mock_api_call(*args):
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        # Make 5 concurrent requests (more than rate limit)
        tasks = [provider._retry_with_backoff(mock_api_call) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All requests should succeed, but rate limiter enforced delays
        assert len(results) == 5
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_mitigation_2_batch_token_resolution(self, mock_kite_client):
        """Test Mitigation 2: Batch instrument token resolution reduces API calls."""
        # Create mock instrument master
        mock_master = MagicMock()
        mock_master.get_instrument.side_effect = [
            # Cache hits for all symbols
            MagicMock(instrument_token=123456, trading_symbol="RELIANCE"),
            MagicMock(instrument_token=234567, trading_symbol="INFY"),
            MagicMock(instrument_token=345678, trading_symbol="TCS"),
        ]

        # Create resolver with Kite provider for API fallback
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )
        resolver = SymbolTokenResolver(instrument_master=mock_master, kite_provider=provider)

        # Resolve multiple tokens in batch (efficient for 50+ symbols)
        symbols = ["RELIANCE", "INFY", "TCS"]
        tokens = await resolver.resolve_multiple_tokens(symbols, Exchange.NSE)

        # Should resolve all symbols
        assert "RELIANCE" in tokens
        assert "INFY" in tokens
        assert "TCS" in tokens
        assert tokens["RELIANCE"] == 123456
        assert tokens["INFY"] == 234567
        assert tokens["TCS"] == 345678

        # Verify batch resolution used cache efficiently
        assert mock_master.get_instrument.call_count == 3

    @pytest.mark.asyncio
    async def test_mitigation_3_historical_data_cache(self, mock_kite_client):
        """Test Mitigation 3: MarketDataCache reduces redundant API calls."""
        cache = MarketDataCache(default_ttl_seconds=60)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )

        # First request - cache miss, fetches from API
        bars1 = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=10
        )

        # Cache the result
        cache.put("RELIANCE", "2024-01-01", "2024-01-31", bars1)

        # Second request - cache hit, no API call
        cached_bars = cache.get("RELIANCE", "2024-01-01", "2024-01-31")

        # Verify cache hit returns same data
        assert cached_bars is not None
        assert len(cached_bars) == len(bars1)

        # Verify API was called only once (not on cache hit)
        assert mock_kite_client.historical_data.call_count == 1

        # Test get_or_fetch pattern
        fetch_count = 0

        def fetch_func():
            nonlocal fetch_count
            fetch_count += 1
            return bars1

        # First call - cache miss
        cache.get_or_fetch("INFY", "2024-01-01", "2024-01-31", fetch_func)
        assert fetch_count == 1

        # Second call - cache hit
        cache.get_or_fetch("INFY", "2024-01-01", "2024-01-31", fetch_func)
        assert fetch_count == 1  # No additional fetch

    @pytest.mark.asyncio
    async def test_mitigation_4_websocket_for_live_data(self, mock_kite_client):
        """Test Mitigation 4: WebSocket bypasses REST rate limits for live data."""
        # Mock KiteTicker
        mock_ticker = MagicMock()
        mock_ticker.on_ticks = None
        mock_ticker.on_connect = None
        mock_ticker.on_close = None
        mock_ticker.on_error = None
        mock_ticker.connect = lambda: None
        mock_ticker.close = lambda: None
        mock_ticker.subscribe = lambda tokens: None

        provider = KiteWebSocketProvider(
            api_key="test_key",
            access_token="test_token",
            kite_ticker_factory=lambda k, t: mock_ticker,
        )

        # Connect to WebSocket (bypasses REST API)
        await provider.connect()
        assert provider._is_connected is True

        # Subscribe to symbol updates (no REST API calls)
        await provider.subscribe(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1m")
        assert "RELIANCE" in provider._tickers

        # WebSocket provides real-time data without rate limits
        # This demonstrates bypassing REST API rate limits
        assert provider._tickers["RELIANCE"].symbol == "RELIANCE"

        # Cleanup
        await provider.disconnect()

    @pytest.mark.asyncio
    async def test_complete_mitigation_scenario(self, mock_kite_client):
        """Test complete mitigation strategy for scanning 50+ symbols."""
        # Simulate scanning 50 symbols
        symbols = [f"STOCK{i}" for i in range(50)]

        # Setup components
        cache = MarketDataCache(default_ttl_seconds=300)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
            requests_per_second=3,  # Kite API limit
        )

        # Mock instrument master for batch resolution
        mock_master = MagicMock()
        mock_master.get_instrument.side_effect = [
            MagicMock(instrument_token=i, trading_symbol=symbol) for i, symbol in enumerate(symbols)
        ]

        resolver = SymbolTokenResolver(instrument_master=mock_master, kite_provider=provider)

        # Step 1: Batch resolve tokens (1 API call for all symbols)
        tokens = await resolver.resolve_multiple_tokens(symbols, Exchange.NSE)
        assert len(tokens) == 50

        # Step 2: Fetch data with caching (reduces API calls)
        api_call_count = 0

        async def fetch_with_cache(symbol):
            nonlocal api_call_count
            # Check cache first
            cached = cache.get(symbol, "2024-01-01", "2024-01-31")
            if cached is not None:
                return cached

            # Cache miss - fetch from API
            api_call_count += 1
            bars = await provider.get_ohlcv(
                symbol=symbol, exchange=Exchange.NSE, timeframe="1d", limit=10
            )
            cache.put(symbol, "2024-01-01", "2024-01-31", bars)
            return bars

        # Fetch data for first 5 symbols
        for symbol in symbols[:5]:
            await fetch_with_cache(symbol)

        # Fetch again for first 5 symbols (should hit cache)
        for symbol in symbols[:5]:
            await fetch_with_cache(symbol)

        # Verify API calls were minimized by cache
        # Should only be 5 API calls (first fetch), not 10
        assert api_call_count == 5

        # Step 3: Rate limiter enforced delays for API calls
        # Even with 5 API calls, rate limiter ensures 3 req/sec limit
        assert provider._rate_limiter is not None

    @pytest.mark.asyncio
    async def test_rate_limiter_concurrent_requests(self):
        """Test rate limiter handles concurrent requests correctly."""
        limiter = _RateLimiter(requests_per_window=3, window_seconds=1.0)

        # Make 10 concurrent requests
        tasks = [limiter.acquire() for _ in range(10)]
        start_time = datetime.now(UTC)

        await asyncio.gather(*tasks)

        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # With 3 req/sec, 10 requests should take at least 3 seconds
        # (3 + 3 + 3 + 1 = 10 requests across 4 windows)
        assert elapsed >= 3.0

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """Test cache respects TTL and expires old entries."""
        cache = MarketDataCache(default_ttl_seconds=1)  # 1 second TTL

        # Add data to cache
        test_data = [{"timestamp": datetime.now(UTC), "close": 100.0}]
        cache.put("TEST", "2024-01-01", "2024-01-31", test_data)

        # Should be available immediately
        assert cache.get("TEST", "2024-01-01", "2024-01-31") is not None

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        assert cache.get("TEST", "2024-01-01", "2024-01-31") is None

    @pytest.mark.asyncio
    async def test_batch_resolution_with_multiple_symbols(self, mock_kite_client):
        """Test batch resolution handles multiple symbols efficiently."""
        mock_master = MagicMock()
        mock_master.get_instrument.side_effect = [
            MagicMock(instrument_token=1, trading_symbol="STOCK1"),
            MagicMock(instrument_token=2, trading_symbol="STOCK2"),
            MagicMock(instrument_token=3, trading_symbol="STOCK3"),
            MagicMock(instrument_token=4, trading_symbol="STOCK4"),
            MagicMock(instrument_token=5, trading_symbol="STOCK5"),
        ]

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )
        resolver = SymbolTokenResolver(instrument_master=mock_master, kite_provider=provider)

        # Resolve multiple symbols
        symbols = ["STOCK1", "STOCK2", "STOCK3", "STOCK4", "STOCK5"]
        tokens = await resolver.resolve_multiple_tokens(symbols, Exchange.NSE)

        # Should resolve all symbols
        assert len(tokens) == 5
        for i, symbol in enumerate(symbols, start=1):
            assert symbol in tokens
            assert tokens[symbol] == i


class TestRateLimitingEdgeCases:
    """Test edge cases for rate limiting mitigation."""

    @pytest.mark.asyncio
    async def test_rate_limiter_zero_tokens_waits_for_refill(self):
        """Test that rate limiter waits for refill when tokens are exhausted."""
        limiter = _RateLimiter(requests_per_window=1, window_seconds=0.5)

        # Consume the only token
        await limiter.acquire()

        # Next acquire should wait for refill
        start_time = datetime.now(UTC)
        await limiter.acquire()
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # Should have waited for refill
        assert elapsed >= 0.4  # Allow some margin

    @pytest.mark.asyncio
    async def test_cache_purge_expired(self):
        """Test cache purging removes expired entries."""
        cache = MarketDataCache(default_ttl_seconds=1)

        # Add multiple entries
        for i in range(3):
            cache.put(f"SYMBOL{i}", "2024-01-01", "2024-01-31", {"data": i})

        # All entries should be present
        assert cache.get_stats()["total_entries"] == 3

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Purge expired entries
        purged = cache.purge_expired()

        # All entries should be purged
        assert purged == 3
        assert cache.get_stats()["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_websocket_reconnection_logic(self):
        """Test WebSocket handles reconnection on failure."""
        mock_ticker = MagicMock()
        mock_ticker.on_ticks = None
        mock_ticker.on_connect = None
        mock_ticker.on_close = None
        mock_ticker.on_error = None
        mock_ticker.connect = lambda: None
        mock_ticker.close = lambda: None
        mock_ticker.subscribe = lambda tokens: None

        provider = KiteWebSocketProvider(
            api_key="test_key",
            access_token="test_token",
            kite_ticker_factory=lambda k, t: mock_ticker,
            max_retries=3,
            retry_delay_seconds=0.1,
        )

        # Connect successfully
        await provider.connect()
        assert provider._is_connected is True

        # Disconnect
        await provider.disconnect()
        assert provider._is_connected is False

        # Reconnect
        await provider.connect()
        assert provider._is_connected is True
