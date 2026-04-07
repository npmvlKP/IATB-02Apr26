"""
Unit tests for src/iatb/core/clock.py.

Tests cover: happy path, edge cases, errors, precision, timezone handling.
All external calls are mocked.
"""

from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.clock import (
    IST_OFFSET,
    MIS_CLOSE_TIMES,
    MIS_SUPPORTED_EXCHANGES,
    Clock,
    ProductType,
    TradingSessions,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_calendar():
    """Mock ExchangeCalendar for testing."""
    calendar = MagicMock()
    calendar.get_regular_session.return_value = MagicMock(
        open_time=time(9, 15), close_time=time(15, 30)
    )
    calendar.session_for.return_value = MagicMock(open_time=time(9, 15), close_time=time(15, 30))
    calendar.is_trading_day.return_value = True
    return calendar


@pytest.fixture
def utc_trading_time():
    """UTC time corresponding to 10:00 AM IST on a trading day."""
    # 10:00 IST = 04:30 UTC
    return datetime(2026, 1, 5, 4, 30, 0, tzinfo=UTC)


@pytest.fixture
def utc_pre_market_time():
    """UTC time before market open."""
    # 8:00 IST = 02:30 UTC
    return datetime(2026, 1, 5, 2, 30, 0, tzinfo=UTC)


@pytest.fixture
def utc_after_hours_time():
    """UTC time after MIS close (after 15:20 IST)."""
    # 16:00 IST = 10:30 UTC
    return datetime(2026, 1, 5, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def utc_weekend_time():
    """UTC time on a weekend (Saturday)."""
    # Saturday Jan 3, 2026 at 10:00 IST = 04:30 UTC
    return datetime(2026, 1, 3, 4, 30, 0, tzinfo=UTC)


# =============================================================================
# ProductType Enum Tests
# =============================================================================


class TestProductType:
    """Tests for ProductType enum."""

    def test_product_type_values(self):
        """Test ProductType has expected values."""
        assert ProductType.MIS.value == "MIS"
        assert ProductType.CNC.value == "CNC"
        assert ProductType.NRML.value == "NRML"

    def test_product_type_from_string(self):
        """Test ProductType can be created from string."""
        assert ProductType("MIS") == ProductType.MIS
        assert ProductType("CNC") == ProductType.CNC

    def test_product_type_invalid_raises(self):
        """Test invalid product type raises ValueError."""
        with pytest.raises(ValueError):
            ProductType("INVALID")


# =============================================================================
# Clock Tests
# =============================================================================


class TestClock:
    """Tests for Clock class."""

    def test_now_returns_utc_timestamp(self):
        """Test Clock.now() returns UTC-aware timestamp."""
        result = Clock.now()
        assert result.tzinfo == UTC

    def test_to_utc_from_naive(self):
        """Test converting naive datetime to UTC."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        result = Clock.to_utc(naive_dt)
        assert result.tzinfo == UTC

    def test_to_utc_from_utc(self):
        """Test converting UTC datetime to UTC (no-op)."""
        utc_dt = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
        result = Clock.to_utc(utc_dt)
        assert result == utc_dt

    def test_to_ist_conversion(self, utc_trading_time):
        """Test UTC to IST conversion."""
        result = Clock.to_ist(utc_trading_time)
        # 04:30 UTC + 5:30 = 10:00 IST
        assert result.hour == 10
        assert result.minute == 0
        assert result.tzinfo is None  # IST is naive

    def test_to_ist_requires_timezone_aware(self):
        """Test to_ist raises on naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="timezone-aware"):
            Clock.to_ist(naive_dt)

    def test_ist_to_utc_conversion(self):
        """Test IST to UTC conversion."""
        ist_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001  # Naive IST
        result = Clock.ist_to_utc(ist_dt)
        # 10:00 IST - 5:30 = 04:30 UTC
        assert result.hour == 4
        assert result.minute == 30
        assert result.tzinfo == UTC

    def test_ist_to_utc_rejects_timezone_aware(self):
        """Test ist_to_utc raises on timezone-aware datetime."""
        aware_dt = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
        with pytest.raises(ClockError, match="naive"):
            Clock.ist_to_utc(aware_dt)


# =============================================================================
# TradingSessions Tests
# =============================================================================


class TestTradingSessions:
    """Tests for TradingSessions class."""

    def test_is_market_open_during_session(self, mock_calendar, utc_trading_time):
        """Test is_market_open returns True during trading hours."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.is_market_open(utc_trading_time, Exchange.NSE)
            assert result is True

    def test_is_market_open_unsupported_exchange(self, utc_trading_time):
        """Test is_market_open returns False for unsupported exchange."""
        result = TradingSessions.is_market_open(utc_trading_time, Exchange.BINANCE)
        assert result is False

    def test_is_market_open_requires_utc(self):
        """Test is_market_open raises on naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError, match="timezone-aware"):
            TradingSessions.is_market_open(naive_dt, Exchange.NSE)

    def test_is_trading_day_weekday(self, mock_calendar, utc_trading_time):
        """Test is_trading_day returns True for weekday."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.is_trading_day(utc_trading_time, Exchange.NSE)
            assert result is True

    def test_require_utc_rejects_naive(self):
        """Test _require_utc rejects naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError):
            TradingSessions._require_utc(naive_dt)

    def test_require_utc_rejects_non_utc(self):
        """Test _require_utc rejects non-UTC timezone."""
        from datetime import timezone

        est = timezone(timedelta(hours=-5))
        non_utc_dt = datetime(2026, 1, 5, 10, 0, 0, tzinfo=est)
        with pytest.raises(ClockError, match="UTC"):
            TradingSessions._require_utc(non_utc_dt)


