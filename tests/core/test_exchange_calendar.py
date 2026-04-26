"""
Tests for exchange calendar module.
"""

from datetime import date, time
from pathlib import Path

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.exchange_calendar import (
    DEFAULT_EXCHANGE_CALENDAR,
    SESSION_EXCHANGES,
    ExchangeCalendar,
    SessionWindow,
    _default_holidays,
    _default_regular_sessions,
    _default_special_sessions,
    _get_exchange_map,
    _initialize_holidays_dict,
    _load_config_file,
    _load_holidays_from_config,
    _load_session_times_from_config,
    _log_holidays_summary,
    _parse_exchange_session_times,
    _parse_mcx_holidays,
    _parse_nse_cds_holidays,
)


class TestSessionWindow:
    def test_creation(self) -> None:
        session = SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
        assert session.open_time == time(9, 15)
        assert session.close_time == time(15, 30)

    def test_frozen(self) -> None:
        session = SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
        with pytest.raises(AttributeError):
            session.open_time = time(10, 0)

    def test_equality(self) -> None:
        s1 = SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
        s2 = SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
        assert s1 == s2

    def test_inequality(self) -> None:
        s1 = SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
        s2 = SessionWindow(open_time=time(9, 0), close_time=time(15, 30))
        assert s1 != s2


class TestExchangeCalendar:
    def test_get_regular_session_nse(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.NSE)
        assert session is not None
        assert session.open_time == time(9, 15)
        assert session.close_time == time(15, 30)

    def test_get_regular_session_bse(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.BSE)
        assert session is not None
        assert session.open_time == time(9, 15)
        assert session.close_time == time(15, 30)

    def test_get_regular_session_mcx(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.MCX)
        assert session is not None
        assert session.open_time == time(9, 0)
        assert session.close_time == time(23, 30)

    def test_get_regular_session_cds(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.CDS)
        assert session is not None
        assert session.open_time == time(9, 0)
        assert session.close_time == time(17, 30)

    def test_get_regular_session_unknown(self) -> None:
        calendar = ExchangeCalendar(regular_sessions={}, holidays={}, special_sessions={})
        assert calendar.get_regular_session(Exchange.BINANCE) is None

    def test_session_for_weekday(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.session_for(Exchange.NSE, date(2024, 1, 1))
        assert session is not None
        assert session.open_time == time(9, 15)

    def test_session_for_weekend_saturday(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.session_for(Exchange.NSE, date(2024, 1, 6))
        assert session is None

    def test_session_for_weekend_sunday(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.session_for(Exchange.NSE, date(2024, 1, 7))
        assert session is None

    def test_session_for_holiday(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.session_for(Exchange.NSE, date(2026, 1, 26))
        assert session is None

    def test_session_for_special_session(self) -> None:
        session = DEFAULT_EXCHANGE_CALENDAR.session_for(Exchange.NSE, date(2026, 11, 8))
        assert session is not None
        assert session.open_time == time(18, 0)
        assert session.close_time == time(19, 0)

    def test_session_for_unknown_exchange(self) -> None:
        calendar = ExchangeCalendar(regular_sessions={}, holidays={}, special_sessions={})
        assert calendar.session_for(Exchange.BINANCE, date(2024, 1, 1)) is None

    def test_is_holiday(self) -> None:
        assert DEFAULT_EXCHANGE_CALENDAR.is_holiday(Exchange.NSE, date(2026, 1, 26))
        assert not DEFAULT_EXCHANGE_CALENDAR.is_holiday(Exchange.NSE, date(2024, 1, 2))

    def test_is_holiday_unknown_exchange(self) -> None:
        assert not DEFAULT_EXCHANGE_CALENDAR.is_holiday(Exchange.BINANCE, date(2024, 1, 1))

    def test_is_trading_day_weekday(self) -> None:
        assert DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, date(2024, 1, 1))
        assert DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.BSE, date(2024, 1, 1))

    def test_is_trading_day_weekend(self) -> None:
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, date(2024, 1, 6))
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, date(2024, 1, 7))

    def test_is_trading_day_holiday(self) -> None:
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, date(2026, 1, 26))

    def test_is_trading_day_special_session(self) -> None:
        assert DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, date(2026, 11, 8))

    def test_is_trading_day_unknown_exchange(self) -> None:
        calendar = ExchangeCalendar(regular_sessions={}, holidays={}, special_sessions={})
        assert not calendar.is_trading_day(Exchange.BINANCE, date(2024, 1, 1))

    def test_empty_calendar(self) -> None:
        calendar = ExchangeCalendar(
            regular_sessions={},
            holidays={},
            special_sessions={},
        )
        assert calendar.get_regular_session(Exchange.NSE) is None
        assert calendar.session_for(Exchange.NSE, date(2024, 1, 1)) is None
        assert not calendar.is_trading_day(Exchange.NSE, date(2024, 1, 1))
        assert not calendar.is_holiday(Exchange.NSE, date(2024, 1, 1))


