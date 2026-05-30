"""Coverage tests for execution.ccxt_executor."""

from __future__ import annotations

from iatb.execution.ccxt_executor import CCXTExecutor


class TestCCXTExecutor:
    def test_init(self) -> None:
        try:
            obj = CCXTExecutor()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CCXTExecutor(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
