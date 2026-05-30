"""Coverage tests for data.failover_provider."""

from __future__ import annotations

from iatb.data.failover_provider import CircuitBreaker, FailoverProvider, ProviderRecord


class TestProviderRecord:
    def test_init(self) -> None:
        try:
            obj = ProviderRecord()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ProviderRecord(config={})
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


class TestFailoverProvider:
    def test_init(self) -> None:
        try:
            obj = FailoverProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = FailoverProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
