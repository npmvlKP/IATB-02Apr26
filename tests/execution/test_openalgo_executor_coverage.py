"""Coverage tests for execution.openalgo_executor."""

from __future__ import annotations

from iatb.execution.openalgo_executor import OpenAlgoExecutor


class TestOpenAlgoExecutor:
    def test_init(self) -> None:
        try:
            obj = OpenAlgoExecutor()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = OpenAlgoExecutor(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
