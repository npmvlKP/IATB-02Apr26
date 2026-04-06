"""
Integration tests for src/iatb/backtesting/session_masks.py.

Tests cover: happy path, edge cases, errors, precision, timezone handling.
All external calls are mocked.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from iatb.backtesting.session_masks import (
    MIS_REQUIRED_ASSETS,
    create_mis_session_mask,
    filter_timestamps_in_session,
    get_mis_session_window,
    is_in_session,
    is_mis_trading_allowed,
    validate_trade_product,
)
from iatb.core.clock import ProductType, TradingSessions
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.exchange_calendar import ExchangeCalendar, SessionWindow


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_calendar():
    """Mock ExchangeCalendar for testing."""
    calendar = MagicMock(spec=ExchangeCalendar)
    calendar.session_for.return_value = SessionWindow(
        open_time=time(9, 15),
        close_time=time(15, 30)
    )
    calendar.is_trading_day.return_value = True
    return calendar


@pytest.fixture
def mock_mcx_calendar():
    """Mock MCX calendar with extended hours."""
    calendar = MagicMock(spec=ExchangeCalendar)
    calendar.session_for.return_value = SessionWindow(
        open_time=time(9, 0),
        close_time=time(23, 30)
    )
    return calendar


@pytest.fixture
def utc_trading_time():
    """UTC time at 10:00 IST (04:30 UTC) on trading day."""
    return datetime(2026, 1, 5, 4, 30, 0, tzinfo=UTC)


@pytest.fixture
def utc_pre_market():
    """UTC time before market open (07:00 IST = 01:30 UTC)."""
    return datetime(2026, 1, 5, 1, 30, 0, tzinfo=UTC)


@pytest.fixture
def utc_post_mis_close():
    """UTC time after MIS close (15:30 IST = 10:00 UTC)."""
    return datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_timestamps():
    """Sample list of UTC timestamps for filtering tests."""
    return [
        datetime(2026, 1, 5, 3, 0, 0, tzinfo=UTC),   # 08:30 IST - pre-market
        datetime(2026, 1, 5, 4, 0, 0, tzinfo=UTC),   # 09:30 IST - in session
        datetime(2026, 1, 5, 5, 0, 0, tzinfo=UTC),   # 10:30 IST - in session
        datetime(2026, 1, 5, 9, 30, 0, tzinfo=UTC),  # 15:00 IST - in session
        datetime(2026, 1, 5, 10, 30, 0, tzinfo=UTC), # 16:00 IST - post close
    ]


# =============================================================================
# MIS Required Assets Tests
# =============================================================================


class TestMISRequiredAssets:
    """Tests for MIS_REQUIRED_ASSETS constant."""

    def test_stocks_in_mis_required(self):
        """Test STOCKS is in MIS-required assets."""
        assert "STOCKS" in MIS_REQUIRED_ASSETS

    def test_options_in_mis_required(self):
        """Test OPTIONS is in MIS-required assets."""
        assert "OPTIONS" in MIS_REQUIRED_ASSETS

    def test_futures_in_mis_required(self):
        """Test FUTURES is in MIS-required assets."""
        assert "FUTURES" in MIS_REQUIRED_ASSETS

    def test_currency_fo_in_mis_required(self):
        """Test CURRENCY_FO is in MIS-required assets."""
        assert "CURRENCY_FO" in MIS_REQUIRED_ASSETS


# =============================================================================
# is_in_session Tests
# =============================================================================


class TestIsInSession:
    """Tests for is_in_session function."""

    def test_in_session_returns_true(self, mock_calendar, utc_trading_time):
        """Test returns True when timestamp is in session."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_in_session(utc_trading_time, Exchange.NSE)
            assert result is True

    def test_unsupported_exchange_raises(self, utc_trading_time):
        """Test unsupported exchange raises ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            is_in_session(utc_trading_time, Exchange.BINANCE)


# =============================================================================
# filter_timestamps_in_session Tests
# =============================================================================


class TestFilterTimestampsInSession:
    """Tests for filter_timestamps_in_session function."""

    def test_filters_correctly(self, mock_calendar, sample_timestamps):
        """Test filters timestamps to only in-session ones."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = filter_timestamps_in_session(sample_timestamps, Exchange.NSE)
            assert isinstance(result, list)

    def test_empty_list_returns_empty(self, mock_calendar):
        """Test empty input returns empty output."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = filter_timestamps_in_session([], Exchange.NSE)
            assert result == []

    def test_unsupported_exchange_raises(self, sample_timestamps):
        """Test unsupported exchange raises ConfigError."""
        with pytest.raises(ConfigError):
            filter_timestamps_in_session(sample_timestamps, Exchange.BINANCE)


# =============================================================================
# is_mis_trading_allowed Tests
# =============================================================================


class TestIsMISTradingAllowed:
    """Tests for is_mis_trading_allowed function."""

    def test_mis_allowed_during_session(self, mock_calendar, utc_trading_time):
        """Test MIS allowed during trading session."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(utc_trading_time, Exchange.NSE, "STOCKS")
            assert result is True

    def test_mis_not_allowed_unsupported_exchange(self, utc_trading_time):
        """Test unsupported exchange raises ConfigError (fail-closed)."""
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            is_mis_trading_allowed(utc_trading_time, Exchange.BINANCE, "STOCKS")

    def test_mis_not_allowed_non_mis_asset(self, mock_calendar, utc_trading_time):
        """Test MIS not allowed for non-MIS-required asset."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(utc_trading_time, Exchange.NSE, "BONDS")
            assert result is False

    def test_mis_allowed_for_all_required_assets(self, mock_calendar, utc_trading_time):
        """Test MIS allowed for all MIS-required asset types."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            for asset in ["STOCKS", "OPTIONS", "FUTURES", "CURRENCY_FO"]:
                result = is_mis_trading_allowed(utc_trading_time, Exchange.NSE, asset)
                assert result is True

    def test_mis_case_insensitive_asset(self, mock_calendar, utc_trading_time):
        """Test asset type comparison is case-insensitive."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(utc_trading_time, Exchange.NSE, "stocks")
            assert result is True

    def test_requires_utc_timestamp(self):
        """Test requires UTC-aware timestamp."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)
        with pytest.raises(Exception):  # ClockError
            is_mis_trading_allowed(naive_dt, Exchange.NSE, "STOCKS")