class TestDefaultRegularSessions:
    def test_all_exchanges_present(self) -> None:
        sessions = _default_regular_sessions()
        assert Exchange.NSE in sessions
        assert Exchange.BSE in sessions
        assert Exchange.MCX in sessions
        assert Exchange.CDS in sessions

    def test_nse_times(self) -> None:
        sessions = _default_regular_sessions()
        assert sessions[Exchange.NSE].open_time == time(9, 15)
        assert sessions[Exchange.NSE].close_time == time(15, 30)

    def test_mcx_times(self) -> None:
        sessions = _default_regular_sessions()
        assert sessions[Exchange.MCX].open_time == time(9, 0)
        assert sessions[Exchange.MCX].close_time == time(23, 30)

    def test_cds_times(self) -> None:
        sessions = _default_regular_sessions()
        assert sessions[Exchange.CDS].open_time == time(9, 0)
        assert sessions[Exchange.CDS].close_time == time(17, 0)


class TestDefaultHolidays:
    def test_all_exchanges_present(self) -> None:
        holidays = _default_holidays()
        assert Exchange.NSE in holidays
        assert Exchange.BSE in holidays
        assert Exchange.MCX in holidays
        assert Exchange.CDS in holidays

    def test_common_holidays(self) -> None:
        holidays = _default_holidays()
        assert date(2026, 1, 26) in holidays[Exchange.NSE]
        assert date(2026, 8, 15) in holidays[Exchange.NSE]
        assert date(2026, 10, 2) in holidays[Exchange.NSE]
        assert date(2026, 12, 25) in holidays[Exchange.NSE]

    def test_mcx_has_same_holidays(self) -> None:
        holidays = _default_holidays()
        assert holidays[Exchange.NSE] == holidays[Exchange.MCX]


class TestDefaultSpecialSessions:
    def test_muhurat_session_nse(self) -> None:
        sessions = _default_special_sessions()
        assert date(2026, 11, 8) in sessions[Exchange.NSE]
        assert sessions[Exchange.NSE][date(2026, 11, 8)].open_time == time(18, 0)
        assert sessions[Exchange.NSE][date(2026, 11, 8)].close_time == time(19, 0)

    def test_muhurat_session_mcx(self) -> None:
        sessions = _default_special_sessions()
        assert date(2026, 11, 8) in sessions[Exchange.MCX]
        assert sessions[Exchange.MCX][date(2026, 11, 8)].open_time == time(18, 0)
        assert sessions[Exchange.MCX][date(2026, 11, 8)].close_time == time(21, 0)


