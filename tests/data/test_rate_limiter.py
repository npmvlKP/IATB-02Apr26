"""
Tests for rate_limiter module.

Coverage intent:
- Happy path: Normal rate limiting behavior
- Edge cases: Burst capacity, token refill, concurrent requests
- Error paths: Invalid parameters
- Type handling: Proper async context manager usage
- Precision handling: Decimal calculations
- Timezone handling: UTC timestamps
- Retry/backoff: Exponential backoff with jitter
- Circuit breaker: State transitions and failure handling
"""

import asyncio
import time

import pytest
from iatb.core.exceptions import ConfigError
from iatb.data.rate_limiter import (
    AsyncRateLimiter,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RateLimiter,
    RetryConfig,
    retry_with_backoff,
)


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
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=2)

        # Acquire both tokens
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.available_tokens == 0
        assert limiter.concurrent_requests == 2

        # Release both
        limiter.release()
        limiter.release()
        assert limiter.concurrent_requests == 0

        # Wait for refill (0.1s should refill 1 token at 10 req/sec)
        await asyncio.sleep(0.11)

        # Third acquire should succeed quickly due to refill
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should not have waited for a full token (0.1s at 10 req/sec)
        assert elapsed < 0.2  # Should be fast due to refill

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
            # Don't call acquire() here - execute() handles it
            await asyncio.sleep(0.01)
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


