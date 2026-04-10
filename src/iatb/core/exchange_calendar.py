"""
Exchange calendar abstractions for trading-session calculations.

Loads official session timings and holiday calendar from config files.
"""

import logging
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

SESSION_EXCHANGES = frozenset({Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS})

# Config file paths (relative to project root)
EXCHANGES_CONFIG_PATH = Path("config/exchanges.toml")
HOLIDAYS_CONFIG_PATH = Path("config/nse_holidays.toml")


@dataclass(frozen=True)
class SessionWindow:
    """Market session open/close window in IST."""

    open_time: time
    close_time: time


class ExchangeCalendar:
    """Trading-day resolver with holidays and special sessions."""

    def __init__(
        self,
        regular_sessions: dict[Exchange, SessionWindow],
        holidays: dict[Exchange, set[date]],
        special_sessions: dict[Exchange, dict[date, SessionWindow]],
    ) -> None:
        self._regular_sessions = regular_sessions
        self._holidays = holidays
        self._special_sessions = special_sessions

    def get_regular_session(self, exchange: Exchange) -> SessionWindow | None:
        """Get regular session window for an exchange."""
        return self._regular_sessions.get(exchange)

    def session_for(self, exchange: Exchange, trading_date: date) -> SessionWindow | None:
        """Resolve effective session for an exchange/date pair."""
        regular = self._regular_sessions.get(exchange)
        if regular is None:
            return None

        special = self._special_sessions.get(exchange, {}).get(trading_date)
        if special is not None:
            return special

        if trading_date.weekday() >= 5:
            return None
        if trading_date in self._holidays.get(exchange, set()):
            return None
        return regular

    def is_holiday(self, exchange: Exchange, trading_date: date) -> bool:
        """Check if a day is a configured holiday for the exchange."""
        return trading_date in self._holidays.get(exchange, set())

    def is_trading_day(self, exchange: Exchange, trading_date: date) -> bool:
        """Check if exchange has an active session on the given date."""
        return self.session_for(exchange, trading_date) is not None


def _load_config_file(config_path: Path) -> dict[str, Any]:
    """Load TOML config file.

    Args:
        config_path: Path to TOML config file.

    Returns:
        Parsed config dictionary.

    Raises:
        ConfigError: If config file cannot be loaded.
    """
    try:
        import tomli

        with config_path.open("rb") as f:
            result: dict[str, Any] = tomli.load(f)
            return result
    except FileNotFoundError:
        logger.warning(
            "Config file not found, using defaults",
            extra={"config_path": str(config_path)},
        )
        return {}
    except Exception as e:
        msg = f"Failed to load config from {config_path}: {e}"
        raise ConfigError(msg) from e


def _parse_session_times(config: dict[str, Any]) -> dict[Exchange, SessionWindow]:
    """Parse session times from config dictionary.

    Args:
        config: Parsed config dictionary.

    Returns:
        Dictionary mapping Exchange to SessionWindow.
    """
    sessions: dict[Exchange, SessionWindow] = {}
    exchange_map = {
        "NSE": Exchange.NSE,
        "BSE": Exchange.BSE,
        "MCX": Exchange.MCX,
        "CDS": Exchange.CDS,
    }

    for exchange_name, exchange_enum in exchange_map.items():
        if exchange_name in config:
            section = config[exchange_name]
            open_str = section.get("session_open", "09:15")
            close_str = section.get("session_close", "15:30")

            try:
                open_time = time.fromisoformat(open_str)
                close_time = time.fromisoformat(close_str)
                sessions[exchange_enum] = SessionWindow(open_time=open_time, close_time=close_time)
                logger.debug(
                    "Loaded session times",
                    extra={
                        "exchange": exchange_name,
                        "open": open_str,
                        "close": close_str,
                    },
                )
            except ValueError as e:
                msg = f"Invalid time format for {exchange_name}: open={open_str}, close={close_str}"
                raise ConfigError(msg) from e

    return sessions


def _load_session_times_from_config(
    config_path: Path = EXCHANGES_CONFIG_PATH,
) -> dict[Exchange, SessionWindow]:
    """Load session timings from exchanges.toml config file.

    Args:
        config_path: Path to exchanges.toml config file.

    Returns:
        Dictionary mapping Exchange to SessionWindow.
    """
    config = _load_config_file(config_path)
    if not config:
        return _default_regular_sessions()
    sessions = _parse_session_times(config)
    return sessions if sessions else _default_regular_sessions()


def _get_exchange_map() -> dict[str, Exchange]:
    """Get mapping from exchange name to Exchange enum."""
    return {
        "NSE": Exchange.NSE,
        "BSE": Exchange.BSE,
        "MCX": Exchange.MCX,
        "CDS": Exchange.CDS,
    }


def _init_holidays_dict() -> dict[Exchange, set[date]]:
    """Initialize empty holidays dictionary for all exchanges."""
    return {
        Exchange.NSE: set(),
        Exchange.BSE: set(),
        Exchange.MCX: set(),
        Exchange.CDS: set(),
    }


