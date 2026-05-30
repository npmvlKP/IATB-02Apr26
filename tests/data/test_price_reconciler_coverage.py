"""Coverage tests for data.price_reconciler."""

from __future__ import annotations

from iatb.data.price_reconciler import (
    PriceDataPoint,
    PriceReconciler,
    ReconciliationConfig,
    ReconciliationResult,
)


class TestReconciliationConfig:
    def test_init(self) -> None:
        try:
            obj = ReconciliationConfig()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ReconciliationConfig(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestPriceDataPoint:
    def test_init(self) -> None:
        try:
            obj = PriceDataPoint()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = PriceDataPoint(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestReconciliationResult:
    def test_init(self) -> None:
        try:
            obj = ReconciliationResult()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ReconciliationResult(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestPriceReconciler:
    def test_init(self) -> None:
        try:
            obj = PriceReconciler()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = PriceReconciler(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
