"""
Exchange calendar abstractions for trading-session calculations.
"""

from dataclasses import dataclass
from datetime import date, time

from iatb.core.enums import Exchange

SESSION_EXCHANGES = frozenset({Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS})


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


def _default_regular_sessions() -> dict[Exchange, SessionWindow]:
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


DEFAULT_EXCHANGE_CALENDAR = ExchangeCalendar(
    regular_sessions=_default_regular_sessions(),
    holidays=_default_holidays(),
    special_sessions=_default_special_sessions(),
)
