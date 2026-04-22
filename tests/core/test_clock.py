"""
Tests for clock utilities.
"""

import random
from datetime import UTC, date, datetime, time, timedelta, timezone

import numpy as np
import pytest
import torch
from iatb.core.clock import Clock, TradingSessions
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError
from iatb.core.exchange_calendar import ExchangeCalendar, SessionWindow

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestClock:
    """Test Clock class."""

    def test_now_returns_utc_timestamp(self) -> None:
        """Test that now returns UTC timestamp."""
        timestamp = Clock.now()
        assert timestamp.tzinfo == UTC
        assert isinstance(timestamp, datetime)

    def test_to_utc_with_naive_datetime(self) -> None:
        """Test converting naive datetime to UTC."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        timestamp = Clock.to_utc(dt)
        assert timestamp.tzinfo == UTC
        assert timestamp.hour == 12

    def test_to_utc_with_aware_datetime(self) -> None:
        """Test converting aware datetime to UTC."""
        tz = timezone(timedelta(hours=5, minutes=30))
        dt = datetime(2024, 1, 1, 17, 30, 0, tzinfo=tz)
        timestamp = Clock.to_utc(dt)
        assert timestamp.tzinfo == UTC
        assert timestamp.hour == 12

    def test_to_ist(self) -> None:
        """Test converting UTC to IST."""
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)
        assert ist_dt.tzinfo is None
        assert ist_dt.hour == 17
        assert ist_dt.minute == 30

    def test_to_ist_naive_raises_error(self) -> None:
        """Test that naive datetime raises error."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="Input datetime must be timezone-aware"):
            Clock.to_ist(dt)

    def test_ist_to_utc(self) -> None:
        """Test converting IST to UTC."""
        ist_dt = datetime(2024, 1, 1, 17, 30, 0)  # noqa: DTZ001
        timestamp = Clock.ist_to_utc(ist_dt)
        assert timestamp.tzinfo == UTC
        assert timestamp.hour == 12

    def test_ist_to_utc_aware_raises_error(self) -> None:
        """Test that aware datetime raises error."""
        dt = datetime(2024, 1, 1, 17, 30, 0, tzinfo=UTC)
        with pytest.raises(ClockError, match="Input datetime should be naive"):
            Clock.ist_to_utc(dt)


