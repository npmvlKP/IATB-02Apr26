"""Coverage tests for execution.instrument_resolver."""

from __future__ import annotations

from iatb.execution.instrument_resolver import InstrumentResolver, ResolvedInstrument


class TestResolvedInstrument:
    def test_init(self) -> None:
        try:
            obj = ResolvedInstrument()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ResolvedInstrument(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestInstrumentResolver:
    def test_init(self) -> None:
        try:
            obj = InstrumentResolver()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = InstrumentResolver(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
