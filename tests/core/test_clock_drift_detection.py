"""
Tests for clock drift detection and NTP sync.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.clock import Clock, ClockDriftDetector
from iatb.core.exceptions import ClockError


class TestClockDriftDetector:
    """Test clock drift detection."""

    def test_clock_drift_detector_initialization(self) -> None:
        """Test clock drift detector initialization."""
        detector = ClockDriftDetector(
            ntp_servers=["time.google.com"],
            drift_threshold_seconds=5.0,
            enable_auto_correction=False,
        )

        assert detector._ntp_servers == ["time.google.com"]
        assert detector._drift_threshold == timedelta(seconds=5.0)
        assert detector._enable_auto_correction is False

    def test_default_ntp_servers(self) -> None:
        """Test default NTP servers are used."""
        detector = ClockDriftDetector()

        assert len(detector._ntp_servers) > 0
        assert "pool.ntp.org" in detector._ntp_servers

    def test_default_drift_threshold(self) -> None:
        """Test default drift threshold is set."""
        detector = ClockDriftDetector()

        assert detector._drift_threshold == timedelta(seconds=5.0)

    def test_check_drift_returns_timedelta(self) -> None:
        """Test check_drift returns timedelta."""
        detector = ClockDriftDetector()

        with patch.object(detector, "_query_ntp_time", return_value=datetime.now(UTC)):
            drift = detector.check_drift()

            assert isinstance(drift, timedelta)

    def test_check_drift_updates_sync_count(self) -> None:
        """Test check_drift updates sync count."""
        detector = ClockDriftDetector()

        with patch.object(detector, "_query_ntp_time", return_value=datetime.now(UTC)):
            detector.check_drift()

            assert detector._sync_count == 1

    def test_check_drift_handles_ntp_failure(self) -> None:
        """Test check_drift handles NTP failure gracefully."""
        detector = ClockDriftDetector()

        with patch.object(detector, "_query_ntp_time", return_value=None):
            drift = detector.check_drift()

            assert detector._sync_failures == 1
            assert drift == timedelta(0)

    def test_drift_exceeds_threshold(self) -> None:
        """Test drift exceeding threshold is detected."""
        detector = ClockDriftDetector(drift_threshold_seconds=1.0)

        ntp_time = datetime.now(UTC) + timedelta(seconds=10)

        with patch.object(detector, "_query_ntp_time", return_value=ntp_time):
            drift = detector.check_drift()

            assert detector.is_drift_exceeded()
            assert drift.total_seconds() > 1.0

    def test_drift_within_threshold(self) -> None:
        """Test drift within threshold is not exceeded."""
        detector = ClockDriftDetector(drift_threshold_seconds=10.0)

        ntp_time = datetime.now(UTC) + timedelta(seconds=1)

        with patch.object(detector, "_query_ntp_time", return_value=ntp_time):
            drift = detector.check_drift()

            assert not detector.is_drift_exceeded()
            assert drift.total_seconds() < 10.0

    def test_get_sync_status(self) -> None:
        """Test get_sync_status returns correct information."""
        detector = ClockDriftDetector()

        with patch.object(detector, "_query_ntp_time", return_value=datetime.now(UTC)):
            detector.check_drift()

            status = detector.get_sync_status()

            assert "last_sync_utc" in status
            assert "current_drift_seconds" in status
            assert "sync_count" in status
            assert "sync_failures" in status
            assert "drift_threshold_seconds" in status
            assert "auto_correction_enabled" in status

    def test_get_sync_status_before_sync(self) -> None:
        """Test get_sync_status before any sync."""
        detector = ClockDriftDetector()

        status = detector.get_sync_status()

        assert status["last_sync_utc"] is None
        assert status["sync_count"] == 0

    def test_query_ntp_time_fallback_to_next_server(self) -> None:
        """Test NTP query falls back to next server on failure."""
        detector = ClockDriftDetector(ntp_servers=["server1.example.com", "server2.example.com"])

        def mock_query_server(server: str) -> datetime:
            if server == "server1.example.com":
                raise Exception("Server 1 failed")
            return datetime.now(UTC)

        with patch.object(detector, "_query_ntp_server", side_effect=mock_query_server):
            result = detector._query_ntp_time()

            assert result is not None

    def test_query_ntp_time_all_servers_fail(self) -> None:
        """Test NTP query returns None when all servers fail."""
        detector = ClockDriftDetector(ntp_servers=["server1.example.com", "server2.example.com"])

        def mock_query_server(server: str) -> datetime:
            raise Exception("Server failed")

        with patch.object(detector, "_query_ntp_server", side_effect=mock_query_server):
            result = detector._query_ntp_time()

            assert result is None

    def test_query_ntp_server_invalid_response(self) -> None:
        """Test NTP server with invalid response raises error."""
        detector = ClockDriftDetector()

        with patch("socket.socket") as mock_socket:
            mock_client = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_client
            mock_client.recvfrom.return_value = (b"\x00" * 10, ("server", 123))

            with pytest.raises((ClockError, ValueError)):
                detector._query_ntp_server("server.example.com")

    def test_auto_correction_disabled_by_default(self) -> None:
        """Test auto correction is disabled by default."""
        detector = ClockDriftDetector()

        assert detector._enable_auto_correction is False

    def test_auto_correction_enabled(self) -> None:
        """Test auto correction can be enabled."""
        detector = ClockDriftDetector(enable_auto_correction=True)

        assert detector._enable_auto_correction is True

    def test_correct_drift_logs_correction(self) -> None:
        """Test correct drift logs correction."""
        detector = ClockDriftDetector(enable_auto_correction=True)

        with patch("iatb.core.clock.logger") as mock_logger:
            detector._correct_drift(timedelta(seconds=5))

            mock_logger.info.assert_called_once()

    def test_negative_drift_detected(self) -> None:
        """Test negative drift (local clock ahead) is detected."""
        detector = ClockDriftDetector(drift_threshold_seconds=1.0)

        ntp_time = datetime.now(UTC) - timedelta(seconds=10)

        with patch.object(detector, "_query_ntp_time", return_value=ntp_time):
            drift = detector.check_drift()

            assert detector.is_drift_exceeded()
            assert drift.total_seconds() < -1.0

    def test_zero_drift(self) -> None:
        """Test zero drift is not exceeded."""
        detector = ClockDriftDetector(drift_threshold_seconds=1.0)

        local_time = datetime.now(UTC)

        with patch.object(detector, "_query_ntp_time", return_value=local_time):
            drift = detector.check_drift()

            assert not detector.is_drift_exceeded()
            assert drift.total_seconds() == 0.0


class TestClockIntegration:
    """Test Clock integration with drift detector."""

    def test_set_drift_detector(self) -> None:
        """Test setting drift detector on Clock."""
        detector = ClockDriftDetector()

        Clock.set_drift_detector(detector)

        assert Clock.get_drift_detector() is detector

    def test_get_drift_detector_none_by_default(self) -> None:
        """Test get_drift_detector returns None by default."""
        detector = Clock.get_drift_detector()

        assert detector is None

    def test_clock_now_returns_utc_timestamp(self) -> None:
        """Test Clock.now returns UTC timestamp."""
        timestamp = Clock.now()

        assert timestamp.tzinfo == UTC
        assert isinstance(timestamp, datetime)

    def test_clock_to_utc_with_naive_datetime(self) -> None:
        """Test Clock.to_utc with naive datetime."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        timestamp = Clock.to_utc(dt)

        assert timestamp.tzinfo == UTC

    def test_clock_to_utc_with_aware_datetime(self) -> None:
        """Test Clock.to_utc with aware datetime."""
        from datetime import timezone

        tz = timezone(timedelta(hours=5, minutes=30))
        dt = datetime(2024, 1, 1, 17, 30, 0, tzinfo=tz)
        timestamp = Clock.to_utc(dt)

        assert timestamp.tzinfo == UTC
        assert timestamp.hour == 12

    def test_clock_to_ist(self) -> None:
        """Test Clock.to_ist converts UTC to IST."""
        utc_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ist_dt = Clock.to_ist(utc_dt)

        assert ist_dt.tzinfo is None
        assert ist_dt.hour == 17
        assert ist_dt.minute == 30

    def test_clock_ist_to_utc(self) -> None:
        """Test Clock.ist_to_utc converts IST to UTC."""
        ist_dt = datetime(2024, 1, 1, 17, 30, 0)  # noqa: DTZ001
        timestamp = Clock.ist_to_utc(ist_dt)

        assert timestamp.tzinfo == UTC
        assert timestamp.hour == 12