def _parse_nse_cds_holiday(
    holiday: dict[str, Any], exchange_map: dict[str, Exchange], holidays: dict[Exchange, set[date]]
) -> None:
    """Parse NSE/CDS holiday entry and add to holidays dict."""
    try:
        holiday_date = date.fromisoformat(holiday["date"])
        exchanges = holiday.get("exchanges", ["NSE", "CDS"])
        for exch_name in exchanges:
            if exch_name in exchange_map:
                holidays[exchange_map[exch_name]].add(holiday_date)
    except (ValueError, KeyError) as e:
        logger.warning(
            "Failed to parse NSE/CDS holiday",
            extra={"holiday": holiday, "error": str(e)},
        )


def _parse_mcx_holiday(holiday: dict[str, Any], holidays: dict[Exchange, set[date]]) -> None:
    """Parse MCX holiday entry and add to holidays dict."""
    try:
        holiday_date = date.fromisoformat(holiday["date"])
        holidays[Exchange.MCX].add(holiday_date)
    except (ValueError, KeyError) as e:
        logger.warning(
            "Failed to parse MCX holiday",
            extra={"holiday": holiday, "error": str(e)},
        )


def _parse_year_holidays(
    year_config: dict[str, Any],
    exchange_map: dict[str, Exchange],
    holidays: dict[Exchange, set[date]],
) -> None:
    """Parse holidays for a single year."""
    if "nse_cds" in year_config:
        for holiday in year_config["nse_cds"]:
            _parse_nse_cds_holiday(holiday, exchange_map, holidays)

    if "mcx" in year_config:
        for holiday in year_config["mcx"]:
            _parse_mcx_holiday(holiday, holidays)


def _load_holidays_from_config(
    config_path: Path = HOLIDAYS_CONFIG_PATH,
) -> dict[Exchange, set[date]]:
    """Load holiday calendar from nse_holidays.toml config file.

    Args:
        config_path: Path to nse_holidays.toml config file.

    Returns:
        Dictionary mapping Exchange to set of holiday dates.
    """
    config = _load_config_file(config_path)
    if not config:
        return _default_holidays()

    holidays = _init_holidays_dict()
    exchange_map = _get_exchange_map()

    for year_key, year_config in config.items():
        if year_key.isdigit():
            _parse_year_holidays(year_config, exchange_map, holidays)

    logger.info(
        "Loaded holiday calendar",
        extra={
            "nse_holidays": len(holidays[Exchange.NSE]),
            "bse_holidays": len(holidays[Exchange.BSE]),
            "mcx_holidays": len(holidays[Exchange.MCX]),
            "cds_holidays": len(holidays[Exchange.CDS]),
        },
    )

    return holidays


def _default_regular_sessions() -> dict[Exchange, SessionWindow]:
    """Fallback default session times if config loading fails."""
    return {
        Exchange.NSE: SessionWindow(open_time=time(9, 15), close_time=time(15, 30)),
        Exchange.BSE: SessionWindow(open_time=time(9, 15), close_time=time(15, 30)),
        Exchange.MCX: SessionWindow(open_time=time(9, 0), close_time=time(23, 30)),
        Exchange.CDS: SessionWindow(open_time=time(9, 0), close_time=time(17, 0)),
    }


def _default_holidays() -> dict[Exchange, set[date]]:
    common_holidays = {
        date(2026, 1, 26),  # Republic Day
        date(2026, 8, 15),  # Independence Day
        date(2026, 10, 2),  # Gandhi Jayanti
        date(2026, 12, 25),  # Christmas
    }
    return {
        Exchange.NSE: set(common_holidays),
        Exchange.BSE: set(common_holidays),
        Exchange.MCX: set(common_holidays),
        Exchange.CDS: set(common_holidays),
    }


def _default_special_sessions() -> dict[Exchange, dict[date, SessionWindow]]:
    muhurat_day = date(2026, 11, 8)
    return {
        Exchange.NSE: {muhurat_day: SessionWindow(open_time=time(18, 0), close_time=time(19, 0))},
        Exchange.BSE: {muhurat_day: SessionWindow(open_time=time(18, 0), close_time=time(19, 0))},
        Exchange.MCX: {muhurat_day: SessionWindow(open_time=time(18, 0), close_time=time(21, 0))},
        Exchange.CDS: {muhurat_day: SessionWindow(open_time=time(18, 0), close_time=time(19, 0))},
    }


# Load session times and holidays from config files
# Falls back to defaults if config files are not available
try:
    DEFAULT_EXCHANGE_CALENDAR = ExchangeCalendar(
        regular_sessions=_load_session_times_from_config(),
        holidays=_load_holidays_from_config(),
        special_sessions=_default_special_sessions(),
    )
    logger.info("Exchange calendar initialized from config files")
except ConfigError:
    # Fallback to defaults if config loading fails
    DEFAULT_EXCHANGE_CALENDAR = ExchangeCalendar(
        regular_sessions=_default_regular_sessions(),
        holidays=_default_holidays(),
        special_sessions=_default_special_sessions(),
    )
    logger.warning("Exchange calendar initialized with default values")