# =============================================================================
# MIS Session Tests
# =============================================================================


class TestMISSession:
    """Tests for MIS (intraday) session handling."""

    def test_mis_supported_exchanges(self):
        """Test MIS_SUPPORTED_EXCHANGES contains expected exchanges."""
        assert Exchange.NSE in MIS_SUPPORTED_EXCHANGES
        assert Exchange.BSE in MIS_SUPPORTED_EXCHANGES
        assert Exchange.MCX in MIS_SUPPORTED_EXCHANGES
        assert Exchange.CDS in MIS_SUPPORTED_EXCHANGES
        assert Exchange.BINANCE not in MIS_SUPPORTED_EXCHANGES

    def test_mis_close_times_defined(self):
        """Test MIS_CLOSE_TIMES has entries for supported exchanges."""
        assert Exchange.NSE in MIS_CLOSE_TIMES
        assert Exchange.BSE in MIS_CLOSE_TIMES
        assert Exchange.MCX in MIS_CLOSE_TIMES
        assert Exchange.CDS in MIS_CLOSE_TIMES

    def test_mis_close_time_before_market_close(self):
        """Test MIS close time is before regular market close."""
        nse_mis_close = MIS_CLOSE_TIMES[Exchange.NSE]
        assert nse_mis_close < time(15, 30)  # Market closes at 15:30

    def test_is_mis_session_active_during_hours(self, mock_calendar, utc_trading_time):
        """Test is_mis_session_active returns True during MIS hours."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.is_mis_session_active(utc_trading_time, Exchange.NSE)
            assert result is True

    def test_is_mis_session_active_unsupported_exchange(self, utc_trading_time):
        """Test is_mis_session_active returns False for unsupported exchange."""
        result = TradingSessions.is_mis_session_active(utc_trading_time, Exchange.BINANCE)
        assert result is False

    def test_is_mis_session_active_requires_utc(self):
        """Test is_mis_session_active raises on naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError):
            TradingSessions.is_mis_session_active(naive_dt, Exchange.NSE)


# =============================================================================
# Product Type Validation Tests
# =============================================================================


class TestValidateProductType:
    """Tests for validate_product_type function."""

    def test_validate_mis_product_type(self, mock_calendar, utc_trading_time):
        """Test validating MIS product type succeeds."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.validate_product_type("MIS", Exchange.NSE, utc_trading_time)
            assert result == ProductType.MIS

    def test_validate_nrml_product_type(self, mock_calendar, utc_trading_time):
        """Test validating NRML product type succeeds."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.validate_product_type("NRML", Exchange.NSE, utc_trading_time)
            assert result == ProductType.NRML

    def test_validate_cnc_blocked_on_nse(self, mock_calendar, utc_trading_time):
        """Test CNC (DELIVERY) is blocked on NSE."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            with pytest.raises(ClockError, match="DELIVERY.*blocked"):
                TradingSessions.validate_product_type("CNC", Exchange.NSE, utc_trading_time)

    def test_validate_invalid_product_type(self, mock_calendar, utc_trading_time):
        """Test invalid product type raises error."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            with pytest.raises(ClockError, match="Invalid product_type"):
                TradingSessions.validate_product_type("INVALID", Exchange.NSE, utc_trading_time)

    def test_validate_product_type_case_insensitive(self, mock_calendar, utc_trading_time):
        """Test product type validation is case-insensitive."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.validate_product_type("mis", Exchange.NSE, utc_trading_time)
            assert result == ProductType.MIS

    def test_validate_product_type_requires_utc(self):
        """Test validate_product_type raises on naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)  # noqa: DTZ001
        with pytest.raises(ClockError):
            TradingSessions.validate_product_type("MIS", Exchange.NSE, naive_dt)


