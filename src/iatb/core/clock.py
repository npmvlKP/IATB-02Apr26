"""
Clock utilities for IATB.

Provides UTC clock and Indian trading session helpers for different exchanges.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError
from iatb.core.exchange_calendar import (
    DEFAULT_EXCHANGE_CALENDAR,
    SESSION_EXCHANGES,
    ExchangeCalendar,
)
from iatb.core.types import Timestamp

logger = logging.getLogger(__name__)

# IST timezone offset (UTC+5:30)
IST_OFFSET = timedelta(hours=5, minutes=30)


class Clock:
    """UTC clock with IST session helpers."""

    @staticmethod
    def now() -> Timestamp:
        """Get current UTC timestamp."""
        return Timestamp(datetime.now(UTC))

    @staticmethod
    def to_utc(dt: datetime) -> Timestamp:
        """Convert a datetime to UTC."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        elif dt.tzinfo != UTC:
            dt = dt.astimezone(UTC)
        return Timestamp(dt)

    @staticmethod
    def to_ist(utc_dt: datetime) -> datetime:
        """Convert UTC datetime to IST."""
        if utc_dt.tzinfo is None:
            msg = "Input datetime must be timezone-aware"
            raise ClockError(msg)

        utc_dt = utc_dt.astimezone(UTC)
        ist_dt = utc_dt + IST_OFFSET
        return ist_dt.replace(tzinfo=None)

    @staticmethod
    def ist_to_utc(ist_dt: datetime) -> Timestamp:
        """Convert IST datetime (naive) to UTC timestamp."""
        if ist_dt.tzinfo is not None:
            msg = "Input datetime should be naive (IST)"
            raise ClockError(msg)

        utc_dt = ist_dt - IST_OFFSET
        return Timestamp(utc_dt.replace(tzinfo=UTC))


class TradingSessions:
    """Trading session utilities for Indian exchanges."""

    calendar: ExchangeCalendar = DEFAULT_EXCHANGE_CALENDAR

    @staticmethod
    def _require_utc(utc_dt: datetime) -> None:
        if utc_dt.tzinfo is None:
            msg = "Input datetime must be timezone-aware"
            raise ClockError(msg)
        if utc_dt.tzinfo != UTC:
            msg = "Input datetime must use UTC timezone"
            raise ClockError(msg)

    @staticmethod
    def _get_session_times(exchange: Literal["NSE", "BSE", "MCX", "CDS"]) -> tuple[time, time]:
        """Get regular session open/close times for an exchange."""
        try:
            exchange_enum = Exchange(exchange)
        except ValueError as exc:
            msg = f"Unknown exchange: {exchange}"
            raise ClockError(msg) from exc

        session = TradingSessions.calendar.get_regular_session(exchange_enum)
        if session is None:
            msg = f"Unknown exchange: {exchange}"
            raise ClockError(msg)
        return session.open_time, session.close_time

    @staticmethod
    def is_market_open(utc_dt: datetime, exchange: Exchange) -> bool:
        """Check if market is open at given UTC time."""
        TradingSessions._require_utc(utc_dt)
        if exchange not in SESSION_EXCHANGES:
            return False

        ist_dt = Clock.to_ist(utc_dt)
        session = TradingSessions.calendar.session_for(exchange, ist_dt.date())
        if session is None:
            return False
        return session.open_time <= ist_dt.time() < session.close_time

    @staticmethod
    def is_trading_day(utc_dt: datetime, exchange: Exchange = Exchange.NSE) -> bool:
        """Check if given UTC time maps to an active trading day."""
        TradingSessions._require_utc(utc_dt)
        if exchange not in SESSION_EXCHANGES:
            return False

        ist_dt = Clock.to_ist(utc_dt)
        return TradingSessions.calendar.is_trading_day(exchange, ist_dt.date())

    @staticmethod
    def next_open_time(utc_dt: datetime, exchange: Exchange) -> Timestamp:
        """Get next market open time after given UTC time."""
        TradingSessions._require_utc(utc_dt)
        if exchange not in SESSION_EXCHANGES:
            msg = f"No trading session defined for exchange: {exchange.value}"
            raise ClockError(msg)

        ist_dt = Clock.to_ist(utc_dt)
        current_date = ist_dt.date()
        current_time = ist_dt.time()

        today_session = TradingSessions.calendar.session_for(exchange, current_date)
        if today_session is not None and current_time < today_session.open_time:
            ist_open = datetime.combine(current_date, today_session.open_time)
            return Clock.ist_to_utc(ist_open)

        return TradingSessions._next_open_time_for_date(exchange, current_date + timedelta(days=1))

    @staticmethod
    def _next_open_time_for_date(exchange: Exchange, start_date: date) -> Timestamp:
        """Find the next open time from a start date."""
        probe_date = start_date
        for _ in range(730):
            session = TradingSessions.calendar.session_for(exchange, probe_date)
            if session is not None:
                return Clock.ist_to_utc(datetime.combine(probe_date, session.open_time))
            probe_date += timedelta(days=1)

        msg = f"Unable to resolve next open time for exchange: {exchange.value}"
        raise ClockError(msg)
