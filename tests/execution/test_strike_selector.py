"""Tests for strike price selection strategies."""

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
)


def _ce(strike: str, lot: str = "75") -> Instrument:
    return Instrument(
        instrument_token=int(Decimal(strike)),
        exchange_token=1,
        trading_symbol=f"NIFTY{strike}CE",
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO-OPT",
        instrument_type=InstrumentType.OPTION_CE,
        lot_size=Decimal(lot),
        tick_size=Decimal("0.05"),
        strike=Decimal(strike),
        expiry=date(2026, 4, 30),
    )


def _pe(strike: str, lot: str = "75") -> Instrument:
    return Instrument(
        instrument_token=int(Decimal(strike)) + 100000,
        exchange_token=2,
        trading_symbol=f"NIFTY{strike}PE",
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO-OPT",
        instrument_type=InstrumentType.OPTION_PE,
        lot_size=Decimal(lot),
        tick_size=Decimal("0.05"),
        strike=Decimal(strike),
        expiry=date(2026, 4, 30),
    )


def _ce_chain() -> list[Instrument]:
    return [_ce("24500"), _ce("24600"), _ce("24700"), _ce("24800"), _ce("24900")]


def _pe_chain() -> list[Instrument]:
    return [_pe("24500"), _pe("24600"), _pe("24700"), _pe("24800"), _pe("24900")]


class TestATMSelector:
    def test_picks_nearest_strike(self) -> None:
        chain = _ce_chain()
        result = ATMSelector().select(chain, Decimal("24650"), OrderSide.BUY)
        assert result.strike == Decimal("24600") or result.strike == Decimal("24700")

    def test_exact_atm(self) -> None:
        chain = _ce_chain()
        result = ATMSelector().select(chain, Decimal("24700"), OrderSide.BUY)
        assert result.strike == Decimal("24700")

    def test_empty_chain_fails(self) -> None:
        with pytest.raises(ConfigError, match="Option chain is empty"):
            ATMSelector().select([], Decimal("24700"), OrderSide.BUY)


class TestOTMByStrikesSelector:
    def test_call_2_strikes_otm(self) -> None:
        chain = _ce_chain()
        result = OTMByStrikesSelector(n_strikes=2).select(chain, Decimal("24700"), OrderSide.BUY)
        assert result.strike == Decimal("24900")

    def test_zero_strikes_equals_atm(self) -> None:
        chain = _ce_chain()
        result = OTMByStrikesSelector(n_strikes=0).select(chain, Decimal("24700"), OrderSide.BUY)
        assert result.strike == Decimal("24700")

    def test_put_2_strikes_otm(self) -> None:
        chain = _pe_chain()
        result = OTMByStrikesSelector(n_strikes=2).select(chain, Decimal("24700"), OrderSide.SELL)
        assert result.strike == Decimal("24500")

    def test_negative_n_strikes_fails(self) -> None:
        with pytest.raises(ConfigError, match="n_strikes cannot be negative"):
            OTMByStrikesSelector(n_strikes=-1)


class TestMoneynessPctSelector:
    def test_call_5pct_otm(self) -> None:
        chain = _ce_chain()
        # 24700 * 1.05 = 25935 — nearest available is 24900
        result = MoneynessPctSelector(pct=Decimal("0.01")).select(
            chain, Decimal("24700"), OrderSide.BUY
        )
        # 24700 * 1.01 = 24947 -> nearest is 24900
        assert result.strike == Decimal("24900")

    def test_invalid_pct(self) -> None:
        with pytest.raises(ConfigError, match="pct must be between 0 and 1"):
            MoneynessPctSelector(pct=Decimal("0"))


class TestDeltaSelector:
    def test_raises_not_implemented(self) -> None:
        with pytest.raises(ConfigError, match="Greeks provider"):
            DeltaSelector().select(_ce_chain(), Decimal("24700"), OrderSide.BUY)


class TestLiquidityFilteredSelector:
    def test_falls_back_to_unfiltered(self) -> None:
        chain = _ce_chain()
        # All have lot_size=75, filter at min_lot_volume=100 filters all out
        result = LiquidityFilteredSelector(ATMSelector(), min_lot_volume=100).select(
            chain, Decimal("24700"), OrderSide.BUY
        )
        assert result.strike == Decimal("24700")

    def test_filters_by_volume(self) -> None:
        chain = [_ce("24700", lot="200"), _ce("24800", lot="50")]
        result = LiquidityFilteredSelector(ATMSelector(), min_lot_volume=100).select(
            chain, Decimal("24750"), OrderSide.BUY
        )
        assert result.strike == Decimal("24700")  # Only one passes filter
