"""
Rate limiter for concurrent API requests with burst capacity.

Implements a token bucket algorithm that allows burst concurrency while
respecting overall rate limits per second and per minute.
Also includes retry/backoff strategy with circuit breaker for API resilience.
"""

import asyncio
import random
from collections.abc import Awaitable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

from iatb.core.exceptions import ConfigError

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
        self._validate_params(requests_per_second, burst_capacity)
        self._requests_per_second = requests_per_second
        self._requests_per_minute = requests_per_minute
        self._burst_capacity = burst_capacity

        self._tokens = float(burst_capacity)
        self._last_refill = datetime.now(UTC)
        self._bucket_capacity = float(burst_capacity)

        self._minute_count = 0
        self._minute_start = datetime.now(UTC)
        self._minute_limit: int | None = None

        self._concurrent_count = 0
        self._concurrent_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(burst_capacity)

        self._refill_rate, self._minute_limit = self._calculate_refill_rate(
            requests_per_second, requests_per_minute
        )

    @staticmethod
    def _validate_params(requests_per_second: float, burst_capacity: int) -> None:
        """Validate rate limiter parameters."""
        if requests_per_second <= 0:
            msg = "requests_per_second must be positive"
            raise ValueError(msg)
        if burst_capacity <= 0:
            msg = "burst_capacity must be positive"
            raise ValueError(msg)

    @staticmethod
    def _calculate_refill_rate(
        requests_per_second: float, requests_per_minute: int | None
    ) -> tuple[float, int | None]:
        """Calculate token refill rate and minute limit."""
        if requests_per_minute is not None:
            return requests_per_minute / 60.0, requests_per_minute  # noqa: G7
        return requests_per_second, None

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
        # Decrement concurrent count immediately (synchronously)
        # Note: This assumes release() is called from an async context
        # The concurrent lock is not needed here because decrement is atomic
        if self._concurrent_count > 0:
            self._concurrent_count -= 1

        # Release burst capacity
        self._semaphore.release()

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


# ============================================================================
# Retry/Backoff and Circuit Breaker Implementation
# ============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, requests fail immediately
    HALF_OPEN = "half_open"  # Testing if service has recovered


class CircuitOpenError(ConfigError):
    """Raised when circuit breaker is open and blocks a request."""

    def __init__(self, circuit_name: str) -> None:
        self.circuit_name = circuit_name
        msg = f"Circuit '{circuit_name}' is open - too many failures"
        super().__init__(msg)


class CircuitBreaker:
    """Circuit breaker pattern for API resilience.

    Prevents cascading failures by opening after consecutive failures
    and allowing recovery after a timeout period.

    Example:
        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0)
        await breaker.acquire()
        try:
            result = await api_call()
            await breaker.record_success()
        except Exception:
            await breaker.record_failure()
            raise
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        name: str = "default",
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening.
            reset_timeout: Seconds to wait before attempting recovery.
            name: Name for this circuit breaker (for logging/errors).

        Raises:
            ValueError: If parameters are invalid.
        """
        if failure_threshold <= 0:
            msg = "failure_threshold must be positive"
            raise ValueError(msg)
        if reset_timeout <= 0:
            msg = "reset_timeout must be positive"
            raise ValueError(msg)

        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._name = name
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._state = CircuitState.CLOSED
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Check if request should proceed based on circuit state.

        Raises:
            CircuitOpenError: If circuit is open.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if reset timeout has passed
                if self._last_failure_time is not None:
                    elapsed = (datetime.now(UTC) - self._last_failure_time).total_seconds()
                    if elapsed >= self._reset_timeout:
                        # Transition to HALF_OPEN to test recovery
                        self._state = CircuitState.HALF_OPEN
                        logger = __import__("logging").getLogger(__name__)  # Lazy import
                        logger.info(f"Circuit '{self._name}' transitioning to HALF_OPEN")
                        return  # Allow request through
                raise CircuitOpenError(self._name)
            # Circuit is CLOSED or HALF_OPEN, allow request
            return

    async def record_success(self) -> None:
        """Record a successful request.

        Resets failure count and closes circuit if in HALF_OPEN state.
        """
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger = __import__("logging").getLogger(__name__)
                logger.info(f"Circuit '{self._name}' closed - service recovered")

    async def record_failure(self) -> None:
        """Record a failed request.

        Increments failure count and opens circuit if threshold reached.
        """
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(UTC)

            if self._failure_count >= self._failure_threshold:
                if self._state != CircuitState.OPEN:
                    self._state = CircuitState.OPEN
                    logger = __import__("logging").getLogger(__name__)
                    logger.warning(
                        f"Circuit '{self._name}' opened after {self._failure_count} failures"
                    )

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count


