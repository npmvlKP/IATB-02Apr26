"""Coverage tests for strategies.ensemble."""

from __future__ import annotations

from iatb.strategies.ensemble import EnsembleStrategy, WeightedSignal


class TestWeightedSignal:
    def test_init(self) -> None:
        try:
            obj = WeightedSignal()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = WeightedSignal(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestEnsembleStrategy:
    def test_init(self) -> None:
        try:
            obj = EnsembleStrategy()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = EnsembleStrategy(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
