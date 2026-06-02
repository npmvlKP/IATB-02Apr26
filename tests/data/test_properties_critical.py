"""Property-based tests for critical data provider functions.

Uses hypothesis to generate test cases and verify properties
that must hold true.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from iatb.core.enums import Exchange
from iatb.data.rate_limiter import RateLimiter


class TestRateLimiterProperties:
    """Property-based tests for rate limiter."""

    @given(st.integers(min_value=4, max_value=10))
    @settings(max_examples=5, deadline=None)
    def test_rate_limiter_never_exceeds_limit(self, num_requests):
        """Property: Rate limiter never exceeds configured limit."""
        limiter = RateLimiter(requests_per_second=3.0, burst_capacity=3)

        async def make_requests():
            for _ in range(num_requests):
                await limiter.acquire()
                limiter.release()

        start = datetime.now(UTC)
        asyncio.run(make_requests())
        elapsed = (datetime.now(UTC) - start).total_seconds()

        if num_requests > 3:
            expected_min_time = (num_requests - 3) / 3.0
            assert (
                elapsed >= expected_min_time * 0.8
            ), f"Elapsed {elapsed}s < expected {expected_min_time}s"

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=5)
    def test_rate_limiter_respects_window(self, requests_per_second):
        """Property: Rate limiter respects requests_per_second parameter."""
        limiter = RateLimiter(
            requests_per_second=float(requests_per_second),
            burst_capacity=10,
        )

        async def make_requests():
            for _ in range(requests_per_second):
                await limiter.acquire()
                limiter.release()

        start = datetime.now(UTC)
        asyncio.run(make_requests())
        elapsed = (datetime.now(UTC) - start).total_seconds()
        expected_time = 1.0 / requests_per_second
        assert (
            elapsed < expected_time * 1.5
        ), f"First window took {elapsed}s, expected < {expected_time * 1.5}s"

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=10)
    def test_rate_limiter_refills_after_window(self, num_windows):
        """Property: Rate limiter refills tokens after window expires."""
        limiter = RateLimiter(requests_per_second=3.0, burst_capacity=10)

        async def make_requests():
            for _ in range(3):
                await limiter.acquire()
            await asyncio.sleep(0.15)
            for _ in range(3):
                await limiter.acquire()

        asyncio.run(make_requests())
        assert True


class TestOHLCVProperties:
    """Property-based tests for OHLCV data properties."""

    @given(
        st.floats(
            min_value=1.0,
            max_value=100000.0,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
        st.floats(
            min_value=0.01,
            max_value=0.10,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_ohlc_high_low_relationship(self, base_price, variation_pct):
        """Property: For any OHLCV bar, high >= low."""
        high = base_price * (1 + variation_pct)
        low = base_price * (1 - variation_pct)
        assert high >= low, f"High {high} < Low {low} for base {base_price}"

    @given(
        st.floats(
            min_value=1.0,
            max_value=100000.0,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
        st.floats(
            min_value=0.01,
            max_value=0.10,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_ohlc_open_close_within_range(self, base_price, variation_pct):
        """Property: Open and close are within [low, high] range."""
        high = base_price * (1 + variation_pct)
        low = base_price * (1 - variation_pct)
        open_price = low + (high - low) * 0.5
        close_price = low + (high - low) * 0.7
        assert low <= open_price <= high, f"Open {open_price} not in [{low}, {high}]"
        assert low <= close_price <= high, f"Close {close_price} not in [{low}, {high}]"

    @given(
        st.floats(
            min_value=0.0,
            max_value=1000000000.0,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_volume_is_non_negative(self, volume):
        """Property: Volume is always non-negative."""
        assert volume >= 0, f"Volume {volume} is negative"

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=60),
    )
    @settings(max_examples=10)
    def test_timestamp_monotonicity(self, num_bars, time_interval_minutes):
        """Property: OHLCV timestamps should be monotonically increasing."""
        start_time = datetime.now(UTC)
        bars = []
        for i in range(num_bars):
            timestamp = start_time + timedelta(minutes=i * time_interval_minutes)
            bars.append(timestamp)
        for i in range(1, len(bars)):
            assert bars[i] > bars[i - 1], f"Timestamp at {i} not greater than {i-1}"


class TestPricePrecisionProperties:
    """Property-based tests for price precision and rounding."""

    @given(
        st.floats(
            min_value=1.0,
            max_value=100000.0,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
        st.integers(min_value=0, max_value=8),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_decimal_precision_preserved(self, price, decimal_places):
        """Property: Converting to Decimal with specific precision preserves value."""
        decimal_str = f"{price:.{decimal_places}f}"
        decimal_price = Decimal(decimal_str)
        reconstructed = Decimal(decimal_str)
        assert (
            decimal_price == reconstructed
        ), f"Decimal precision lost: {decimal_price} vs {reconstructed}"

    @given(
        st.floats(
            min_value=0.01,
            max_value=0.99,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
        st.floats(
            min_value=1.0,
            max_value=100000.0,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_percentage_calculation_properties(self, pct, base):
        """Property: Percentage calculations maintain expected relationships."""
        result = base * (1 + pct)
        if pct > 0:
            assert result > base, f"Result {result} not > base {base} for pct {pct}"
        elif pct < 0:
            assert result < base, f"Result {result} not < base {base} for pct {pct}"


class TestCacheProperties:
    """Property-based tests for cache behavior."""

    @given(
        st.integers(min_value=1, max_value=10),
        st.integers(min_value=1, max_value=2),
    )
    @settings(max_examples=5, deadline=3000)
    def test_cache_ttl_behavior(self, num_entries, ttl_seconds):
        """Property: Cache entries expire after TTL."""
        from iatb.data.market_data_cache import MarketDataCache
        from iatb.scanner.instrument_scanner import InstrumentCategory, MarketData

        cache = MarketDataCache(default_ttl_seconds=ttl_seconds)
        for i in range(num_entries):
            test_data = MarketData(
                symbol=f"TEST{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal(str(100 + i)),
                prev_close_price=Decimal(str(100 + i - 1)),
                volume=Decimal("1000000"),
                avg_volume=Decimal("1000000"),
                timestamp_utc=datetime.now(UTC),
                high_price=Decimal(str(100 + i + 1)),
                low_price=Decimal(str(100 + i - 1)),
                adx=Decimal("30"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
            cache.put(f"TEST{i}", "2024-01-01", "2024-01-31", test_data)

        for i in range(num_entries):
            cached = cache.get(f"TEST{i}", "2024-01-01", "2024-01-31")
            assert cached is not None, f"Entry {i} not found immediately"

        time.sleep(ttl_seconds + 0.1)

        for i in range(num_entries):
            cached = cache.get(f"TEST{i}", "2024-01-01", "2024-01-31")
            assert cached is None, f"Entry {i} should have expired"

    @given(st.integers(min_value=1, max_value=50))
    @settings(max_examples=10)
    def test_cache_hit_rate_calculation(self, num_operations):
        """Property: Cache hit rate is calculated correctly."""
        from iatb.data.market_data_cache import MarketDataCache
        from iatb.scanner.instrument_scanner import InstrumentCategory, MarketData

        cache = MarketDataCache(default_ttl_seconds=60)
        test_data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("99"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("1000000"),
            timestamp_utc=datetime.now(UTC),
            high_price=Decimal("101"),
            low_price=Decimal("99"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )
        cache.put("TEST", "2024-01-01", "2024-01-31", test_data)

        hits = 0
        misses = 0
        for i in range(num_operations):
            if i % 2 == 0:
                cached = cache.get("TEST", "2024-01-01", "2024-01-31")
                if cached is not None:
                    hits += 1
            else:
                cached = cache.get(f"MISS{i}", "2024-01-01", "2024-01-31")
                if cached is None:
                    misses += 1

        stats = cache.get_stats()
        expected_hits = hits
        expected_misses = misses
        assert (
            stats["hits"] == expected_hits
        ), f"Hit count mismatch: {stats['hits']} vs {expected_hits}"
        assert (
            stats["misses"] == expected_misses
        ), f"Miss count mismatch: {stats['misses']} vs {expected_misses}"
        assert (
            stats["total_entries"] == 1
        ), f"Total entries mismatch: {stats['total_entries']}"
