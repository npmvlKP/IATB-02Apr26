"""Supplemental coverage tests for iatb.core.clock — MIS boundaries, drift, session edge cases."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.clock import (
    DEFAULT_DRIFT_THRESHOLD_SECONDS,
    DEFAULT_NTP_SERVERS,
    IST_OFFSET,
    Clock,
    ClockDriftDetector,
    ProductType,
    TradingSessions,
)
from iatb.core.enums import Exchange
from iatb.core.exceptions import ClockError


class TestClockDriftDetectorEdgeCases:
    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_negative_drift_exceeds_threshold(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now - timedelta(seconds=10)
        mock_local.return_value = utc_now
        detector = ClockDriftDetector(drift_threshold_seconds=5.0)
        drift = detector.check_drift()
        assert drift.total_seconds() < 0
        assert detector.is_drift_exceeded()

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_drift_exactly_at_threshold_not_exceeded(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now - timedelta(seconds=5.0)
        detector = ClockDriftDetector(drift_threshold_seconds=5.0)
        detector.check_drift()
        assert not detector.is_drift_exceeded()

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_multiple_sync_failures_increment(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        mock_ntp.return_value = None
        detector = ClockDriftDetector()
        detector.check_drift()
        detector.check_drift()
        detector.check_drift()
        assert detector.get_sync_status()["sync_failures"] == 3

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_auto_correction_with_negative_drift(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now - timedelta(seconds=8)
        mock_local.return_value = utc_now
        detector = ClockDriftDetector(
            enable_auto_correction=True, drift_threshold_seconds=5.0
        )
        detector.check_drift()
        assert detector.is_drift_exceeded()

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    @patch.object(ClockDriftDetector, "_get_local_time")
    def test_sync_status_after_successful_sync(
        self, mock_local: MagicMock, mock_ntp: MagicMock
    ) -> None:
        utc_now = datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC)
        mock_ntp.return_value = utc_now
        mock_local.return_value = utc_now
        detector = ClockDriftDetector()
        detector.check_drift()
        status = detector.get_sync_status()
        assert status["last_sync_utc"] is not None
        assert status["sync_count"] == 1
        assert status["sync_failures"] == 0

    @patch.object(ClockDriftDetector, "_query_ntp_time")
    def test_check_drift_failure_does_not_overwrite_drift(
        self, mock_ntp: MagicMock
    ) -> None:
        detector = ClockDriftDetector()
        detector._current_drift = timedelta(seconds=3)
        mock_ntp.return_value = None
        drift = detector.check_drift()
        assert drift == timedelta(seconds=3)

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_valid_response(self, mock_socket_cls: MagicMock) -> None:
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        import struct

        ntp_delta = 2208988800
        fake_timestamp = (
            int(datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC).timestamp()) + ntp_delta
        )
        data = struct.pack("!12I", *([0] * 10), fake_timestamp, 0)
        mock_sock.recvfrom.return_value = (data, ("server", 123))
        detector = ClockDriftDetector()
        result = detector._query_ntp_server("pool.ntp.org")
        assert result.tzinfo == UTC

    @patch("iatb.core.clock.socket.socket")
    def test_query_ntp_server_socket_timeout(self, mock_socket_cls: MagicMock) -> None:
        import socket

        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.sendto.side_effect = socket.timeout("timeout")
        detector = ClockDriftDetector()
        with pytest.raises(socket.timeout):
            detector._query_ntp_server("slow.server.org")

    def test_default_ntp_servers(self) -> None:
        assert len(DEFAULT_NTP_SERVERS) == 3

    def test_default_drift_threshold(self) -> None:
        assert DEFAULT_DRIFT_THRESHOLD_SECONDS == 5.0


class TestClockToIstEdgeCases:
    def test_midnight_utc_conversion(self) -> None:
        utc_midnight = datetime(2024, 6, 15, 0, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_midnight)
        assert ist_dt.hour == 5
        assert ist_dt.minute == 30

    def test_ist_result_is_naive(self) -> None:
        utc_dt = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)
        assert ist_dt.tzinfo is None

    def test_end_of_day_utc(self) -> None:
        utc_dt = datetime(2024, 6, 15, 23, 59, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)
        assert ist_dt.hour == 5
        assert ist_dt.minute == 29
        assert ist_dt.day == 16


class TestClockIstToUtcEdgeCases:
    def test_ist_midnight(self) -> None:
        ist_midnight = datetime(2024, 6, 15, 0, 0)
        result = Clock.ist_to_utc(ist_midnight)
        assert result.hour == 18
        assert result.minute == 30
        assert result.day == 14

    def test_result_is_utc(self) -> None:
        ist_dt = datetime(2024, 6, 15, 15, 30)
        result = Clock.ist_to_utc(ist_dt)
        assert result.tzinfo == UTC


class TestMisSessionBoundaries:
    def test_mis_nse_before_session(self) -> None:
        utc_dt = datetime(2024, 6, 14, 3, 50, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.NSE)
        assert isinstance(result, bool)

    def test_mis_nse_at_close_time(self) -> None:
        utc_at_close = datetime(2024, 6, 14, 9, 50, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_at_close, Exchange.NSE)
        assert isinstance(result, bool)

    def test_mis_mcx_extended_hours(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.MCX)
        assert isinstance(result, bool)

    def test_mis_cds_session(self) -> None:
        utc_dt = datetime(2024, 6, 14, 6, 0, tzinfo=UTC)
        result = TradingSessions.is_mis_session_active(utc_dt, Exchange.CDS)
        assert isinstance(result, bool)

    def test_non_session_exchange_returns_false_for_mis(self) -> None:
        utc_dt = datetime(2024, 6, 14, 10, 0, tzinfo=UTC)
        assert TradingSessions.is_mis_session_active(utc_dt, Exchange.BINANCE) is False


class TestValidateProductTypeEdgeCases:
    def test_nrml_on_mis_exchange_outside_session(self) -> None:
        utc_dt = datetime(2024, 6, 14, 1, 0, tzinfo=UTC)
        with pytest.raises(ClockError, match="MIS session not active"):
            TradingSessions.validate_product_type("NRML", Exchange.NSE, utc_dt)

    def test_lowercase_product_type_accepted(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("mis", Exchange.NSE, utc_dt)
        assert result == ProductType.MIS

    def test_cnc_on_non_mis_exchange_accepted(self) -> None:
        utc_dt = datetime(2024, 6, 14, 4, 30, tzinfo=UTC)
        result = TradingSessions.validate_product_type("CNC", Exchange.BINANCE, utc_dt)
        assert result == ProductType.CNC


class TestNextOpenTimeEdgeCases:
    def test_before_market_opens_same_day(self) -> None:
        utc_dt = datetime(2024, 6, 14, 3, 0, tzinfo=UTC)
        result = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        assert result.tzinfo is not None
        assert result.hour is not None

    def test_after_market_close_next_day(self) -> None:
        utc_dt = datetime(2024, 6, 14, 11, 0, tzinfo=UTC)
        result = TradingSessions.next_open_time(utc_dt, Exchange.NSE)
        assert result.tzinfo is not None

    def test_non_utc_raises(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ClockError):
            TradingSessions.next_open_time(
                datetime(2024, 6, 15, 10, 0, tzinfo=ist), Exchange.NSE
            )


class TestGetSessionTimes:
    def test_unknown_exchange_raises(self) -> None:
        with pytest.raises(ClockError, match="Unknown exchange"):
            TradingSessions._get_session_times("UNKNOWN")

    def test_nse_session_times(self) -> None:
        open_t, close_t = TradingSessions._get_session_times("NSE")
        assert isinstance(open_t, time)
        assert isinstance(close_t, time)


class TestGetMisSquareOffTimeEdgeCases:
    def test_bse_returns_time(self) -> None:
        result = TradingSessions.get_mis_square_off_time(
            Exchange.BSE, date(2024, 6, 14)
        )
        assert result == time(15, 20)

    def test_mcx_returns_time(self) -> None:
        result = TradingSessions.get_mis_square_off_time(
            Exchange.MCX, date(2024, 6, 14)
        )
        assert result == time(23, 0)


class TestIstOffsetValue:
    def test_ist_offset_is_5h30m(self) -> None:
        assert IST_OFFSET == timedelta(hours=5, minutes=30)


class TestProductTypeEnum:
    def test_product_type_members(self) -> None:
        members = list(ProductType)
        assert len(members) == 3
        assert ProductType.MIS in members
        assert ProductType.CNC in members
        assert ProductType.NRML in members

    def test_product_type_string_comparison(self) -> None:
        assert ProductType.MIS == "MIS"
        assert ProductType.CNC == "CNC"
        assert ProductType.NRML == "NRML"