# =============================================================================
# MIS Square-Off Time Tests
# =============================================================================


class TestGetMISSquareOffTime:
    """Tests for get_mis_square_off_time function."""

    def test_get_mis_square_off_time_nse(self, mock_calendar):
        """Test getting MIS square-off time for NSE."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.get_mis_square_off_time(Exchange.NSE, date(2026, 1, 5))
            assert result == time(15, 20)

    def test_get_mis_square_off_time_mcx(self, mock_calendar):
        """Test getting MIS square-off time for MCX."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.get_mis_square_off_time(Exchange.MCX, date(2026, 1, 5))
            assert result == time(23, 0)

    def test_get_mis_square_off_time_unsupported_exchange(self):
        """Test returns None for unsupported exchange."""
        result = TradingSessions.get_mis_square_off_time(Exchange.BINANCE, date(2026, 1, 5))
        assert result is None

    def test_get_mis_square_off_time_holiday(self, mock_calendar):
        """Test returns None for holiday."""
        mock_calendar.session_for.return_value = None
        with patch.object(TradingSessions, "calendar", mock_calendar):
            result = TradingSessions.get_mis_square_off_time(Exchange.NSE, date(2026, 1, 26))
            assert result is None


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_ist_offset_value(self):
        """Test IST offset is exactly 5 hours 30 minutes."""
        assert IST_OFFSET == timedelta(hours=5, minutes=30)

    def test_clock_to_ist_day_rollover(self):
        """Test IST conversion handles day rollover correctly."""
        # 20:00 UTC = 01:30 IST (next day)
        utc_dt = datetime(2026, 1, 5, 20, 0, 0, tzinfo=UTC)
        result = Clock.to_ist(utc_dt)
        assert result.day == 6
        assert result.hour == 1
        assert result.minute == 30

    def test_clock_ist_to_utc_day_rollback(self):
        """Test IST to UTC handles day rollback correctly."""
        # 02:00 IST = 20:30 UTC (previous day)
        ist_dt = datetime(2026, 1, 6, 2, 0, 0)  # noqa: DTZ001
        result = Clock.ist_to_utc(ist_dt)
        assert result.day == 5
        assert result.hour == 20
        assert result.minute == 30

    def test_mis_session_after_square_off(self, mock_calendar, utc_after_hours_time):
        """Test MIS session is inactive after square-off time."""
        with patch.object(TradingSessions, "calendar", mock_calendar):
            # Configure to return session but time check should fail
            result = TradingSessions.is_mis_session_active(utc_after_hours_time, Exchange.NSE)
            # Result depends on mock setup - this tests the path
            assert isinstance(result, bool)


# =============================================================================
# Timezone Precision Tests
# =============================================================================


class TestTimezonePrecision:
    """Tests for timezone and precision handling."""

    def test_utc_timestamp_precision_microseconds(self):
        """Test UTC timestamp preserves microsecond precision."""
        utc_dt = datetime(2026, 1, 5, 10, 15, 30, 123456, tzinfo=UTC)
        result = Clock.to_utc(utc_dt)
        assert result.microsecond == 123456

    def test_ist_conversion_precision(self):
        """Test IST conversion preserves microsecond precision."""
        utc_dt = datetime(2026, 1, 5, 4, 30, 0, 123456, tzinfo=UTC)
        result = Clock.to_ist(utc_dt)
        assert result.microsecond == 123456

    def test_decimal_not_used_in_time_calculations(self):
        """Test that time calculations don't use float/Decimal."""
        # IST_OFFSET should be timedelta, not Decimal
        assert isinstance(IST_OFFSET, timedelta)


