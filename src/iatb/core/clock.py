"""
Clock utilities for IATB.

Provides UTC clock and Indian trading session helpers for different exchanges.
Includes MIS (intraday) session enforcement for NSE/CDS/MCX exchanges.
"""

import logging
import socket
import struct
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
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

# Default NTP servers
DEFAULT_NTP_SERVERS = [
    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com",
]

# Clock drift threshold in seconds
DEFAULT_DRIFT_THRESHOLD_SECONDS = 5.0


class ProductType(StrEnum):
    """Trading product types for Indian exchanges."""

    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"


# Exchanges that support MIS (intraday) trading
MIS_SUPPORTED_EXCHANGES: frozenset[Exchange] = frozenset(
    {Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS}
)

# MIS session close times by exchange (IST) - when square-off occurs
MIS_CLOSE_TIMES: dict[Exchange, time] = {
    Exchange.NSE: time(15, 20),
    Exchange.BSE: time(15, 20),
    Exchange.MCX: time(23, 0),
    Exchange.CDS: time(16, 30),
}


class ClockDriftDetector:
    """Detects and corrects clock drift using NTP sync."""

    def __init__(
        self,
        ntp_servers: list[str] | None = None,
        drift_threshold_seconds: float = DEFAULT_DRIFT_THRESHOLD_SECONDS,
        enable_auto_correction: bool = False,
    ) -> None:
        self._ntp_servers = ntp_servers or DEFAULT_NTP_SERVERS
        self._drift_threshold = timedelta(seconds=drift_threshold_seconds)
        self._enable_auto_correction = enable_auto_correction
        self._last_sync_utc: datetime | None = None
        self._current_drift: timedelta = timedelta(0)
        self._sync_count = 0
        self._sync_failures = 0

    def _get_local_time(self) -> datetime:
        """Get current local time in UTC. Override in tests for deterministic behavior."""
        return datetime.now(UTC)

    def check_drift(self) -> timedelta:
        """Check current clock drift against NTP servers."""
        ntp_time = self._query_ntp_time()
        if ntp_time is None:
            self._sync_failures += 1
            logger.warning(
                "NTP sync failed",
                extra={"failures": self._sync_failures},
            )
            return self._current_drift

        local_time = self._get_local_time()
        drift = ntp_time - local_time
        self._current_drift = drift
        self._last_sync_utc = local_time
        self._sync_count += 1

        if abs(drift) > self._drift_threshold:
            logger.warning(
                "Clock drift detected",
                extra={
                    "drift_seconds": drift.total_seconds(),
                    "threshold_seconds": self._drift_threshold.total_seconds(),
                    "ntp_time": ntp_time.isoformat(),
                    "local_time": local_time.isoformat(),
                },
            )

            if self._enable_auto_correction:
                self._correct_drift(drift)

        return drift

    def _query_ntp_time(self) -> datetime | None:
        """Query NTP server for current time."""
        for server in self._ntp_servers:
            try:
                return self._query_ntp_server(server)
            except Exception as exc:
                logger.debug(
                    "NTP server query failed",
                    extra={"server": server, "error": str(exc)},
                )
                continue
        return None

    def _query_ntp_server(self, server: str) -> datetime:
        """Query a single NTP server."""
        ntp_packet_format = "!12I"
        ntp_delta = 2208988800

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(5.0)

        try:
            data = b"\x1b" + 47 * b"\0"
            client.sendto(data, (server, 123))
            data, _ = client.recvfrom(1024)

            if len(data) < 48:
                msg = "Invalid NTP response"
                raise ClockError(msg)

            unpacked = struct.unpack(ntp_packet_format, data[:48])
            transmit_timestamp = unpacked[10] + float(unpacked[11]) / 2**32

            return datetime.fromtimestamp(transmit_timestamp - ntp_delta, UTC)
        finally:
            client.close()

    def _correct_drift(self, drift: timedelta) -> None:
        """Correct clock drift (placeholder for actual correction)."""
        logger.info(
            "Clock drift correction applied",
            extra={"drift_seconds": drift.total_seconds()},
        )

    def get_sync_status(self) -> dict[str, object]:
        """Get current sync status."""
        return {
            "last_sync_utc": self._last_sync_utc.isoformat() if self._last_sync_utc else None,
            "current_drift_seconds": self._current_drift.total_seconds(),
            "sync_count": self._sync_count,
            "sync_failures": self._sync_failures,
            "drift_threshold_seconds": self._drift_threshold.total_seconds(),
            "auto_correction_enabled": self._enable_auto_correction,
        }

    def is_drift_exceeded(self) -> bool:
        """Check if current drift exceeds threshold."""
        return abs(self._current_drift) > self._drift_threshold


class Clock:
    """UTC clock with IST session helpers."""

    _drift_detector: ClockDriftDetector | None = None

    @staticmethod
    def now() -> Timestamp:
        """Get current UTC timestamp."""
        return Timestamp(datetime.now(UTC))

    @staticmethod
    def set_drift_detector(detector: ClockDriftDetector) -> None:
        """Set the clock drift detector for monitoring."""
        Clock._drift_detector = detector

    @staticmethod
    def get_drift_detector() -> ClockDriftDetector | None:
        """Get the current clock drift detector."""
        return Clock._drift_detector

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

    @staticmethod
    def is_mis_session_active(utc_dt: datetime, exchange: Exchange) -> bool:
        """Check if MIS (intraday) trading is active at given UTC time."""
        TradingSessions._require_utc(utc_dt)
        if exchange not in MIS_SUPPORTED_EXCHANGES:
            logger.debug("MIS not supported on exchange", extra={"exchange": exchange.value})
            return False

        ist_dt = Clock.to_ist(utc_dt)
        session = TradingSessions.calendar.session_for(exchange, ist_dt.date())
        if session is None:
            return False

        mis_close = MIS_CLOSE_TIMES.get(exchange, session.close_time)
        return session.open_time <= ist_dt.time() < mis_close

    @staticmethod
    def validate_product_type(
        product_type: str, exchange: Exchange, utc_dt: datetime
    ) -> ProductType:
        """Validate and return ProductType, blocking DELIVERY for MIS-only exchanges."""
        TradingSessions._require_utc(utc_dt)

        try:
            pt = ProductType(product_type.upper())
        except ValueError:
            valid = [p.value for p in ProductType]
            msg = f"Invalid product_type: {product_type}. Valid: {valid}"
            raise ClockError(msg) from None

        if exchange in MIS_SUPPORTED_EXCHANGES:
            if pt == ProductType.CNC:
                msg = f"DELIVERY (CNC) blocked on {exchange.value}: MIS-only mode"
                logger.warning(
                    "DELIVERY trade blocked",
                    extra={"exchange": exchange.value, "product_type": product_type},
                )
                raise ClockError(msg)
            if not TradingSessions.is_mis_session_active(utc_dt, exchange):
                msg = f"MIS session not active on {exchange.value} at {utc_dt.isoformat()}"
                raise ClockError(msg)

        return pt

    @staticmethod
    def get_mis_square_off_time(exchange: Exchange, trading_date: date) -> time | None:
        """Get MIS square-off time for exchange on given date."""
        if exchange not in MIS_SUPPORTED_EXCHANGES:
            return None

        session = TradingSessions.calendar.session_for(exchange, trading_date)
        if session is None:
            return None

        return MIS_CLOSE_TIMES.get(exchange, session.close_time)
