"""Tests for market_data_cache.py - caching and parallelization optimization."""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.data.market_data_cache import CacheEntry, MarketDataCache
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_is_expired_with_future_timestamp(self):
        """Test that entry is not expired when timestamp is in future."""
        entry = CacheEntry(
            data={"test": "data"},
            cached_at=datetime.now(UTC) + timedelta(minutes=1),
            cache_key="test_key",
        )
        assert not entry.is_expired(ttl_seconds=60)

    def test_is_expired_with_old_timestamp(self):
        """Test that entry is expired when timestamp is old."""
        entry = CacheEntry(
            data={"test": "data"},
            cached_at=datetime.now(UTC) - timedelta(minutes=2),
            cache_key="test_key",
        )
        assert entry.is_expired(ttl_seconds=60)

    def test_is_expired_at_boundary(self):
        """Test expiration at exact TTL boundary."""
        entry = CacheEntry(
            data={"test": "data"},
            cached_at=datetime.now(UTC) - timedelta(seconds=60),
            cache_key="test_key",
        )
        assert entry.is_expired(ttl_seconds=60)


class TestMarketDataCache:
    """Test MarketDataCache functionality."""

    def test_cache_initialization(self):
        """Test cache initialization with default TTL."""
        cache = MarketDataCache()
        assert cache._default_ttl_seconds == 60

    def test_cache_initialization_custom_ttl(self):
        """Test cache initialization with custom TTL."""
        cache = MarketDataCache(default_ttl_seconds=120)
        assert cache._default_ttl_seconds == 120

    def test_put_and_get_cached_data(self):
        """Test storing and retrieving cached data."""
        cache = MarketDataCache()
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data)
        cached = cache.get("TCS", "2024-01-01", "2024-01-31")

        assert cached is not None
        assert cached.symbol == "TCS"
        assert cached.close_price == Decimal("3500")

    def test_get_returns_none_for_miss(self):
        """Test that cache miss returns None."""
        cache = MarketDataCache()
        result = cache.get("NONEXISTENT", "2024-01-01", "2024-01-31")
        assert result is None

    def test_cache_expiration(self):
        """Test that expired entries are not returned."""
        cache = MarketDataCache(default_ttl_seconds=1)
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data)
        time.sleep(1.1)  # Wait for expiration
        result = cache.get("TCS", "2024-01-01", "2024-01-31")

        assert result is None

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = MarketDataCache()
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data)

        # Miss
        cache.get("NONEXISTENT", "2024-01-01", "2024-01-31")

        # Hit
        cache.get("TCS", "2024-01-01", "2024-01-31")

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["total_entries"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_clear(self):
        """Test clearing all cache entries."""
        cache = MarketDataCache()
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data)
        assert cache.get_stats()["total_entries"] == 1

        cache.clear()
        assert cache.get_stats()["total_entries"] == 0
        assert cache.get_stats()["hits"] == 0
        assert cache.get_stats()["misses"] == 0

    def test_purge_expired(self):
        """Test purging expired entries."""
        cache = MarketDataCache(default_ttl_seconds=1)

        # Add fresh entry
        fresh_data = MarketData(
            symbol="FRESH",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("90"),
            volume=Decimal("1000"),
            avg_volume=Decimal("500"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
        cache.put("FRESH", "2024-01-01", "2024-01-31", fresh_data)

        # Add old entry that will expire
        old_data = MarketData(
            symbol="OLD",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("90"),
            volume=Decimal("1000"),
            avg_volume=Decimal("500"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
        cache.put("OLD", "2024-01-01", "2024-01-31", old_data)

        assert cache.get_stats()["total_entries"] == 2

        time.sleep(1.1)  # Wait for expiration

        purged = cache.purge_expired()
        assert purged == 2  # Both entries expire since added at same time
        assert cache.get_stats()["total_entries"] == 0

    def test_get_or_fetch_with_cache_hit(self):
        """Test get_or_fetch returns cached data when available."""
        cache = MarketDataCache()
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data)

        fetch_called = False

        def fetch_func():
            nonlocal fetch_called
            fetch_called = True
            return None

        result = cache.get_or_fetch("TCS", "2024-01-01", "2024-01-31", fetch_func)

        assert result is not None
        assert result.symbol == "TCS"
        assert not fetch_called  # Fetch function should not be called

    def test_get_or_fetch_with_cache_miss(self):
        """Test get_or_fetch calls fetch function on cache miss."""
        cache = MarketDataCache()
        test_data = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        fetch_called = False

        def fetch_func():
            nonlocal fetch_called
            fetch_called = True
            return test_data

        result = cache.get_or_fetch("TCS", "2024-01-01", "2024-01-31", fetch_func)

        assert result is not None
        assert result.symbol == "TCS"
        assert fetch_called  # Fetch function should be called

        # Verify data was cached
        cached = cache.get("TCS", "2024-01-01", "2024-01-31")
        assert cached is not None

    def test_different_keys_for_different_parameters(self):
        """Test that different parameters generate different cache keys."""
        cache = MarketDataCache()
        test_data1 = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3500"),
            prev_close_price=Decimal("3400"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3550"),
            low_price=Decimal("3450"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )

        test_data2 = MarketData(
            symbol="TCS",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("3600"),
            prev_close_price=Decimal("3500"),
            volume=Decimal("2000000"),
            avg_volume=Decimal("600000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("3650"),
            low_price=Decimal("3550"),
            adx=Decimal("35"),
            atr_pct=Decimal("0.03"),
            breadth_ratio=Decimal("1.6"),
        )

        cache.put("TCS", "2024-01-01", "2024-01-31", test_data1)
        cache.put("TCS", "2024-02-01", "2024-02-28", test_data2)

        result1 = cache.get("TCS", "2024-01-01", "2024-01-31")
        result2 = cache.get("TCS", "2024-02-01", "2024-02-28")

        assert result1 is not None
        assert result2 is not None
        assert result1.close_price == Decimal("3500")
        assert result2.close_price == Decimal("3600")
        assert cache.get_stats()["total_entries"] == 2


class TestScannerParallelization:
    """Test InstrumentScanner parallelization with cache."""

    def test_scanner_initialization_with_cache(self):
        """Test that scanner initializes with cache."""
        scanner = InstrumentScanner(
            symbols=["TCS", "INFY"],
            cache_ttl_seconds=120,
        )
        assert scanner._cache is not None
        assert scanner._cache._default_ttl_seconds == 120

    def test_scanner_with_custom_data_bypasses_cache(self):
        """Test that custom data bypasses cache entirely."""
        scanner = InstrumentScanner(
            sentiment_analyzer=create_mock_sentiment_analyzer({"TCS": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
            symbols=[],
        )

        custom_data = [
            MarketData(
                symbol="TCS",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal("3500"),
                prev_close_price=Decimal("3400"),
                volume=Decimal("2000000"),
                avg_volume=Decimal("500000"),
                timestamp_utc=datetime.now(UTC),
                high_price=Decimal("3550"),
                low_price=Decimal("3450"),
                adx=Decimal("30"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
        ]

        result = scanner.scan(custom_data=custom_data)

        assert result.total_scanned == 1
        # Cache should remain empty
        assert scanner._cache.get_stats()["total_entries"] == 0

    def test_scanner_cache_stats_after_scan_with_custom_data(self):
        """Test that cache stats are tracked correctly."""
        scanner = InstrumentScanner(
            sentiment_analyzer=create_mock_sentiment_analyzer({"TCS": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
            symbols=[],
            cache_ttl_seconds=60,
        )

        custom_data = [
            MarketData(
                symbol="TCS",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal("3500"),
                prev_close_price=Decimal("3400"),
                volume=Decimal("2000000"),
                avg_volume=Decimal("500000"),
                timestamp_utc=datetime.now(UTC),
                high_price=Decimal("3550"),
                low_price=Decimal("3450"),
                adx=Decimal("30"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
        ]

        scanner.scan(custom_data=custom_data)

        stats = scanner._cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_entries"] == 0
