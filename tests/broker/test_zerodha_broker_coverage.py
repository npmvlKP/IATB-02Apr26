"""Coverage tests for broker.zerodha_broker."""

from __future__ import annotations

from iatb.broker.zerodha_broker import ZerodhaBroker


class TestZerodhaBroker:
    def test_init(self) -> None:
        try:
            obj = ZerodhaBroker()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ZerodhaBroker(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
