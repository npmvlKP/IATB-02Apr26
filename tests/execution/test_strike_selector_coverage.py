"""Coverage tests for execution.strike_selector - enhanced with Decimal, error paths, boundary values."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.data.instrument import Instrument, InstrumentType
from iatb.execution.strike_selector import (
    ATMSelector,
    DeltaSelector,
    LiquidityFilteredSelector,
    MoneynessPctSelector,
    OTMByStrikesSelector,
    StrikeSelector,
)


def _make_option(
    strike: Decimal,
    option_type: InstrumentType = InstrumentType.OPTION_CE,
    lot_size: Decimal = Decimal("50"),
) -> Instrument:
    """Helper to create a valid option Instrument."""
    return Instrument(
        instrument_token=0,
        exchange_token=0,
        trading_symbol=f"NIFTY{strike}{option_type.value}",
        name=f"NIFTY {strike} {option_type.value}",
        exchange=Exchange.NSE,
        segment="NFO",
        instrument_type=option_type,
        lot_size=lot_size,
        tick_size=Decimal("0.05"),
        strike=strike,
        expiry=date(2026, 6, 26),
    )


class TestATMSelector:
    def test_init(self) -> None:
        obj = ATMSelector()
        assert obj is not None

    def test_is_strike_selector_protocol(self) -> None:
        obj = ATMSelector()
        assert isinstance(obj, StrikeSelector)

    def test_select_atm_call(self) -> None:
        chain = [
            _make_option(Decimal("19000")),
            _make_option(Decimal("19500")),
            _make_option(Decimal("20000")),
        ]
        selector = ATMSelector()
        result = selector.select(chain, Decimal("19600"), OrderSide.BUY)
        assert result.strike == Decimal("19500")

    def test_select_empty_chain_raises(self) -> None:
        selector = ATMSelector()
        with pytest.raises(ConfigError, match="empty"):
            selector.select([], Decimal("19500"), OrderSide.BUY)

    def test_select_zero_price_raises(self) -> None:
        chain = [_make_option(Decimal("19500"))]
        selector = ATMSelector()
        with pytest.raises(ConfigError, match="positive"):
            selector.select(chain, Decimal("0"), OrderSide.BUY)


class TestOTMByStrikesSelector:
    def test_init_default(self) -> None:
        obj = OTMByStrikesSelector()
        assert obj is not None

    def test_init_negative_raises(self) -> None:
        with pytest.raises(ConfigError, match="negative"):
            OTMByStrikesSelector(n_strikes=-1)

    def test_init_zero_n(self) -> None:
        obj = OTMByStrikesSelector(n_strikes=0)
        chain = [
            _make_option(Decimal("19000")),
            _make_option(Decimal("19500")),
            _make_option(Decimal("20000")),
        ]
        result = obj.select(chain, Decimal("19500"), OrderSide.BUY)
        assert result is not None


class TestDeltaSelector:
    def test_init(self) -> None:
        obj = DeltaSelector()
        assert obj is not None

    def test_select_raises(self) -> None:
        chain = [_make_option(Decimal("19500"))]
        selector = DeltaSelector()
        with pytest.raises(ConfigError, match="Greeks"):
            selector.select(chain, Decimal("19500"), OrderSide.BUY)


class TestMoneynessPctSelector:
    def test_init(self) -> None:
        obj = MoneynessPctSelector()
        assert obj is not None

    def test_init_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            MoneynessPctSelector(pct=Decimal("0"))

    def test_init_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            MoneynessPctSelector(pct=Decimal("1"))


class TestLiquidityFilteredSelector:
    def test_init(self) -> None:
        inner = ATMSelector()
        obj = LiquidityFilteredSelector(inner=inner)
        assert obj is not None

    def test_init_negative_raises(self) -> None:
        inner = ATMSelector()
        with pytest.raises(ConfigError, match="negative"):
            LiquidityFilteredSelector(inner=inner, min_lot_volume=-1)

    def test_empty_chain_raises(self) -> None:
        inner = ATMSelector()
        selector = LiquidityFilteredSelector(inner=inner)
        with pytest.raises(ConfigError, match="empty"):
            selector.select([], Decimal("19500"), OrderSide.BUY)


class TestStrikeSelectorBase:
    def test_protocol_atm(self) -> None:
        obj = ATMSelector()
        assert isinstance(obj, StrikeSelector)

    def test_protocol_otm(self) -> None:
        obj = OTMByStrikesSelector()
        assert isinstance(obj, StrikeSelector)