class TestParseExchangeSessionTimes:
    def test_valid_config(self) -> None:
        config = {
            "NSE": {"session_open": "09:15", "session_close": "15:30"},
            "MCX": {"session_open": "09:00", "session_close": "23:30"},
        }
        exchange_map = {"NSE": Exchange.NSE, "MCX": Exchange.MCX}
        sessions = _parse_exchange_session_times(config, exchange_map)
        assert Exchange.NSE in sessions
        assert Exchange.MCX in sessions
        assert sessions[Exchange.NSE].open_time == time(9, 15)

    def test_missing_exchange_uses_defaults(self) -> None:
        config = {"NSE": {"session_open": "09:15", "session_close": "15:30"}}
        exchange_map = {"NSE": Exchange.NSE, "MCX": Exchange.MCX}
        sessions = _parse_exchange_session_times(config, exchange_map)
        assert Exchange.MCX not in sessions

    def test_invalid_time_format_raises(self) -> None:
        config = {"NSE": {"session_open": "invalid", "session_close": "15:30"}}
        exchange_map = {"NSE": Exchange.NSE}
        with pytest.raises(ConfigError, match="Invalid time format"):
            _parse_exchange_session_times(config, exchange_map)

    def test_empty_config(self) -> None:
        config: dict[str, dict[str, str]] = {}
        exchange_map = {"NSE": Exchange.NSE}
        sessions = _parse_exchange_session_times(config, exchange_map)
        assert sessions == {}


class TestParseNseCdsHolidays:
    def test_valid_holidays(self) -> None:
        year_config = {
            "nse_cds": [
                {"date": "2026-01-26", "exchanges": ["NSE", "CDS"]},
                {"date": "2026-08-15", "exchanges": ["NSE"]},
            ]
        }
        exchange_map = {"NSE": Exchange.NSE, "CDS": Exchange.CDS}
        holidays = _parse_nse_cds_holidays(year_config, exchange_map)
        assert date(2026, 1, 26) in holidays[Exchange.NSE]
        assert date(2026, 1, 26) in holidays[Exchange.CDS]
        assert date(2026, 8, 15) in holidays[Exchange.NSE]

    def test_no_nse_cds_section(self) -> None:
        year_config = {}
        exchange_map = {"NSE": Exchange.NSE, "CDS": Exchange.CDS}
        holidays = _parse_nse_cds_holidays(year_config, exchange_map)
        assert holidays[Exchange.NSE] == set()
        assert holidays[Exchange.CDS] == set()

    def test_invalid_date_skipped(self) -> None:
        year_config = {
            "nse_cds": [
                {"date": "not-a-date", "exchanges": ["NSE"]},
            ]
        }
        exchange_map = {"NSE": Exchange.NSE}
        holidays = _parse_nse_cds_holidays(year_config, exchange_map)
        assert holidays[Exchange.NSE] == set()

    def test_missing_date_key_skipped(self) -> None:
        year_config = {
            "nse_cds": [
                {"exchanges": ["NSE"]},
            ]
        }
        exchange_map = {"NSE": Exchange.NSE}
        holidays = _parse_nse_cds_holidays(year_config, exchange_map)
        assert holidays[Exchange.NSE] == set()

    def test_default_exchanges(self) -> None:
        year_config = {
            "nse_cds": [
                {"date": "2026-01-26"},
            ]
        }
        exchange_map = {"NSE": Exchange.NSE, "CDS": Exchange.CDS}
        holidays = _parse_nse_cds_holidays(year_config, exchange_map)
        assert date(2026, 1, 26) in holidays[Exchange.NSE]
        assert date(2026, 1, 26) in holidays[Exchange.CDS]


class TestParseMcxHolidays:
    def test_valid_holidays(self) -> None:
        year_config = {
            "mcx": [
                {"date": "2026-01-26"},
                {"date": "2026-03-14"},
            ]
        }
        holidays = _parse_mcx_holidays(year_config)
        assert date(2026, 1, 26) in holidays
        assert date(2026, 3, 14) in holidays

    def test_no_mcx_section(self) -> None:
        year_config = {}
        holidays = _parse_mcx_holidays(year_config)
        assert holidays == set()

    def test_invalid_date_skipped(self) -> None:
        year_config = {
            "mcx": [
                {"date": "not-a-date"},
            ]
        }
        holidays = _parse_mcx_holidays(year_config)
        assert holidays == set()

    def test_missing_date_key_skipped(self) -> None:
        year_config = {
            "mcx": [
                {"exchanges": ["MCX"]},
            ]
        }
        holidays = _parse_mcx_holidays(year_config)
        assert holidays == set()