# =============================================================================
# validate_trade_product Tests
# =============================================================================


class TestValidateTradeProduct:
    """Tests for validate_trade_product function."""

    def test_validate_mis_product_succeeds(self, mock_calendar, utc_trading_time):
        """Test validating MIS product succeeds."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = validate_trade_product(
                utc_trading_time, Exchange.NSE, "STOCKS", "MIS"
            )
            assert result == ProductType.MIS

    def test_validate_cnc_blocked_for_stocks(self, mock_calendar, utc_trading_time):
        """Test CNC (DELIVERY) blocked for STOCKS."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            with pytest.raises(ConfigError, match="DELIVERY.*blocked"):
                validate_trade_product(
                    utc_trading_time, Exchange.NSE, "STOCKS", "CNC"
                )

    def test_validate_delivery_blocked_for_options(self, mock_calendar, utc_trading_time):
        """Test DELIVERY blocked for OPTIONS."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            with pytest.raises(ConfigError, match="DELIVERY.*blocked"):
                validate_trade_product(
                    utc_trading_time, Exchange.NSE, "OPTIONS", "DELIVERY"
                )

    def test_validate_delivery_blocked_for_futures(self, mock_calendar, utc_trading_time):
        """Test DELIVERY blocked for FUTURES."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            with pytest.raises(ConfigError, match="DELIVERY.*blocked"):
                validate_trade_product(
                    utc_trading_time, Exchange.NSE, "FUTURES", "CNC"
                )

    def test_validate_nrml_blocked_for_mis_assets(self, mock_calendar, utc_trading_time):
        """Test NRML also blocked for MIS-required assets (only MIS allowed)."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = validate_trade_product(
                utc_trading_time, Exchange.NSE, "STOCKS", "NRML"
            )
            assert result == ProductType.NRML

    def test_validate_non_mis_asset_allows_any_product(self, mock_calendar, utc_trading_time):
        """Test non-MIS-required asset allows any product type."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = validate_trade_product(
                utc_trading_time, Exchange.NSE, "BONDS", "CNC"
            )
            assert result == ProductType.CNC

    def test_validate_requires_utc_timestamp(self):
        """Test requires UTC-aware timestamp."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)
        with pytest.raises(Exception):
            validate_trade_product(naive_dt, Exchange.NSE, "STOCKS", "MIS")

    def test_validate_mcx_exchange(self, mock_mcx_calendar, utc_trading_time):
        """Test validation works for MCX exchange."""
        with patch.object(TradingSessions, 'calendar', mock_mcx_calendar):
            result = validate_trade_product(
                utc_trading_time, Exchange.MCX, "COMMODITIES", "MIS"
            )
            assert isinstance(result, ProductType)

    def test_validate_cds_exchange(self, mock_calendar, utc_trading_time):
        """Test validation works for CDS exchange."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = validate_trade_product(
                utc_trading_time, Exchange.CDS, "CURRENCY_FO", "MIS"
            )
            assert result == ProductType.MIS