class TestTradingSessions:
    """Test TradingSessions class."""

    def test_nse_session_times(self) -> None:
        """Test NSE session times."""
        open_time, close_time = TradingSessions._get_session_times("NSE")
        assert open_time == time(9, 15)
        assert close_time == time(15, 30)

    def test_bse_session_times(self) -> None:
        """Test BSE session times."""
        open_time, close_time = TradingSessions._get_session_times("BSE")
        assert open_time == time(9, 15)
        assert close_time == time(15, 30)

    def test_mcx_session_times(self) -> None:
        """Test MCX session times."""
        open_time, close_time = TradingSessions._get_session_times("MCX")
        assert open_time == time(9, 0)
        assert close_time == time(23, 30)

    def test_cds_session_times(self) -> None:
        """Test CDS session times."""
        open_time, close_time = TradingSessions._get_session_times("CDS")
        assert open_time == time(9, 0)
        assert close_time == time(17, 30)

    def test_invalid_exchange_raises_error(self) -> None:
        """Test that invalid exchange raises error."""
        with pytest.raises(ClockError, match="Unknown exchange"):
            TradingSessions._get_session_times("INVALID")  # type: ignore[arg-type]

    def test_is_market_open_during_nse_hours(self) -> None:
        """Test market open during NSE hours."""
        # 10:00 UTC = 15:30 IST
        utc_dt = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        # Actually 10:00 UTC = 15:30 IST, which is close time, so not open
        # Let's use 09:00 UTC = 14:30 IST (during session)
        utc_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        assert TradingSessions.is_market_open(utc_dt, Exchange.NSE)

    def test_is_market_closed_outside_nse_hours(self) -> None:
        """Test market closed outside NSE hours."""
        # 00:00 UTC = 05:30 IST (before open)
        utc_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert not TradingSessions.is_market_open(utc_dt, Exchange.NSE)

    def test_is_market_open_during_mcx_hours(self) -> None:
        """Test market open during MCX hours."""
        # 09:00 UTC = 14:30 IST (during MCX session)
        utc_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        assert TradingSessions.is_market_open(utc_dt, Exchange.MCX)

    def test_is_market_open_during_cds_hours(self) -> None:
        """Test market open during CDS hours."""
        # 09:00 UTC = 14:30 IST (during CDS session)
        utc_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        assert TradingSessions.is_market_open(utc_dt, Exchange.CDS)

    def test_is_market_open_naive_raises_error(self) -> None:
        """Test that naive datetime raises error."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="Input datetime must be timezone-aware"):
            TradingSessions.is_market_open(dt, Exchange.NSE)

    def test_is_market_open_non_utc_raises_error(self) -> None:
        """Test that non-UTC aware datetime raises error."""
        ist = timezone(timedelta(hours=5, minutes=30))
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=ist)
        with pytest.raises(ClockError, match="Input datetime must use UTC timezone"):
            TradingSessions.is_market_open(dt, Exchange.NSE)

    def test_is_market_open_unsupported_exchange_returns_false(self) -> None:
        """Test exchanges without defined sessions return closed."""
        utc_dt = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        assert not TradingSessions.is_market_open(utc_dt, Exchange.BINANCE)

    def test_is_trading_day_weekday(self) -> None:
        """Test that weekdays are trading days."""
        # Monday (weekday 0)
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)  # Monday
        assert TradingSessions.is_trading_day(utc_dt)

    def test_is_trading_day_weekend(self) -> None:
        """Test that weekends are not trading days."""
        # Saturday (weekday 5)
        utc_dt = datetime(2024, 1, 6, 12, 0, 0, tzinfo=UTC)  # Saturday
        assert not TradingSessions.is_trading_day(utc_dt)

    def test_is_trading_day_holiday(self) -> None:
        """Test configured exchange holiday is not a trading day."""
        # Republic Day 2026
        utc_dt = datetime(2026, 1, 26, 6, 0, 0, tzinfo=UTC)
        assert not TradingSessions.is_trading_day(utc_dt, Exchange.NSE)

    def test_is_trading_day_unsupported_exchange_returns_false(self) -> None:
        """Test unsupported exchanges are never marked as active sessions."""
        utc_dt = datetime(2024, 1, 1, 6, 0, 0, tzinfo=UTC)
        assert not TradingSessions.is_trading_day(utc_dt, Exchange.BINANCE)

    def test_is_trading_day_naive_raises_error(self) -> None:
        """Test that naive datetime raises error."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="Input datetime must be timezone-aware"):
            TradingSessions.is_trading_day(dt)

    def test_next_open_time_before_market_open(self) -> None:
        """Test next open time before market opens."""
        # 03:00 UTC = 08:30 IST (before NSE open at 09:15)
        utc_dt = datetime(2024, 1, 1, 3, 30, 0, tzinfo=UTC)  # Monday
        next_open = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        # Should be today's open: 03:45 UTC = 09:15 IST
        assert next_open.hour == 3
        assert next_open.minute == 45

    def test_next_open_time_during_market_hours(self) -> None:
        """Test next open time during market hours."""
        # 08:00 UTC = 13:30 IST (during NSE session)
        utc_dt = datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)  # Monday
        next_open = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        # Should be next day's open
        assert next_open.day == 2

    def test_next_open_time_after_market_close(self) -> None:
        """Test next open time after market closes."""
        # 12:00 UTC = 17:30 IST (after NSE close at 15:30)
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)  # Monday
        next_open = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        # Should be next day's open
        assert next_open.day == 2

    def test_next_open_time_weekend(self) -> None:
        """Test next open time on weekend."""
        # Saturday
        utc_dt = datetime(2024, 1, 6, 12, 0, 0, tzinfo=UTC)
        next_open = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        # Should be Monday's open
        assert next_open.day == 8

    def test_next_open_time_naive_raises_error(self) -> None:
        """Test that naive datetime raises error."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="Input datetime must be timezone-aware"):
            TradingSessions.next_open_time(dt, Exchange.NSE)

    def test_next_open_time_unsupported_exchange_raises_error(self) -> None:
        """Test unsupported exchange next-open request fails closed."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        with pytest.raises(ClockError, match="No trading session defined for exchange"):
            TradingSessions.next_open_time(dt, Exchange.BINANCE)

    def test_holiday_market_closed_during_regular_hours(self) -> None:
        """Test market closed on configured holiday during regular hours."""
        # 05:00 UTC = 10:30 IST on Republic Day 2026
        holiday_time = datetime(2026, 1, 26, 5, 0, 0, tzinfo=UTC)
        assert not TradingSessions.is_market_open(holiday_time, Exchange.NSE)

    def test_special_session_market_open(self) -> None:
        """Test special session overrides weekend/holiday closure."""
        # Special session: 18:00-19:00 IST on 2026-11-08
        special_session_time = datetime(2026, 11, 8, 12, 35, 0, tzinfo=UTC)  # 18:05 IST
        assert TradingSessions.is_market_open(special_session_time, Exchange.NSE)

    def test_get_session_times_missing_calendar_entry_raises_error(self) -> None:
        """Test misconfigured calendar fails closed for known exchange literal."""
        original_calendar = TradingSessions.calendar
        TradingSessions.calendar = ExchangeCalendar(
            regular_sessions={},
            holidays={},
            special_sessions={},
        )
        try:
            with pytest.raises(ClockError, match="Unknown exchange"):
                TradingSessions._get_session_times("NSE")
        finally:
            TradingSessions.calendar = original_calendar

    def test_next_open_time_resolution_failure_raises_error(self) -> None:
        """Test inability to resolve next session fails closed."""

        class NeverOpenCalendar(ExchangeCalendar):
            def session_for(self, exchange: Exchange, trading_date: date) -> SessionWindow | None:
                return None

        original_calendar = TradingSessions.calendar
        TradingSessions.calendar = NeverOpenCalendar(
            regular_sessions={
                Exchange.NSE: SessionWindow(open_time=time(9, 15), close_time=time(15, 30))
            },
            holidays={Exchange.NSE: set()},
            special_sessions={Exchange.NSE: {}},
        )
        try:
            with pytest.raises(ClockError, match="Unable to resolve next open time"):
                TradingSessions._next_open_time_for_date(Exchange.NSE, date(2024, 1, 1))
        finally:
            TradingSessions.calendar = original_calendar