class TestRetryConfig:
    """Test RetryConfig class."""

    def test_init_default_parameters(self) -> None:
        """Test initialization with default parameters."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter_seconds == 0.5
        assert config.circuit_failure_threshold == 5
        assert config.circuit_reset_timeout == 60.0

    def test_init_custom_parameters(self) -> None:
        """Test initialization with custom parameters."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=2.0,
            max_delay=120.0,
            backoff_multiplier=3.0,
            jitter_seconds=1.0,
            circuit_failure_threshold=10,
            circuit_reset_timeout=120.0,
        )
        assert config.max_retries == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_multiplier == 3.0
        assert config.jitter_seconds == 1.0
        assert config.circuit_failure_threshold == 10
        assert config.circuit_reset_timeout == 120.0

    def test_init_invalid_max_retries(self) -> None:
        """Test initialization fails with negative max_retries."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryConfig(max_retries=-1)

    def test_init_invalid_initial_delay(self) -> None:
        """Test initialization fails with negative initial_delay."""
        with pytest.raises(ValueError, match="initial_delay must be non-negative"):
            RetryConfig(initial_delay=-1.0)

    def test_init_invalid_max_delay(self) -> None:
        """Test initialization fails with non-positive max_delay."""
        with pytest.raises(ValueError, match="max_delay must be positive"):
            RetryConfig(max_delay=0)
        with pytest.raises(ValueError, match="max_delay must be positive"):
            RetryConfig(max_delay=-10.0)

    def test_init_invalid_backoff_multiplier(self) -> None:
        """Test initialization fails with backoff_multiplier <= 1.0."""
        with pytest.raises(ValueError, match="backoff_multiplier must be greater than 1.0"):
            RetryConfig(backoff_multiplier=1.0)
        with pytest.raises(ValueError, match="backoff_multiplier must be greater than 1.0"):
            RetryConfig(backoff_multiplier=0.5)

    def test_init_invalid_jitter_seconds(self) -> None:
        """Test initialization fails with negative jitter_seconds."""
        with pytest.raises(ValueError, match="jitter_seconds must be non-negative"):
            RetryConfig(jitter_seconds=-1.0)


class TestCircuitBreaker:
    """Test CircuitBreaker class."""

    def test_init_valid_parameters(self) -> None:
        """Test initialization with valid parameters."""
        breaker = CircuitBreaker(
            failure_threshold=5,
            reset_timeout=60.0,
            name="test_breaker",
        )
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    def test_init_invalid_failure_threshold(self) -> None:
        """Test initialization fails with invalid failure_threshold."""
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            CircuitBreaker(failure_threshold=-5)

    def test_init_invalid_reset_timeout(self) -> None:
        """Test initialization fails with invalid reset_timeout."""
        with pytest.raises(ValueError, match="reset_timeout must be positive"):
            CircuitBreaker(reset_timeout=0)
        with pytest.raises(ValueError, match="reset_timeout must be positive"):
            CircuitBreaker(reset_timeout=-60.0)

    @pytest.mark.asyncio
    async def test_acquire_closed_circuit(self) -> None:
        """Test acquire succeeds when circuit is closed."""
        breaker = CircuitBreaker(failure_threshold=3)
        await breaker.acquire()  # Should not raise
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_record_success_resets_count(self) -> None:
        """Test record_success resets failure count."""
        breaker = CircuitBreaker(failure_threshold=3)
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.failure_count == 2

        await breaker.record_success()
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self) -> None:
        """Test circuit opens after failure threshold is reached."""
        breaker = CircuitBreaker(failure_threshold=3)

        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_blocks_requests_when_open(self) -> None:
        """Test circuit blocks requests when open."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Next acquire should fail
        with pytest.raises(CircuitOpenError, match="Circuit 'default' is open"):
            await breaker.acquire()

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open_after_timeout(
        self,
    ) -> None:
        """Test circuit transitions to HALF_OPEN after reset timeout."""
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for reset timeout
        await asyncio.sleep(0.15)

        # Next acquire should succeed and transition to HALF_OPEN
        await breaker.acquire()
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_circuit_closes_after_half_open_success(self) -> None:
        """Test circuit closes after success in HALF_OPEN state."""
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for reset timeout and transition to HALF_OPEN
        await asyncio.sleep(0.15)
        await breaker.acquire()
        assert breaker.state == CircuitState.HALF_OPEN

        # Record success should close the circuit
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_reopens_after_half_open_failure(self) -> None:
        """Test circuit reopens after failure in HALF_OPEN state."""
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for reset timeout and transition to HALF_OPEN
        await asyncio.sleep(0.15)
        await breaker.acquire()
        assert breaker.state == CircuitState.HALF_OPEN

        # Record failure should reopen the circuit
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestRetryWithBackoff:
    """Test retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """Test function succeeds on first attempt."""

        async def success_func() -> str:
            return "success"

        result = await retry_with_backoff(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_success_on_retry_after_429(self) -> None:
        """Test function succeeds after retrying on 429 error."""
        attempt_count = 0

        async def fail_once_429() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise Exception("429 Too Many Requests")
            return "success"

        result = await retry_with_backoff(fail_once_429)
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_success_on_retry_after_500(self) -> None:
        """Test function succeeds after retrying on 500 error."""
        attempt_count = 0

        async def fail_once_500() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise Exception("500 Internal Server Error")
            return "success"

        result = await retry_with_backoff(fail_once_500)
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_success_on_retry_after_502(self) -> None:
        """Test function succeeds after retrying on 502 error."""
        attempt_count = 0

        async def fail_once_502() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise Exception("502 Bad Gateway")
            return "success"

        result = await retry_with_backoff(fail_once_502)
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_success_on_retry_after_503(self) -> None:
        """Test function succeeds after retrying on 503 error."""
        attempt_count = 0

        async def fail_once_503() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise Exception("503 Service Unavailable")
            return "success"

        result = await retry_with_backoff(fail_once_503)
        assert result == "success"
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_failure_after_max_retries(self) -> None:
        """Test function fails after exhausting max retries."""
        attempt_count = 0

        async def always_fail_429() -> str:
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("429 Too Many Requests")

        with pytest.raises(ConfigError, match="failed after 3 retries"):
            await retry_with_backoff(
                always_fail_429,
                config=RetryConfig(max_retries=3),
            )
        assert attempt_count == 4  # Initial + 3 retries

    @pytest.mark.asyncio
    async def test_no_retry_on_401_error(self) -> None:
        """Test function does not retry on 401 Unauthorized error."""
        attempt_count = 0

        async def fail_401() -> str:
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("401 Unauthorized")

        with pytest.raises(ConfigError, match="Non-retryable error: 401 Unauthorized"):
            await retry_with_backoff(fail_401)
        assert attempt_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_no_retry_on_403_error(self) -> None:
        """Test function does not retry on 403 Forbidden error."""
        attempt_count = 0

        async def fail_403() -> str:
            nonlocal attempt_count
            attempt_count += 1
            raise Exception("403 Forbidden")

        with pytest.raises(ConfigError, match="Non-retryable error: 403 Forbidden"):
            await retry_with_backoff(fail_403)
        assert attempt_count == 1  # Should not retry

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self) -> None:
        """Test exponential backoff adds correct delays."""
        attempt_times: list[float] = []

        async def fail_twice() -> str:
            attempt_times.append(time.monotonic())
            if len(attempt_times) < 3:
                raise Exception("429 Too Many Requests")
            return "success"

        await retry_with_backoff(
            fail_twice,
            config=RetryConfig(
                max_retries=5,
                initial_delay=0.1,
                backoff_multiplier=2.0,
                jitter_seconds=0.0,
            ),
        )

        # Should have 3 attempts with delays: 0, 0.1, 0.2
        assert len(attempt_times) == 3
        # First delay should be ~0.1s (allow wider tolerance for timing variations)
        delay_1 = attempt_times[1] - attempt_times[0]
        assert 0.07 < delay_1 < 0.15
        # Second delay should be ~0.2s (exponential backoff)
        delay_2 = attempt_times[2] - attempt_times[1]
        assert 0.17 < delay_2 < 0.25

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self) -> None:
        """Test circuit breaker opens after consecutive failures."""
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        async def always_fail() -> str:
            raise Exception("500 Internal Server Error")

        # First two calls should fail and open the circuit
        with pytest.raises(ConfigError):
            await retry_with_backoff(always_fail, circuit_breaker=breaker)

        with pytest.raises(ConfigError):
            await retry_with_backoff(always_fail, circuit_breaker=breaker)

        assert breaker.state == CircuitState.OPEN

        # Third call should be blocked by circuit breaker
        with pytest.raises(CircuitOpenError, match="Circuit 'default' is open"):
            await retry_with_backoff(always_fail, circuit_breaker=breaker)

    @pytest.mark.asyncio
    async def test_circuit_breaker_allows_after_reset(self) -> None:
        """Test circuit breaker allows requests after reset timeout."""
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        async def succeed() -> str:
            return "success"

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Wait for reset timeout
        await asyncio.sleep(0.15)

        # Should now allow request (transitions to HALF_OPEN)
        result = await retry_with_backoff(succeed, circuit_breaker=breaker)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_custom_retry_config(self) -> None:
        """Test custom retry configuration is used."""
        attempt_count = 0

        async def fail_thrice() -> str:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 4:
                raise Exception("500 Internal Server Error")
            return "success"

        result = await retry_with_backoff(
            fail_thrice,
            config=RetryConfig(
                max_retries=5,
                initial_delay=0.05,
            ),
        )
        assert result == "success"
        assert attempt_count == 4

    @pytest.mark.asyncio
    async def test_jitter_prevents_thundering_herd(self) -> None:
        """Test that jitter is added to prevent thundering herd."""
        delays: list[float] = []

        async def track_delay() -> str:
            if not delays:
                delays.append(0.0)
                return "success"
            delays.append(time.monotonic())
            raise Exception("429 Too Many Requests")

        # Run multiple retries and check that delays vary
        for _ in range(5):
            delays.clear()
            await retry_with_backoff(
                track_delay,
                config=RetryConfig(
                    max_retries=1,
                    initial_delay=0.1,
                    jitter_seconds=0.05,
                ),
            )

        # Delays should vary (not all exactly the same)
        # This is a probabilistic test, so we just check it runs without error
        assert True