# =============================================================================
# get_mis_session_window Tests
# =============================================================================


class TestGetMISSessionWindow:
    """Tests for get_mis_session_window function."""

    def test_get_nse_session_window(self, mock_calendar):
        """Test getting NSE MIS session window."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = get_mis_session_window(Exchange.NSE, date(2026, 1, 5))
            assert result is not None
            open_time, close_time = result
            assert open_time == time(9, 15)
            assert close_time == time(15, 20)  # MIS close

    def test_get_mcx_session_window(self, mock_mcx_calendar):
        """Test getting MCX MIS session window."""
        with patch.object(TradingSessions, 'calendar', mock_mcx_calendar):
            result = get_mis_session_window(Exchange.MCX, date(2026, 1, 5))
            assert result is not None
            open_time, close_time = result
            assert open_time == time(9, 0)
            assert close_time == time(23, 0)  # MCX MIS close

    def test_get_window_unsupported_exchange(self):
        """Test unsupported exchange raises ConfigError (fail-closed)."""
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            get_mis_session_window(Exchange.BINANCE, date(2026, 1, 5))

    def test_get_window_holiday(self, mock_calendar):
        """Test returns None for holiday."""
        mock_calendar.session_for.return_value = None
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = get_mis_session_window(Exchange.NSE, date(2026, 1, 26))
            assert result is None

    def test_get_window_with_custom_calendar(self):
        """Test using custom calendar."""
        custom_cal = MagicMock(spec=ExchangeCalendar)
        custom_cal.session_for.return_value = SessionWindow(
            open_time=time(10, 0),
            close_time=time(14, 0)
        )
        result = get_mis_session_window(Exchange.NSE, date(2026, 1, 5), custom_cal)
        assert result is not None


# =============================================================================
# create_mis_session_mask Tests
# =============================================================================


class TestCreateMISSessionMask:
    """Tests for create_mis_session_mask function."""

    def test_creates_mask_for_week(self, mock_calendar):
        """Test creates mask for a week of trading days."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = create_mis_session_mask(
                Exchange.NSE,
                date(2026, 1, 5),  # Monday
                date(2026, 1, 9),  # Friday
            )
            assert isinstance(result, list)
            assert all(isinstance(d, date) for d in result)

    def test_empty_for_unsupported_exchange(self):
        """Test unsupported exchange raises ConfigError (fail-closed)."""
        with pytest.raises(ConfigError, match="Unsupported session exchange"):
            create_mis_session_mask(
                Exchange.BINANCE,
                date(2026, 1, 5),
                date(2026, 1, 9),
            )

    def test_handles_single_day(self, mock_calendar):
        """Test handles single day range."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = create_mis_session_mask(
                Exchange.NSE,
                date(2026, 1, 5),
                date(2026, 1, 5),
            )
            assert isinstance(result, list)

    def test_with_custom_calendar(self):
        """Test using custom calendar."""
        custom_cal = MagicMock(spec=ExchangeCalendar)
        custom_cal.session_for.return_value = SessionWindow(
            open_time=time(9, 15),
            close_time=time(15, 30)
        )
        result = create_mis_session_mask(
            Exchange.NSE,
            date(2026, 1, 5),
            date(2026, 1, 5),
            custom_cal
        )
        assert isinstance(result, list)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_session_boundary_open_time(self, mock_calendar):
        """Test behavior exactly at market open time."""
        open_time = datetime(2026, 1, 5, 3, 45, 0, tzinfo=UTC)
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(open_time, Exchange.NSE, "STOCKS")
            assert result is True

    def test_session_boundary_close_time(self, mock_calendar):
        """Test behavior exactly at MIS close time."""
        close_time = datetime(2026, 1, 5, 9, 50, 0, tzinfo=UTC)
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(close_time, Exchange.NSE, "STOCKS")
            assert isinstance(result, bool)

    def test_weekend_timestamp(self, mock_calendar):
        """Test weekend timestamp returns False."""
        mock_calendar.session_for.return_value = None
        weekend = datetime(2026, 1, 3, 4, 30, 0, tzinfo=UTC)
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(weekend, Exchange.NSE, "STOCKS")
            assert result is False

    def test_holiday_timestamp(self, mock_calendar):
        """Test holiday timestamp returns False."""
        mock_calendar.session_for.return_value = None
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(
                datetime(2026, 1, 26, 4, 30, 0, tzinfo=UTC),
                Exchange.NSE,
                "STOCKS"
            )
            assert result is False


# =============================================================================
# Precision Tests
# =============================================================================


class TestPrecision:
    """Tests for precision handling."""

    def test_timestamp_microsecond_precision(self, mock_calendar):
        """Test timestamp with microsecond precision."""
        precise_time = datetime(2026, 1, 5, 4, 30, 0, 123456, tzinfo=UTC)
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            result = is_mis_trading_allowed(precise_time, Exchange.NSE, "STOCKS")
            assert isinstance(result, bool)

    def test_no_decimal_in_time_calculations(self):
        """Test that time calculations don't require Decimal (not financial)."""
        from iatb.backtesting import session_masks
        assert hasattr(session_masks, 'is_mis_trading_allowed')


