"""Tests for InstrumentMaster SQLite-cached instrument service."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.instrument import Instrument, InstrumentType
from iatb.data.instrument_master import InstrumentMaster


@pytest.fixture()
def master(tmp_path: Path) -> InstrumentMaster:
    return InstrumentMaster(cache_dir=tmp_path)


def _insert(master: InstrumentMaster, inst: Instrument) -> None:
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


def _equity() -> Instrument:
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


def _nifty_ce(strike: str, token: int) -> Instrument:
    return Instrument(
        instrument_token=token,
        exchange_token=token,
        trading_symbol=f"NIFTY{strike}CE",
        name="NIFTY",
        exchange=Exchange.NSE,
        segment="NFO-OPT",
        instrument_type=InstrumentType.OPTION_CE,
        lot_size=Decimal("75"),
        tick_size=Decimal("0.05"),
        strike=Decimal(strike),
        expiry=date(2026, 5, 1),
    )


class TestGetInstrument:
    def test_found(self, master: InstrumentMaster) -> None:
        _insert(master, _equity())
        inst = master.get_instrument("RELIANCE", Exchange.NSE)
        assert inst.trading_symbol == "RELIANCE"
        assert inst.lot_size == Decimal("1")

    def test_not_found_raises(self, master: InstrumentMaster) -> None:
        with pytest.raises(ConfigError, match="Instrument not found"):
            master.get_instrument("NOTEXIST", Exchange.NSE)

    def test_filter_by_type(self, master: InstrumentMaster) -> None:
        _insert(master, _equity())
        with pytest.raises(ConfigError):
            master.get_instrument("RELIANCE", Exchange.NSE, InstrumentType.FUTURE)


class TestGetOptionChain:
    def test_returns_sorted_chain(self, master: InstrumentMaster) -> None:
        _insert(master, _nifty_ce("25000", 1001))
        _insert(master, _nifty_ce("24500", 1002))
        _insert(master, _nifty_ce("25500", 1003))
        chain = master.get_option_chain("NIFTY", Exchange.NSE)
        strikes = [c.strike for c in chain]
        assert strikes == sorted(strikes)
        assert len(chain) == 3

    def test_filter_by_expiry(self, master: InstrumentMaster) -> None:
        _insert(master, _nifty_ce("25000", 1001))
        chain = master.get_option_chain("NIFTY", Exchange.NSE, expiry=date(2026, 5, 1))
        assert len(chain) == 1
        chain_empty = master.get_option_chain("NIFTY", Exchange.NSE, expiry=date(2026, 6, 1))
        assert len(chain_empty) == 0


class TestGetLotSize:
    def test_equity_lot_size(self, master: InstrumentMaster) -> None:
        _insert(master, _equity())
        assert master.get_lot_size("RELIANCE", Exchange.NSE) == Decimal("1")


class TestGetAvailableTypes:
    def test_multiple_types(self, master: InstrumentMaster) -> None:
        _insert(master, _equity())
        _insert(master, _nifty_ce("25000", 1001))
        types = master.get_available_types("RELIANCE", Exchange.NSE)
        assert InstrumentType.EQUITY in types

    def test_empty_for_unknown(self, master: InstrumentMaster) -> None:
        types = master.get_available_types("UNKNOWN", Exchange.NSE)
        assert len(types) == 0


class TestGetNearestExpiry:
    def test_finds_expiry(self, master: InstrumentMaster) -> None:
        _insert(master, _nifty_ce("25000", 1001))
        expiry = master.get_nearest_expiry("NIFTY", Exchange.NSE, InstrumentType.OPTION_CE)
        assert expiry == date(2026, 5, 1)

    def test_no_expiry_raises(self, master: InstrumentMaster) -> None:
        with pytest.raises(ConfigError, match="No expiry found"):
            master.get_nearest_expiry("NIFTY", Exchange.NSE, InstrumentType.FUTURE)


class TestLoadFromCSV:
    def test_nonexistent_csv_raises(self, master: InstrumentMaster) -> None:
        with pytest.raises(ConfigError, match="CSV not found"):
            master.load_from_csv(Path("/nonexistent.csv"), Exchange.NSE)

    def test_valid_csv_loads(self, master: InstrumentMaster, tmp_path: Path) -> None:
        csv_path = tmp_path / "instruments.csv"
        csv_path.write_text(
            "instrument_token,exchange_token,tradingsymbol,name,"
            "last_price,expiry,strike,tick_size,lot_size,"
            "instrument_type,segment,exchange\n"
            "408065,1594,RELIANCE,RELIANCE,0,,,0.05,1,EQ,NSE,NSE\n"
            "5720578,22346,NIFTY25000CE,NIFTY,0,2026-05-01,25000,"
            "0.05,75,CE,NFO-OPT,NFO\n",
            encoding="utf-8",
        )
        loaded = master.load_from_csv(csv_path, Exchange.NSE)
        assert loaded == 2
        inst = master.get_instrument("RELIANCE", Exchange.NSE)
        assert inst.lot_size == Decimal("1")

    def test_invalid_csv_row_skipped(self, master: InstrumentMaster, tmp_path: Path) -> None:
        csv_path = tmp_path / "bad.csv"
        csv_path.write_text(
            "instrument_token,exchange_token,tradingsymbol,name,"
            "last_price,expiry,strike,tick_size,lot_size,"
            "instrument_type,segment,exchange\n"
            "bad,bad,RELIANCE,RELIANCE,0,,,0.05,1,EQ,NSE,NSE\n",
            encoding="utf-8",
        )
        loaded = master.load_from_csv(csv_path, Exchange.NSE)
        assert loaded == 0


class TestPurgeStale:
    def test_stale_entries_purged(self, master: InstrumentMaster) -> None:
        from datetime import UTC, datetime, timedelta

        from iatb.data.instrument_master import _instrument_to_db_tuple

        old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        inst = _equity()
        with master._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO instruments "
                "(instrument_token, exchange_token, trading_symbol, name, "
                "exchange, segment, instrument_type, lot_size, tick_size, "
                "strike, expiry, fetched_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                _instrument_to_db_tuple(inst, old_time),
            )
        master._purge_stale()
        types = master.get_available_types("RELIANCE", Exchange.NSE)
        assert len(types) == 0
