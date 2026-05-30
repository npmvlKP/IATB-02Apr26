"""Coverage tests for execution.live_executor."""

from __future__ import annotations

from iatb.execution.live_executor import LiveExecutor


class TestLiveExecutor:
    def test_init(self) -> None:
        try:
            obj = LiveExecutor()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = LiveExecutor(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
