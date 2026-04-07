"""Tests for instrument model, InstrumentType enum, and validation."""

from datetime import date
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError
from iatb.data.instrument import (
    Instrument,
    InstrumentType,
    map_kite_instrument_type,
)


def _equity(symbol: str = "RELIANCE") -> Instrument:
    return Instrument(
        instrument_token=408065,
        exchange_token=1594,
        trading_symbol=symbol,
        name="RELIANCE",
        exchange=Exchange.NSE,
        segment="NSE",
        instrument_type=InstrumentType.EQUITY,
        lot_size=Decimal("1"),
        tick_size=Decimal("0.05"),
    )


def _option_ce() -> Instrument:
    return Instrument(
        instrument_token=5720578,
        exchange_token=22346,
        trading_symbol="NIFTY2500CE",
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO-OPT",
        instrument_type=InstrumentType.OPTION_CE,
        lot_size=Decimal("75"),
        tick_size=Decimal("0.05"),
        strike=Decimal("25000"),
        expiry=date(2026, 4, 30),
    )


class TestInstrumentCreation:
    def test_valid_equity(self) -> None:
        inst = _equity()
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.lot_size == Decimal("1")
        assert not inst.is_option
        assert not inst.is_derivative

    def test_valid_option_ce(self) -> None:
        inst = _option_ce()
        assert inst.is_option
        assert inst.is_derivative
        assert inst.strike == Decimal("25000")

    def test_option_without_strike_fails(self) -> None:
        with pytest.raises(ValidationError, match="strike is required"):
            Instrument(
                instrument_token=1,
                exchange_token=1,
                trading_symbol="NIFTY2500CE",
                name="NIFTY",
                exchange=Exchange.NSE,
                segment="NFO-OPT",
                instrument_type=InstrumentType.OPTION_CE,
                lot_size=Decimal("75"),
                tick_size=Decimal("0.05"),
                expiry=date(2026, 4, 30),
            )

    def test_derivative_without_expiry_fails(self) -> None:
        with pytest.raises(ValidationError, match="expiry is required"):
            Instrument(
                instrument_token=1,
                exchange_token=1,
                trading_symbol="NIFTYFUT",
                name="NIFTY",
                exchange=Exchange.NSE,
                segment="NFO-FUT",
                instrument_type=InstrumentType.FUTURE,
                lot_size=Decimal("75"),
                tick_size=Decimal("0.05"),
            )

    def test_zero_lot_size_fails(self) -> None:
        with pytest.raises(ValidationError, match="lot_size must be positive"):
            Instrument(
                instrument_token=1,
                exchange_token=1,
                trading_symbol="RELIANCE",
                name="RELIANCE",
                exchange=Exchange.NSE,
                segment="NSE",
                instrument_type=InstrumentType.EQUITY,
                lot_size=Decimal("0"),
                tick_size=Decimal("0.05"),
            )

    def test_empty_trading_symbol_fails(self) -> None:
        with pytest.raises(ValidationError, match="trading_symbol cannot be empty"):
            Instrument(
                instrument_token=1,
                exchange_token=1,
                trading_symbol="  ",
                name="X",
                exchange=Exchange.NSE,
                segment="NSE",
                instrument_type=InstrumentType.EQUITY,
                lot_size=Decimal("1"),
                tick_size=Decimal("0.05"),
            )

    def test_negative_strike_fails(self) -> None:
        with pytest.raises(ValidationError, match="strike cannot be negative"):
            Instrument(
                instrument_token=1,
                exchange_token=1,
                trading_symbol="NIFTY2500CE",
                name="NIFTY",
                exchange=Exchange.NSE,
                segment="NFO-OPT",
                instrument_type=InstrumentType.OPTION_CE,
                lot_size=Decimal("75"),
                tick_size=Decimal("0.05"),
                strike=Decimal("-100"),
                expiry=date(2026, 4, 30),
            )


class TestMapKiteInstrumentType:
    def test_valid_types(self) -> None:
        assert map_kite_instrument_type("EQ") == InstrumentType.EQUITY
        assert map_kite_instrument_type("FUT") == InstrumentType.FUTURE
        assert map_kite_instrument_type("CE") == InstrumentType.OPTION_CE
        assert map_kite_instrument_type("PE") == InstrumentType.OPTION_PE

    def test_case_insensitive(self) -> None:
        assert map_kite_instrument_type("eq") == InstrumentType.EQUITY
        assert map_kite_instrument_type(" Ce ") == InstrumentType.OPTION_CE

    def test_unknown_type_fails(self) -> None:
        with pytest.raises(ValidationError, match="Unknown Kite instrument_type"):
            map_kite_instrument_type("UNKNOWN")
