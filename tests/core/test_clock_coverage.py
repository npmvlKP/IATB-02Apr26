"""Coverage tests for iatb.core.clock — UTC clock, IST conversion, drift detection."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time
from iatb.core.clock import (
    IST_OFFSET,
    MIS_CLOSE_TIMES,
    MIS_SUPPORTED_EXCHANGES,
    Clock,
    ClockDriftDetector,
    ProductType,
    TradingSessions,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError


class TestClockNow:
    def test_now_returns_utc_aware_timestamp(self) -> None:
        ts = Clock.now()
        assert ts.tzinfo is not None

    def test_now_returns_utc_timezone(self) -> None:
        ts = Clock.now()
        assert ts.tzinfo == UTC


class TestClockToUtc:
    def test_naive_datetime_gets_utc_assigned(self) -> None:
        naive = datetime(2024, 6, 15, 10, 30)
        result = Clock.to_utc(naive)
        assert result.tzinfo == UTC

    def test_non_utc_datetime_converted(self) -> None:
        from datetime import timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        ist_dt = datetime(2024, 6, 15, 10, 30, tzinfo=ist)
        result = Clock.to_utc(ist_dt)
        assert result.tzinfo == UTC
        assert result.hour == 5

    def test_utc_datetime_passes_through(self) -> None:
        utc_dt = datetime(2024, 6, 15, 10, 30, tzinfo=UTC)
        result = Clock.to_utc(utc_dt)
        assert result == utc_dt


class TestClockToIst:
    def test_utc_to_ist_conversion(self) -> None:
        utc_dt = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)
        assert ist_dt.hour == 15
        assert ist_dt.minute == 30

    def test_raises_on_naive_datetime(self) -> None:
        with pytest.raises(ClockError, match="timezone-aware"):
            Clock.to_ist(datetime(2024, 6, 15, 10, 0))


class TestClockIstToUtc:
    def test_ist_naive_to_utc(self) -> None:
        ist_naive = datetime(2024, 6, 15, 15, 30)
        result = Clock.ist_to_utc(ist_naive)
        assert result.tzinfo == UTC
        assert result.hour == 10
        assert result.minute == 0

    def test_raises_on_tz_aware_input(self) -> None:
        with pytest.raises(ClockError, match="naive"):
            Clock.ist_to_utc(datetime(2024, 6, 15, 15, 30, tzinfo=UTC))


class TestClockDriftDetector:
    def test_init_defaults(self) -> None:
        detector = ClockDriftDetector()
        status = detector.get_sync_status()
        assert status["sync_count"] == 0
        assert status["sync_failures"] == 0
        assert status["auto_correction_enabled"] is False

    def test_init_custom_servers(self) -> None:
        detector = ClockDriftDetector(ntp_servers=["custom.ntp.org"])
        assert detector._ntp_servers == ["custom.ntp.org"]

    def test_init_auto_correction(self) -> None:
        detector = ClockDriftDetector(enable_auto_correction=True)
        status = detector.get_sync_status()
        assert status["auto_correction_enabled"] is True

    @patch.object(ClockDriftDetector, "_query_ntp_time", return_value=None)
    def test_check_drift_ntp_failure_returns_current_drift(
        self, mock_ntp: MagicMock
    ) -> None:
        detector = ClockDriftDetector()
        drift = detector.check_drift()
        assert drift == timedelta(0)
        assert detector.get_sync_status()["sync_failures"] == 1

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_check_drift_within_threshold(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now
        detector = ClockDriftDetector(drift_threshold_seconds=5.0)
        drift = detector.check_drift()
        assert abs(drift) < timedelta(seconds=5)

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_check_drift_exceeds_threshold(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=10)
        detector = ClockDriftDetector(drift_threshold_seconds=5.0)
        drift = detector.check_drift()
        assert abs(drift) > timedelta(seconds=5)
        assert detector.is_drift_exceeded()

    def test_is_drift_exceeded_initially_false(self) -> None:
        detector = ClockDriftDetector()
        assert not detector.is_drift_exceeded()

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_sync_count_increments(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now
        detector = ClockDriftDetector()
        detector.check_drift()
        assert detector.get_sync_status()["sync_count"] == 1

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_invalid_response(
        self, mock_socket_cls: MagicMock
    ) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.recvfrom.return_value = (b"short", ("server", 123))
        detector = ClockDriftDetector()
        with pytest.raises(ClockError, match="Invalid NTP"):
            detector._query_ntp_server("pool.ntp.org")

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_socket_error(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.sendto.side_effect = OSError("network error")
        detector = ClockDriftDetector()
        with pytest.raises(OSError):
            detector._query_ntp_server("bad.server.org")

    def test_get_sync_status_with_no_sync(self) -> None:
        detector = ClockDriftDetector()
        status = detector.get_sync_status()
        assert status["last_sync_utc"] is None
        assert status["current_drift_seconds"] == 0.0

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_correct_drift_with_auto_correction(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=10)
        detector = ClockDriftDetector(enable_auto_correction=True)
        detector.check_drift()


class TestClockDriftDetectorSetGet:
    def test_set_and_get_drift_detector(self) -> None:
        detector = ClockDriftDetector()
        Clock.set_drift_detector(detector)
        assert Clock.get_drift_detector() is detector
        Clock._drift_detector = None

    def test_get_drift_detector_none_initially(self) -> None:
        Clock._drift_detector = None
        assert Clock.get_drift_detector() is None


class TestProductType:
    def test_mis_value(self) -> None:
        assert ProductType.MIS == "MIS"

    def test_cnc_value(self) -> None:
        assert ProductType.CNC == "CNC"

    def test_nrml_value(self) -> None:
        assert ProductType.NRML == "NRML"


class TestMisSupportedExchanges:
    def test_nse_supported(self) -> None:
        assert Exchange.NSE in MIS_SUPPORTED_EXCHANGES

    def test_bse_supported(self) -> None:
        assert Exchange.BSE in MIS_SUPPORTED_EXCHANGES

    def test_binance_not_supported(self) -> None:
        assert Exchange.BINANCE not in MIS_SUPPORTED_EXCHANGES


class TestMisCloseTimes:
    def test_nse_close_time(self) -> None:
        assert MIS_CLOSE_TIMES[Exchange.NSE] == time(15, 20)

    def test_mcx_close_time(self) -> None:
        assert MIS_CLOSE_TIMES[Exchange.MCX] == time(23, 0)

    def test_cds_close_time(self) -> None:
        assert MIS_CLOSE_TIMES[Exchange.CDS] == time(16, 30)


class TestTradingSessionsRequireUtc:
    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError, match="timezone-aware"):
            TradingSessions._require_utc(datetime(2024, 6, 15, 10, 0))

    def test_raises_on_non_utc(self) -> None:
        from datetime import timezone

        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ClockError, match="UTC"):
            TradingSessions._require_utc(datetime(2024, 6, 15, 10, 0, tzinfo=ist))

    def test_passes_on_utc(self) -> None:
        TradingSessions._require_utc(datetime(2024, 6, 15, 10, 0, tzinfo=UTC))


class TestTradingSessionsIsMarketOpen:
    @freeze_time("2024-06-14T04:00:00Z")  # Changed date to match utc_dt
    def test_nse_open_during_session(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)  # Fixed syntax error
        result = TradingSessions.is_market_open(utc_dt, Exchange.NSE)
        assert isinstance(result, bool)

    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError):
            TradingSessions.is_market_open(datetime(2024, 6, 15, 10, 0), Exchange.NSE)

    def test_returns_false_for_non_session_exchange(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_market_open(utc_dt, Exchange.BINANCE) is False


class TestTradingSessionsIsTradingDay:
    def test_weekday_is_trading_day(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_trading_day(utc_dt, Exchange.NSE) is True

    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError):
            TradingSessions.is_trading_day(datetime(2024, 6, 15), Exchange.NSE)

    def test_non_session_exchange_returns_false(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_trading_day(utc_dt, Exchange.BINANCE) is False


class TestTradingSessionsNextOpenTime:
    def test_returns_timestamp(self) -> None:
        utc_dt = datetime(2024, 6, 14, 3, 0, tzinfo=UTC)
        result = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        assert result.tzinfo is not None

    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError):
            TradingSessions.next_open_time(datetime(2024, 6, 15), Exchange.NSE)

    def test_raises_for_non_session_exchange(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        with pytest.raises(ClockError, match="No trading session"):
            TradingSessions.next_open_time(utc_dt, Exchange.BINANCE)


class TestTradingSessionsIsMisSessionActive:
    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError):
            TradingSessions.is_mis_session_active(datetime(2024, 6, 15), Exchange.NSE)

    def test_non_mis_exchange_returns_false(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_mis_session_active(utc_dt, Exchange.BINANCE) is False

    def test_nse_mis_during_session(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.NSE)
        assert isinstance(result, bool)


class TestTradingSessionsValidateProductType:
    def test_valid_mis(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("MIS", Exchange.NSE, utc_dt)
        assert result == ProductType.MIS

    def test_invalid_product_type(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        with pytest.raises(ClockError, match="Invalid product_type"):
            TradingSessions.validate_product_type("INVALID", Exchange.NSE, utc_dt)

    def test_cnc_blocked_on_mis_exchange(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        with pytest.raises(ClockError, match="DELIVERY"):
            TradingSessions.validate_product_type("CNC", Exchange.NSE, utc_dt)

    def test_raises_on_naive(self) -> None:
        with pytest.raises(ClockError):
            TradingSessions.validate_product_type(
                "MIS", Exchange.NSE, datetime(2024, 6, 15)
            )

    def test_nrml_on_non_mis_exchange(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("NRML", Exchange.BINANCE, utc_dt)
        assert result == ProductType.NRML


class TestTradingSessionsGetMisSquareOffTime:
    def test_nse_returns_time(self) -> None:
        result = TradingSessions.get_mis_square_off_time(
            Exchange.NSE, date(2024, 6, 14)
        )
        assert result == time(15, 20)

    def test_non_mis_exchange_returns_none(self) -> None:
        result = TradingSessions.get_mis_square_off_time(
            Exchange.BINANCE, date(2024, 6, 14)
        )
        assert result is None

    def test_holiday_returns_none(self) -> None:
        result = TradingSessions.get_mis_square_off_time(
            Exchange.NSE, date(2026, 1, 26)
        )
        assert result is None


class TestIstOffset:
    def test_ist_offset_value(self) -> None:
        assert IST_OFFSET == timedelta(hours=5, minutes=30)


class TestClockToIstEdgeCases:
    def test_midnight_utc_converts(self) -> None:
        utc_midnight = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_midnight)
        assert ist_dt.hour == 5
        assert ist_dt.minute == 30

    def test_preserves_date_crossing_midnight(self) -> None:
        utc_dt = datetime(2024, 6, 14, 23, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)
        assert ist_dt.hour == 4
        assert ist_dt.minute == 30
        assert ist_dt.day == 15


class TestClockIstToUtcEdgeCases:
    def test_midnight_ist_converts(self) -> None:
        ist_midnight = datetime(2024, 6, 15, 0, 0)
        result = Clock.ist_to_utc(ist_midnight)
        assert result.hour == 18
        assert result.minute == 30
        assert result.day == 14


class TestClockDriftDetectorSocketError:
    @patch.object(ClockDriftDetector, "_query_ntp_time")
    def test_check_drift_catches_socket_error(self, mock_ntp: MagicMock) -> None:
        mock_ntp.side_effect = OSError("socket error")
        detector = ClockDriftDetector()
        with pytest.raises(OSError, match="socket error"):
            detector.check_drift()

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_check_drift_logs_warning_on_excessive_drift(
        self,
        mock_local: MagicMock,
        mock_ntp: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=10)
        detector = ClockDriftDetector(drift_threshold_seconds=5.0)
        with caplog.at_level(logging.WARNING):
            detector.check_drift()
        assert any("Clock drift detected" in r.message for r in caplog.records)

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    def test_check_drift_ntp_failure_logs_warning(
        self, mock_ntp: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_ntp.return_value = None
        detector = ClockDriftDetector()
        with caplog.at_level(logging.WARNING):
            detector.check_drift()
        assert any("NTP sync failed" in r.message for r in caplog.records)

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_check_drift_auto_correction_calls_correct_drift(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=10)
        detector = ClockDriftDetector(enable_auto_correction=True)
        with patch.object(detector, "_correct_drift") as mock_correct:
            detector.check_drift()
            mock_correct.assert_called_once()

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_timeout_error(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.sendto.side_effect = TimeoutError("ntp timeout")
        detector = ClockDriftDetector()
        result = detector._query_ntp_time()
        assert result is None

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_valid_response(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        import struct

        ntp_delta = 2208988800
        test_timestamp = datetime(2024, 6, 14, 10, 0, 0, tzinfo=UTC).timestamp()
        integer_part = int(test_timestamp)
        fraction = int((test_timestamp - integer_part) * (2**32))
        ntp_transmit = integer_part + ntp_delta
        data = struct.pack("!12I", *([0] * 10 + [int(ntp_transmit), fraction]))
        mock_sock.recvfrom.return_value = (data, ("pool.ntp.org", 123))
        detector = ClockDriftDetector()
        result = detector._query_ntp_server("pool.ntp.org")
        assert result is not None
        assert result.tzinfo == UTC
        assert result.year == 2024


class TestTradingSessionsMisSessionActiveEdgeCases:
    def test_mis_session_active_during_nse_hours(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.NSE)
        assert result is True

    def test_mis_session_inactive_after_close(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 5, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.NSE)
        assert result is False

    def test_mis_session_mcx_during_hours(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.MCX)
        assert isinstance(result, bool)

    def test_mis_session_cds_during_hours(self) -> None:
        utc_dt = datetime(2024, 6, 14, 6, 0, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.CDS)
        assert isinstance(result, bool)

    def test_mis_session_non_trading_day(self) -> None:
        utc_dt = datetime(2024, 6, 16, 4, 30, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.NSE)
        assert result is False


class TestTradingSessionsIsTradingDayEdgeCases:
    def test_saturday_not_trading_day(self) -> None:
        utc_dt = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_trading_day(utc_dt, Exchange.NSE) is False

    def test_sunday_not_trading_day(self) -> None:
        utc_dt = datetime(2024, 6, 16, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_trading_day(utc_dt, Exchange.NSE) is False


class TestTradingSessionsNextOpenTimeEdgeCases:
    def test_next_open_time_before_open(self) -> None:
        utc_dt = datetime(2024, 6, 14, 3, 0, tzinfo=UTC)
        result = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        assert result.tzinfo is not None
        assert isinstance(result, datetime)

    def test_next_open_time_after_close_same_day(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        result = TradingSessions.next_open_time(utc_dt, Exchange.BSE)
        assert result.tzinfo is not None


class TestTradingSessionsValidateProductTypeEdgeCases:
    def test_mis_not_active_raises(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 5, tzinfo=UTC)
        with pytest.raises(ClockError, match="MIS session not active"):
            TradingSessions.validate_product_type("MIS", Exchange.NSE, utc_dt)

    def test_nrml_on_mis_exchange_when_mis_active(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("NRML", Exchange.NSE, utc_dt)
        assert result == ProductType.NRML

    def test_mis_on_binance_returns_false(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.BINANCE)
        assert result is False

    def test_validate_cnc_on_binance_not_blocked(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("NRML", Exchange.BINANCE, utc_dt)
        assert result == ProductType.NRML


class TestClockDriftDetectorCorrectDrift:
    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_correct_drift_logs(
        self,
        mock_local: MagicMock,
        mock_ntp: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=10)
        detector = ClockDriftDetector(enable_auto_correction=True)
        with caplog.at_level(logging.INFO):
            detector.check_drift()
        assert any("Clock drift correction" in r.message for r in caplog.records)


class TestClockDriftDetectorGetSyncStatusWithSync:
    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_sync_status_after_check(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now
        detector = ClockDriftDetector()
        detector.check_drift()
        status = detector.get_sync_status()
        assert status["last_sync_utc"] is not None
        assert status["current_drift_seconds"] == 0.0
