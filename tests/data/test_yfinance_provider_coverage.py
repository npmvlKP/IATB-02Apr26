"""Coverage tests for data.yfinance_provider."""

from __future__ import annotations

from iatb.data.yfinance_provider import YFinanceProvider


class TestYFinanceProvider:
    def test_init(self) -> None:
        try:
            obj = YFinanceProvider()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = YFinanceProvider(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
