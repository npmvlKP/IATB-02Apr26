"""
Rate limiter for concurrent API requests with burst capacity.

Implements a token bucket algorithm that allows burst concurrency while
respecting overall rate limits per second and per minute.
"""

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any, TypeVar

_T = TypeVar("_T")


class RateLimiter:
    """Token bucket rate limiter with burst capacity.

    This rate limiter allows concurrent requests up to a burst limit,
    while ensuring the overall rate limit is respected over time.

    Example:
        limiter = RateLimiter(
            requests_per_second=3,
            burst_capacity=10
        )
        await limiter.acquire()
        # Make API request
    """

    def __init__(
        self,
        *,
        requests_per_second: float = 3.0,
        requests_per_minute: int | None = None,
        burst_capacity: int = 10,
    ) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_second: Target rate limit in requests per second.
            requests_per_minute: Optional per-minute limit (overrides second-based).
            burst_capacity: Maximum concurrent requests allowed.

        Raises:
            ValueError: If parameters are invalid.
        """
        if requests_per_second <= 0:
            msg = "requests_per_second must be positive"
            raise ValueError(msg)
        if burst_capacity <= 0:
            msg = "burst_capacity must be positive"
            raise ValueError(msg)

        self._requests_per_second = requests_per_second
        self._requests_per_minute = requests_per_minute
        self._burst_capacity = burst_capacity

        # Token bucket state
        self._tokens = float(burst_capacity)
        self._last_refill = datetime.now(UTC)
        self._bucket_capacity = float(burst_capacity)

        # Per-minute tracking (if enabled)
        self._minute_count = 0
        self._minute_start = datetime.now(UTC)
        self._minute_limit: int | None = None

        # Current concurrent requests count
        self._concurrent_count = 0
        self._concurrent_lock = asyncio.Lock()

        # Semaphore for burst capacity
        self._semaphore = asyncio.Semaphore(burst_capacity)

        # Calculate token refill rate
        if requests_per_minute is not None:
            self._refill_rate = requests_per_minute / 60.0
            self._minute_limit = requests_per_minute
        else:
            self._refill_rate = requests_per_second
            self._minute_limit = None

    async def acquire(self) -> None:
        """Acquire permission to make a request.

        Waits if necessary until a token is available and burst capacity allows.

        This method is thread-safe and can be called concurrently from
        multiple coroutines.
        """
        # Wait for burst capacity
        await self._semaphore.acquire()

        try:
            # Refill tokens based on elapsed time
            await self._refill_tokens()

            # Wait for token availability
            while self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._refill_rate
                await asyncio.sleep(wait_time)
                await self._refill_tokens()

            # Consume a token
            self._tokens -= 1.0

            # Track concurrent requests
            async with self._concurrent_lock:
                self._concurrent_count += 1

            # Track per-minute limit
            if self._minute_limit is not None:
                await self._check_minute_limit()
        except Exception:
            # Release semaphore on error
            self._semaphore.release()
            raise

    def release(self) -> None:
        """Release permission after request completes.

        Must be called after each acquired request completes.
        """
        # Release burst capacity
        self._semaphore.release()

        # Decrement concurrent count
        async def _decrement() -> None:
            async with self._concurrent_lock:
                if self._concurrent_count > 0:
                    self._concurrent_count -= 1

        asyncio.create_task(_decrement())

    async def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.now(UTC)
        elapsed = (now - self._last_refill).total_seconds()

        if elapsed > 0:
            # Calculate tokens to add
            new_tokens = elapsed * self._refill_rate
            self._tokens = min(self._bucket_capacity, self._tokens + new_tokens)
            self._last_refill = now

    async def _check_minute_limit(self) -> None:
        """Check and enforce per-minute limit."""
        if self._minute_limit is None:
            return

        now = datetime.now(UTC)
        elapsed_seconds = (now - self._minute_start).total_seconds()

        # Reset minute counter if minute has passed
        if elapsed_seconds >= 60.0:
            self._minute_count = 0
            self._minute_start = now
        else:
            # Check if we've exceeded minute limit
            if self._minute_count >= self._minute_limit:
                # Wait until next minute
                wait_time = 60.0 - elapsed_seconds
                await asyncio.sleep(wait_time)
                self._minute_count = 0
                self._minute_start = datetime.now(UTC)

        self._minute_count += 1

    async def execute(
        self,
        coro: Awaitable[_T],
    ) -> _T:
        """Execute a coroutine with rate limiting.

        Acquires a permit, executes the coroutine, and releases the permit.

        Args:
            coro: Coroutine to execute.

        Returns:
            Result of the coroutine.

        Example:
            result = await limiter.execute(api_client.fetch_data())
        """
        await self.acquire()
        try:
            return await coro
        finally:
            self.release()

    @property
    def available_tokens(self) -> int:
        """Get number of available tokens."""
        return int(self._tokens)

    @property
    def concurrent_requests(self) -> int:
        """Get current number of concurrent requests."""
        return self._concurrent_count

    @property
    def burst_capacity(self) -> int:
        """Get burst capacity."""
        return self._burst_capacity


class AsyncRateLimiter(RateLimiter):
    """Async rate limiter with context manager support.

    Example:
        limiter = AsyncRateLimiter(requests_per_second=3)
        async with limiter:
            await api_call()
    """

    async def __aenter__(self) -> "AsyncRateLimiter":
        """Enter context manager, acquiring a permit."""
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, releasing the permit."""
        self.release()
