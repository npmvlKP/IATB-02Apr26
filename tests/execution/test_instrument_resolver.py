"""Tests for instrument type resolution with cascade fallback."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import InstrumentResolutionError
from iatb.data.instrument import Instrument, InstrumentType
from iatb.data.instrument_master import InstrumentMaster
from iatb.execution.instrument_resolver import InstrumentResolver


@pytest.fixture()
def master(tmp_path: Path) -> InstrumentMaster:
    return InstrumentMaster(cache_dir=tmp_path)


def _insert_instrument(master: InstrumentMaster, inst: Instrument) -> None:
    """Insert an instrument directly into the master's SQLite cache."""
    from datetime import UTC, datetime

    from iatb.data.instrument_master import _instrument_to_db_tuple

    now_utc = datetime.now(UTC).isoformat()
    with master._connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO instruments "
            "(instrument_token, exchange_token, trading_symbol, name, "
            "exchange, segment, instrument_type, lot_size, tick_size, "
            "strike, expiry, fetched_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _instrument_to_db_tuple(inst, now_utc),
        )


def _reliance_eq() -> Instrument:
    return Instrument(
        instrument_token=408065,
        exchange_token=1594,
        trading_symbol="RELIANCE",
        name="RELIANCE",
        exchange=Exchange.NSE,
        segment="NSE",
        instrument_type=InstrumentType.EQUITY,
        lot_size=Decimal("1"),
        tick_size=Decimal("0.05"),
    )


def _reliance_fut() -> Instrument:
    return Instrument(
        instrument_token=408066,
        exchange_token=1595,
        trading_symbol="RELIANCEFUT",
        name="RELIANCE",
        exchange=Exchange.NSE,
        segment="NFO-FUT",
        instrument_type=InstrumentType.FUTURE,
        lot_size=Decimal("250"),
        tick_size=Decimal("0.05"),
        expiry=date(2026, 5, 29),
    )


def _nifty_ce() -> Instrument:
    return Instrument(
        instrument_token=500001,
        exchange_token=2001,
        trading_symbol="NIFTY25000CE",
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO-OPT",
        instrument_type=InstrumentType.OPTION_CE,
        lot_size=Decimal("75"),
        tick_size=Decimal("0.05"),
        strike=Decimal("25000"),
        expiry=date(2030, 6, 1),
    )


class TestCascadeResolution:
    def test_equity_fallback(self, master: InstrumentMaster) -> None:
        _insert_instrument(master, _reliance_eq())
        resolver = InstrumentResolver(master)
        result = resolver.resolve(
            "RELIANCE",
            Exchange.NSE,
            [InstrumentType.FUTURE, InstrumentType.EQUITY],
        )
        assert result.instrument.instrument_type == InstrumentType.EQUITY
        assert "EQUITY" in result.resolution_path

    def test_future_preferred(self, master: InstrumentMaster) -> None:
        _insert_instrument(master, _reliance_eq())
        _insert_instrument(master, _reliance_fut())
        resolver = InstrumentResolver(master)
        result = resolver.resolve(
            "RELIANCE",
            Exchange.NSE,
            [InstrumentType.FUTURE, InstrumentType.EQUITY],
        )
        assert result.instrument.instrument_type == InstrumentType.FUTURE

    def test_no_instruments_raises(self, master: InstrumentMaster) -> None:
        resolver = InstrumentResolver(master)
        with pytest.raises(InstrumentResolutionError, match="No instruments found"):
            resolver.resolve("NOTEXIST", Exchange.NSE, [InstrumentType.EQUITY])


class TestOptionResolution:
    def test_option_ce_resolves_with_price(self, master: InstrumentMaster) -> None:
        _insert_instrument(master, _nifty_ce())
        ce2 = Instrument(
            instrument_token=500002,
            exchange_token=2002,
            trading_symbol="NIFTY24500CE",
            name="NIFTY",
            exchange=Exchange.NSE,
            segment="NFO-OPT",
            instrument_type=InstrumentType.OPTION_CE,
            lot_size=Decimal("75"),
            tick_size=Decimal("0.05"),
            strike=Decimal("24500"),
            expiry=date(2030, 6, 1),
        )
        _insert_instrument(master, ce2)
        resolver = InstrumentResolver(master)
        result = resolver.resolve(
            "NIFTY",
            Exchange.NSE,
            [InstrumentType.OPTION_CE],
            underlying_price=Decimal("24600"),
        )
        assert result.instrument.instrument_type == InstrumentType.OPTION_CE
        assert result.instrument.strike == Decimal("24500")

    def test_non_index_keeps_equity(self, master: InstrumentMaster) -> None:
        _insert_instrument(master, _reliance_eq())
        resolver = InstrumentResolver(master)
        result = resolver.resolve(
            "RELIANCE",
            Exchange.NSE,
            [InstrumentType.EQUITY],
        )
        assert result.instrument.instrument_type == InstrumentType.EQUITY


class TestIndexAwareness:
    def test_nifty_skips_equity(self, master: InstrumentMaster) -> None:
        _insert_instrument(master, _nifty_ce())
        resolver = InstrumentResolver(master)
        result = resolver.resolve(
            "NIFTY",
            Exchange.NSE,
            [InstrumentType.OPTION_CE, InstrumentType.EQUITY],
            underlying_price=Decimal("25000"),
        )
        assert result.instrument.instrument_type == InstrumentType.OPTION_CE

    def test_index_with_only_equity_raises(self, master: InstrumentMaster) -> None:
        resolver = InstrumentResolver(master)
        with pytest.raises(InstrumentResolutionError):
            resolver.resolve(
                "NIFTY",
                Exchange.NSE,
                [InstrumentType.EQUITY],
            )
