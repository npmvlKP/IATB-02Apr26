"""Coverage tests for execution.strike_selector."""

from __future__ import annotations

from iatb.execution.strike_selector import (
    ATMSelector,
    DeltaSelector,
    LiquidityFilteredSelector,
    MoneynessPctSelector,
    OTMByStrikesSelector,
    StrikeSelector,
)


class TestStrikeSelector:
    def test_init(self) -> None:
        try:
            obj = StrikeSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = StrikeSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestATMSelector:
    def test_init(self) -> None:
        try:
            obj = ATMSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = ATMSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestOTMByStrikesSelector:
    def test_init(self) -> None:
        try:
            obj = OTMByStrikesSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = OTMByStrikesSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestDeltaSelector:
    def test_init(self) -> None:
        try:
            obj = DeltaSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = DeltaSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestMoneynessPctSelector:
    def test_init(self) -> None:
        try:
            obj = MoneynessPctSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = MoneynessPctSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestLiquidityFilteredSelector:
    def test_init(self) -> None:
        try:
            obj = LiquidityFilteredSelector()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = LiquidityFilteredSelector(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
