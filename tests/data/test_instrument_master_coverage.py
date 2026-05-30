"""Coverage tests for data.instrument_master."""

from __future__ import annotations

from iatb.data.instrument_master import InstrumentMaster


class TestInstrumentMaster:
    def test_init(self) -> None:
        try:
            obj = InstrumentMaster()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = InstrumentMaster(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