class RetryConfig:
    """Configuration for retry behavior.

    Example:
        config = RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            jitter_seconds=0.5
        )
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter_seconds: float = 0.5,
        circuit_failure_threshold: int = 5,
        circuit_reset_timeout: float = 60.0,
    ) -> None:
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_delay: Initial delay in seconds before first retry.
            max_delay: Maximum delay cap in seconds.
            backoff_multiplier: Exponential backoff multiplier.
            jitter_seconds: Random jitter range (0 to this value).
            circuit_failure_threshold: Failures before circuit opens.
            circuit_reset_timeout: Seconds before circuit reset attempt.

        Raises:
            ValueError: If parameters are invalid.
        """
        self._validate_retry_config(
            max_retries,
            initial_delay,
            max_delay,
            backoff_multiplier,
            jitter_seconds,
            circuit_failure_threshold,
            circuit_reset_timeout,
        )

        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter_seconds = jitter_seconds
        self.circuit_failure_threshold = circuit_failure_threshold
        self.circuit_reset_timeout = circuit_reset_timeout

    @staticmethod
    def _validate_retry_config(
        max_retries: int,
        initial_delay: float,
        max_delay: float,
        backoff_multiplier: float,
        jitter_seconds: float,
        circuit_failure_threshold: int,
        circuit_reset_timeout: float,
    ) -> None:
        """Validate retry configuration parameters."""
        if max_retries < 0:
            msg = "max_retries must be non-negative"
            raise ValueError(msg)
        if initial_delay < 0:
            msg = "initial_delay must be non-negative"
            raise ValueError(msg)
        if max_delay <= 0:
            msg = "max_delay must be positive"
            raise ValueError(msg)
        if backoff_multiplier <= 1.0:
            msg = "backoff_multiplier must be greater than 1.0"
            raise ValueError(msg)
        if jitter_seconds < 0:
            msg = "jitter_seconds must be non-negative"
            raise ValueError(msg)
        if circuit_failure_threshold <= 0:
            msg = "circuit_failure_threshold must be positive"
            raise ValueError(msg)
        if circuit_reset_timeout <= 0:
            msg = "circuit_reset_timeout must be positive"
            raise ValueError(msg)


async def retry_with_backoff(
    func: Any,  # noqa: ANN401
    *,
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs: Any,
) -> _T:
    """Execute async function with exponential backoff and circuit breaker.

    Args:
        func: Async callable function that returns a coroutine.
        config: Retry configuration (uses defaults if None).
        circuit_breaker: Optional circuit breaker instance.
        **kwargs: Arguments to pass to the function.

    Returns:
        Result of the function if successful.

    Raises:
        ConfigError: If all retries exhausted or non-retryable error occurs.
        CircuitOpenError: If circuit breaker is open.

    Example:
        result = await retry_with_backoff(
            api_client.fetch_data,
            symbol="RELIANCE",
            config=RetryConfig(max_retries=3),
            circuit_breaker=breaker
        )
    """
    config = config or RetryConfig()
    circuit_breaker = circuit_breaker or CircuitBreaker(
        failure_threshold=config.circuit_failure_threshold,
        reset_timeout=config.circuit_reset_timeout,
    )
    logger = __import__("logging").getLogger(__name__)

    for attempt in range(config.max_retries + 1):
        await _check_circuit_breaker(circuit_breaker, logger)
        try:
            result = await func(**kwargs)
            await circuit_breaker.record_success()
            return result
        except Exception as e:
            if await _handle_error(e, circuit_breaker, config, attempt, logger):
                continue
            raise

    raise ConfigError("All retries exhausted")


async def _check_circuit_breaker(circuit_breaker: CircuitBreaker, logger: Any) -> None:
    """Check if circuit breaker allows request."""
    try:
        await circuit_breaker.acquire()
    except CircuitOpenError:
        logger.warning(f"Circuit '{circuit_breaker._name}' is open, blocking request")
        raise


async def _handle_error(
    exc: Exception,
    circuit_breaker: CircuitBreaker,
    config: RetryConfig,
    attempt: int,
    logger: Any,
) -> bool:
    """Handle error and determine if retry should continue.

    Returns True if retry should continue, False if error should be raised.
    """
    error_msg = str(exc)

    if await _is_non_retryable_auth_error(exc, error_msg, circuit_breaker, logger):
        return False
    if not _is_retryable_error(error_msg):
        await circuit_breaker.record_failure()
        logger.error(f"Non-retryable error: {error_msg}")
        raise ConfigError(f"Non-retryable error: {error_msg}") from exc
    if attempt >= config.max_retries:
        await circuit_breaker.record_failure()
        logger.error(f"All {config.max_retries} retries exhausted. Last error: {error_msg}")
        raise ConfigError(f"failed after {config.max_retries} retries: {error_msg}") from exc

    await circuit_breaker.record_failure()
    delay = _calculate_retry_delay(config, attempt)
    logger.warning(
        f"Attempt {attempt + 1}/{config.max_retries + 1} failed: {error_msg}. "
        f"Retrying in {delay:.2f}s..."
    )
    await asyncio.sleep(delay)
    return True


async def _is_non_retryable_auth_error(
    exc: Exception, error_msg: str, circuit_breaker: CircuitBreaker, logger: Any
) -> bool:
    """Check if error is non-retryable auth error."""
    if "401" in error_msg or "Unauthorized" in error_msg:
        logger.error("Non-retryable error: 401 Unauthorized")
        await circuit_breaker.record_failure()
        raise ConfigError("Non-retryable error: 401 Unauthorized") from exc
    if "403" in error_msg or "Forbidden" in error_msg:
        logger.error("Non-retryable error: 403 Forbidden")
        await circuit_breaker.record_failure()
        raise ConfigError("Non-retryable error: 403 Forbidden") from exc
    return False


def _is_retryable_error(error_msg: str) -> bool:
    """Check if error message indicates a retryable error."""
    return any(
        code in error_msg for code in ["429", "500", "502", "503", "Rate Limit", "Server Error"]
    )


def _calculate_retry_delay(config: RetryConfig, attempt: int) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(
        config.initial_delay * (config.backoff_multiplier**attempt),
        config.max_delay,
    )
    # Using random.uniform is acceptable for jitter, not cryptographic
    jitter = random.uniform(0, config.jitter_seconds)  # nosec B311
    return delay + jitter
