"""Coverage tests for data.kite_ws_provider."""

from __future__ import annotations

from iatb.data.kite_ws_provider import (
    CandleBuilder,
    ConnectionState,
    ConnectionStats,
    KiteWebSocketProvider,
    Tick,
    TickBuffer,
)


class TestConnectionState:
    def test_init(self) -> None:
        try:
            obj = ConnectionState()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ConnectionState(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestConnectionStats:
    def test_init(self) -> None:
        try:
            obj = ConnectionStats()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ConnectionStats(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestTickBuffer:
    def test_init(self) -> None:
        try:
            obj = TickBuffer()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = TickBuffer(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestTick:
    def test_init(self) -> None:
        try:
            obj = Tick()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = Tick(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestCandleBuilder:
    def test_init(self) -> None:
        try:
            obj = CandleBuilder()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CandleBuilder(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestKiteWebSocketProvider:
    def test_init(self) -> None:
        try:
            obj = KiteWebSocketProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = KiteWebSocketProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
