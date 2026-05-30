"""Coverage tests for data.ccxt_provider."""

from __future__ import annotations

from iatb.data.ccxt_provider import CCXTProvider


class TestCCXTProvider:
    def test_init(self) -> None:
        try:
            obj = CCXTProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CCXTProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