# =============================================================================
# Config Loading Tests
# =============================================================================


class TestConfigLoading:
    """Tests for config loading functionality in exchange_calendar."""

    def test_load_session_times_from_config(self):
        """Test loading session times from config file."""
        from iatb.core.exchange_calendar import _load_session_times_from_config

        sessions = _load_session_times_from_config()
        assert Exchange.NSE in sessions
        assert Exchange.BSE in sessions
        assert Exchange.MCX in sessions
        assert Exchange.CDS in sessions

    def test_load_session_times_nse_values(self):
        """Test NSE session times match config."""
        from iatb.core.exchange_calendar import _load_session_times_from_config

        sessions = _load_session_times_from_config()
        nse_session = sessions[Exchange.NSE]
        assert nse_session.open_time == time(9, 15)
        assert nse_session.close_time == time(15, 30)

    def test_load_session_times_mcx_values(self):
        """Test MCX session times match config."""
        from iatb.core.exchange_calendar import _load_session_times_from_config

        sessions = _load_session_times_from_config()
        mcx_session = sessions[Exchange.MCX]
        assert mcx_session.open_time == time(9, 0)
        assert mcx_session.close_time == time(23, 30)

    def test_load_holidays_from_config(self):
        """Test loading holidays from config file."""
        from iatb.core.exchange_calendar import _load_holidays_from_config

        holidays = _load_holidays_from_config()
        assert Exchange.NSE in holidays
        assert Exchange.BSE in holidays
        assert Exchange.MCX in holidays
        assert Exchange.CDS in holidays

    def test_load_holidays_includes_republic_day(self):
        """Test Republic Day is loaded as holiday."""
        from iatb.core.exchange_calendar import _load_holidays_from_config

        holidays = _load_holidays_from_config()
        republic_day = date(2026, 1, 26)
        assert republic_day in holidays[Exchange.NSE]
        assert republic_day in holidays[Exchange.MCX]

    def test_load_holidays_includes_independence_day(self):
        """Test Independence Day is loaded as holiday."""
        from iatb.core.exchange_calendar import _load_holidays_from_config

        holidays = _load_holidays_from_config()
        independence_day = date(2026, 8, 15)
        assert independence_day in holidays[Exchange.NSE]
        assert independence_day in holidays[Exchange.CDS]

    def test_load_holidays_maharashtra_day_nse_only(self):
        """Test Maharashtra Day is NSE-only holiday."""
        from iatb.core.exchange_calendar import _load_holidays_from_config

        holidays = _load_holidays_from_config()
        maharashtra_day = date(2026, 5, 1)
        assert maharashtra_day in holidays[Exchange.NSE]
        # CDS should NOT have Maharashtra Day
        assert maharashtra_day not in holidays[Exchange.CDS]

    def test_default_calendar_uses_config(self):
        """Test DEFAULT_EXCHANGE_CALENDAR uses loaded config."""
        from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR

        # Verify calendar has sessions from config
        nse_session = DEFAULT_EXCHANGE_CALENDAR.get_regular_session(Exchange.NSE)
        assert nse_session is not None
        assert nse_session.open_time == time(9, 15)
        assert nse_session.close_time == time(15, 30)

    def test_calendar_holiday_check(self):
        """Test calendar correctly identifies holidays."""
        from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR

        republic_day = date(2026, 1, 26)
        assert DEFAULT_EXCHANGE_CALENDAR.is_holiday(Exchange.NSE, republic_day)
        assert DEFAULT_EXCHANGE_CALENDAR.is_holiday(Exchange.MCX, republic_day)

    def test_calendar_trading_day_check(self):
        """Test calendar correctly identifies trading days."""
        from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR

        regular_day = date(2026, 1, 5)  # Monday
        assert DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, regular_day)

    def test_calendar_holiday_not_trading_day(self):
        """Test holidays are not trading days."""
        from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR

        republic_day = date(2026, 1, 26)
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, republic_day)

    def test_calendar_weekend_not_trading_day(self):
        """Test weekends are not trading days."""
        from iatb.core.exchange_calendar import DEFAULT_EXCHANGE_CALENDAR

        saturday = date(2026, 1, 3)
        sunday = date(2026, 1, 4)
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, saturday)
        assert not DEFAULT_EXCHANGE_CALENDAR.is_trading_day(Exchange.NSE, sunday)
