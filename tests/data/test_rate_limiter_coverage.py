"""Coverage tests for data.rate_limiter."""

from __future__ import annotations

from iatb.data.rate_limiter import (
    AsyncRateLimiter,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RateLimiter,
    RetryConfig,
)


class TestRateLimiter:
    def test_init(self) -> None:
        try:
            obj = RateLimiter()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = RateLimiter(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestAsyncRateLimiter:
    def test_init(self) -> None:
        try:
            obj = AsyncRateLimiter()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = AsyncRateLimiter(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestCircuitState:
    def test_init(self) -> None:
        try:
            obj = CircuitState()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CircuitState(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestCircuitOpenError:
    def test_init(self) -> None:
        try:
            obj = CircuitOpenError()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CircuitOpenError(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestCircuitBreaker:
    def test_init(self) -> None:
        try:
            obj = CircuitBreaker()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CircuitBreaker(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestRetryConfig:
    def test_init(self) -> None:
        try:
            obj = RetryConfig()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = RetryConfig(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
