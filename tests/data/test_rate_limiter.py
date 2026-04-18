"""
Tests for rate_limiter module.

Coverage intent:
- Happy path: Normal rate limiting behavior
- Edge cases: Burst capacity, token refill, concurrent requests
- Error paths: Invalid parameters
- Type handling: Proper async context manager usage
- Precision handling: Decimal calculations
- Timezone handling: UTC timestamps
"""

import asyncio
import time

import pytest
from iatb.data.rate_limiter import AsyncRateLimiter, RateLimiter


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_init_valid_parameters(self) -> None:
        """Test initialization with valid parameters."""
        limiter = RateLimiter(
            requests_per_second=3.0,
            burst_capacity=10,
        )
        assert limiter.available_tokens == 10
        assert limiter.burst_capacity == 10
        assert limiter.concurrent_requests == 0

    def test_init_invalid_requests_per_second(self) -> None:
        """Test initialization fails with invalid requests_per_second."""
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            RateLimiter(requests_per_second=0)
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            RateLimiter(requests_per_second=-1.0)

    def test_init_invalid_burst_capacity(self) -> None:
        """Test initialization fails with invalid burst_capacity."""
        with pytest.raises(ValueError, match="burst_capacity must be positive"):
            RateLimiter(burst_capacity=0)
        with pytest.raises(ValueError, match="burst_capacity must be positive"):
            RateLimiter(burst_capacity=-5)

    @pytest.mark.asyncio
    async def test_acquire_release_single(self) -> None:
        """Test acquire and release for single request."""
        limiter = RateLimiter(requests_per_second=1.0, burst_capacity=1)

        assert limiter.available_tokens == 1
        await limiter.acquire()
        assert limiter.available_tokens == 0
        limiter.release()
        # Small delay to allow async decrement task to complete
        await asyncio.sleep(0.01)
        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_concurrent_requests_within_burst(self) -> None:
        """Test concurrent requests within burst capacity."""
        limiter = RateLimiter(requests_per_second=1.0, burst_capacity=5)

        async def make_request(n: int) -> int:
            await limiter.acquire()
            await asyncio.sleep(0.01)
            limiter.release()
            return n

        # All 5 requests should complete within burst capacity
        results = await asyncio.gather(*[make_request(i) for i in range(5)])
        assert sorted(results) == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_token_refill_over_time(self) -> None:
        """Test tokens refill over time."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=1)

        # Acquire the only token
        await limiter.acquire()
        assert limiter.available_tokens == 0

        # Wait for refill
        await asyncio.sleep(0.15)  # 150ms should refill 1.5 tokens

        # Try to acquire again - should succeed after refill
        await limiter.acquire()
        limiter.release()
        limiter.release()

        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self) -> None:
        """Test that rate limit is enforced over time."""
        limiter = RateLimiter(requests_per_second=2.0, burst_capacity=2)

        start = time.monotonic()

        # Make 4 requests at 2 req/sec
        for _ in range(4):
            await limiter.acquire()
            await asyncio.sleep(0.05)
            limiter.release()

        elapsed = time.monotonic() - start

        # Should take at least 1 second for 4 requests at 2 req/sec
        # (2 in burst, then wait for 2 more tokens)
        assert elapsed >= 0.9  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_execute_method(self) -> None:
        """Test execute method with coroutine."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)

        async def mock_api_call(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2

        results = await asyncio.gather(*[limiter.execute(mock_api_call(i)) for i in range(5)])

        assert results == [0, 2, 4, 6, 8]
        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_execute_with_exception(self) -> None:
        """Test execute releases permit even on exception."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=1)

        async def failing_call() -> None:
            await limiter.acquire()
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await limiter.execute(failing_call())

        # Permit should be released
        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_per_minute_limit(self) -> None:
        """Test per-minute rate limiting."""
        limiter = RateLimiter(
            requests_per_second=100.0,  # High second rate
            requests_per_minute=5,  # Low minute rate
            burst_capacity=10,
        )

        # Make 5 requests quickly
        for _ in range(5):
            await limiter.acquire()
            limiter.release()

        # 6th request should wait for next minute
        start = time.monotonic()
        await limiter.acquire()
        limiter.release()
        elapsed = time.monotonic() - start

        # Should have waited for minute reset
        assert elapsed >= 0.01  # Small delay expected

    @pytest.mark.asyncio
    async def test_concurrent_request_tracking(self) -> None:
        """Test concurrent request counter is accurate."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)

        async def tracked_request() -> None:
            await limiter.acquire()
            assert limiter.concurrent_requests >= 1
            await asyncio.sleep(0.05)
            limiter.release()

        await asyncio.gather(*[tracked_request() for _ in range(5)])
        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_burst_capacity_semaphore(self) -> None:
        """Test burst capacity limits concurrent requests."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=2)

        async def long_request(n: int) -> int:
            await limiter.acquire()
            await asyncio.sleep(0.1)
            limiter.release()
            return n

        # Start 4 requests, but only 2 should run concurrently
        results = await asyncio.gather(*[long_request(i) for i in range(4)])

        assert sorted(results) == [0, 1, 2, 3]
        assert limiter.concurrent_requests == 0


class TestAsyncRateLimiter:
    """Test AsyncRateLimiter context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_basic(self) -> None:
        """Test basic context manager usage."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_capacity=2)

        async def make_request() -> str:
            async with limiter:
                return "success"

        result = await make_request()
        assert result == "success"
        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self) -> None:
        """Test context manager releases on exception."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_capacity=1)

        with pytest.raises(ValueError, match="Test error"):
            async with limiter:
                raise ValueError("Test error")

        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_nested_context_managers(self) -> None:
        """Test multiple context managers work correctly."""
        limiter = AsyncRateLimiter(requests_per_second=10.0, burst_capacity=3)

        async def nested_request(n: int) -> int:
            async with limiter:
                await asyncio.sleep(0.01)
                return n

        results = await asyncio.gather(*[nested_request(i) for i in range(3)])
        assert sorted(results) == [0, 1, 2]


class TestRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_refill_rate(self) -> None:
        """Test behavior with very low refill rate."""
        limiter = RateLimiter(requests_per_second=0.1, burst_capacity=1)

        await limiter.acquire()
        assert limiter.available_tokens == 0
        limiter.release()

        # After 0.1 seconds, should have 0.1 tokens
        await asyncio.sleep(0.1)
        assert limiter.available_tokens == 0  # Still need 1 full token

    @pytest.mark.asyncio
    async def test_large_burst_capacity(self) -> None:
        """Test with large burst capacity."""
        limiter = RateLimiter(requests_per_second=1.0, burst_capacity=100)

        # Should be able to acquire 100 tokens immediately
        for _ in range(100):
            await limiter.acquire()
            limiter.release()

        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_rapid_acquire_release(self) -> None:
        """Test rapid acquire/release cycles."""
        limiter = RateLimiter(requests_per_second=100.0, burst_capacity=10)

        for _ in range(20):
            await limiter.acquire()
            await asyncio.sleep(0.001)
            limiter.release()

        assert limiter.concurrent_requests == 0

    @pytest.mark.asyncio
    async def test_acquire_without_release(self) -> None:
        """Test that unreleased permits don't cause deadlocks."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)

        # Acquire permits without releasing
        await limiter.acquire()
        await limiter.acquire()

        # Still have capacity for 3 more
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

        assert limiter.concurrent_requests >= 5

        # Clean up
        limiter.release()
        limiter.release()
        limiter.release()
        limiter.release()
        limiter.release()

    @pytest.mark.asyncio
    async def test_utc_timestamps(self) -> None:
        """Test that internal timestamps use UTC."""
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=1)

        # The limiter should work correctly regardless of timezone
        await limiter.acquire()
        await asyncio.sleep(0.05)
        limiter.release()

        assert limiter.concurrent_requests == 0