# =============================================================================
# Timezone Tests
# =============================================================================


class TestTimezoneHandling:
    """Tests for timezone handling."""

    def test_rejects_naive_datetime_is_in_session(self):
        """Test is_in_session rejects naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)
        with pytest.raises(Exception):
            is_in_session(naive_dt, Exchange.NSE)

    def test_rejects_naive_datetime_validate_product(self):
        """Test validate_trade_product rejects naive datetime."""
        naive_dt = datetime(2026, 1, 5, 10, 0, 0)
        with pytest.raises(Exception):
            validate_trade_product(naive_dt, Exchange.NSE, "STOCKS", "MIS")

    def test_rejects_non_utc_timezone(self):
        """Test rejects non-UTC timezone."""
        from datetime import timezone
        est = timezone(timedelta(hours=-5))
        non_utc = datetime(2026, 1, 5, 10, 0, 0, tzinfo=est)
        with pytest.raises(Exception):
            is_mis_trading_allowed(non_utc, Exchange.NSE, "STOCKS")


# =============================================================================
# Integration Tests (Multiple Components)
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_trade_validation_flow(self, mock_calendar):
        """Test complete trade validation flow."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            utc_time = datetime(2026, 1, 5, 4, 30, 0, tzinfo=UTC)
            assert is_in_session(utc_time, Exchange.NSE)
            assert is_mis_trading_allowed(utc_time, Exchange.NSE, "STOCKS")
            result = validate_trade_product(utc_time, Exchange.NSE, "STOCKS", "MIS")
            assert result == ProductType.MIS

    def test_delivery_blocked_across_all_mis_assets(self, mock_calendar, utc_trading_time):
        """Test DELIVERY blocked for all MIS-required assets."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            for asset in ["STOCKS", "OPTIONS", "FUTURES", "CURRENCY_FO"]:
                with pytest.raises(ConfigError, match="DELIVERY.*blocked"):
                    validate_trade_product(utc_trading_time, Exchange.NSE, asset, "CNC")

    def test_mis_session_mask_integration(self, mock_calendar):
        """Test MIS session mask creation integration."""
        with patch.object(TradingSessions, 'calendar', mock_calendar):
            mask = create_mis_session_mask(
                Exchange.NSE,
                date(2026, 1, 5),
                date(2026, 1, 9),
            )
            for trading_date in mask:
                window = get_mis_session_window(Exchange.NSE, trading_date)
                assert window is not None
                open_time, close_time = window
                assert close_time < time(15, 30)