class TestHelperFunctions:
    def test_initialize_holidays_dict(self) -> None:
        holidays = _initialize_holidays_dict()
        assert Exchange.NSE in holidays
        assert Exchange.BSE in holidays
        assert Exchange.MCX in holidays
        assert Exchange.CDS in holidays
        assert holidays[Exchange.NSE] == set()

    def test_get_exchange_map(self) -> None:
        exchange_map = _get_exchange_map()
        assert exchange_map["NSE"] == Exchange.NSE
        assert exchange_map["BSE"] == Exchange.BSE
        assert exchange_map["MCX"] == Exchange.MCX
        assert exchange_map["CDS"] == Exchange.CDS

    def test_log_holidays_summary(self) -> None:
        holidays = {
            Exchange.NSE: {date(2026, 1, 26)},
            Exchange.BSE: set(),
            Exchange.MCX: {date(2026, 1, 26)},
            Exchange.CDS: {date(2026, 1, 26)},
        }
        _log_holidays_summary(holidays)

    def test_session_exchanges(self) -> None:
        assert Exchange.NSE in SESSION_EXCHANGES
        assert Exchange.BSE in SESSION_EXCHANGES
        assert Exchange.MCX in SESSION_EXCHANGES
        assert Exchange.CDS in SESSION_EXCHANGES
        assert Exchange.BINANCE not in SESSION_EXCHANGES


class TestLoadConfigFile:
    def test_load_valid_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[nse]
session_open = "09:15"
session_close = "15:30"
"""
        )
        config = _load_config_file(config_file)
        assert "nse" in config

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _load_config_file(tmp_path / "missing.toml")

    def test_load_invalid_toml_raises(self, tmp_path: Path) -> None:
        import tomli

        config_file = tmp_path / "bad.toml"
        config_file.write_text("invalid toml {{{")
        with pytest.raises(tomli.TOMLDecodeError):
            _load_config_file(config_file)


class TestLoadSessionTimesFromConfig:
    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "exchanges.toml"
        config_file.write_text(
            """
[nse]
session_open = "09:15"
session_close = "15:30"
"""
        )
        sessions = _load_session_times_from_config(config_file)
        assert Exchange.NSE in sessions

    def test_load_missing_file_returns_defaults(self) -> None:
        sessions = _load_session_times_from_config(Path("nonexistent.toml"))
        assert Exchange.NSE in sessions

    def test_load_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "empty.toml"
        config_file.write_text("")
        sessions = _load_session_times_from_config(config_file)
        assert Exchange.NSE in sessions

    def test_load_invalid_toml_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.toml"
        config_file.write_text("invalid {{{")
        with pytest.raises(ConfigError):
            _load_session_times_from_config(config_file)


class TestLoadHolidaysFromConfig:
    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "holidays.toml"
        config_file.write_text(
            """
["2026"]
nse_cds = [
    {date = "2026-01-26", exchanges = ["NSE", "CDS"]},
]
mcx = [
    {date = "2026-01-26"},
]
"""
        )
        holidays = _load_holidays_from_config(config_file)
        assert date(2026, 1, 26) in holidays[Exchange.NSE]
        assert date(2026, 1, 26) in holidays[Exchange.MCX]

    def test_load_missing_file_returns_defaults(self) -> None:
        holidays = _load_holidays_from_config(Path("nonexistent.toml"))
        assert Exchange.NSE in holidays
        assert date(2026, 1, 26) in holidays[Exchange.NSE]

    def test_load_invalid_toml_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bad.toml"
        config_file.write_text("invalid {{{")
        with pytest.raises(ConfigError):
            _load_holidays_from_config(config_file)

    def test_load_non_year_keys_skipped(self, tmp_path: Path) -> None:
        config_file = tmp_path / "holidays.toml"
        config_file.write_text(
            """
[note]
description = "This is not a year"
"""
        )
        holidays = _load_holidays_from_config(config_file)
        assert holidays[Exchange.NSE] == set()
