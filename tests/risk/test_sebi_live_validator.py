"""Tests for SEBI Live Execution Validation Harness."""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.sebi_live_validator import (
    LiveValidationReport,
    SEBILiveValidationHarness,
    SEBIMarketHours,
    ValidationSeverity,
)


def _utc_now() -> datetime:
    return datetime(2026, 4, 27, 10, 0, 0, tzinfo=UTC)


class TestSEBIMarketHours:
    def test_is_market_hours_within(self) -> None:
        mh = SEBIMarketHours(
            exchange="NSE",
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
        )
        ist_noon = datetime(2026, 4, 27, 6, 30, 0, tzinfo=UTC)
        assert mh.is_market_hours(ist_noon) is True

    def test_is_market_hours_outside(self) -> None:
        mh = SEBIMarketHours(
            exchange="NSE",
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
        )
        early_utc = datetime(2026, 4, 27, 2, 0, 0, tzinfo=UTC)
        assert mh.is_market_hours(early_utc) is False


class TestSEBILiveValidationHarness:
    def _make_harness(self) -> SEBILiveValidationHarness:
        return SEBILiveValidationHarness(
            max_order_rate_per_sec=Decimal("3"),
            max_daily_orders=1000,
            min_audit_trail_entries=1,
        )

    def test_init_validates_rate(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_order_rate_per_sec=Decimal("0"))

    def test_init_validates_daily_orders(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_daily_orders=0)

    def test_validate_order_timing_pass(self) -> None:
        harness = self._make_harness()
        ist_noon = datetime(2026, 4, 27, 6, 30, 0, tzinfo=UTC)
        result = harness.validate_order_timing("NSE", ist_noon)
        assert result.severity == ValidationSeverity.PASS

    def test_validate_order_timing_fail_outside(self) -> None:
        harness = self._make_harness()
        early = datetime(2026, 4, 27, 2, 0, 0, tzinfo=UTC)
        result = harness.validate_order_timing("NSE", early)
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_order_timing_unknown_exchange(self) -> None:
        harness = self._make_harness()
        result = harness.validate_order_timing("UNKNOWN", _utc_now())
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_order_rate_pass(self) -> None:
        harness = self._make_harness()
        result = harness.validate_order_rate(_utc_now())
        assert result.severity == ValidationSeverity.PASS

    def test_validate_order_rate_exceeded(self) -> None:
        harness = self._make_harness()
        now = _utc_now()
        for _ in range(3):
            harness.record_order(now)
        result = harness.validate_order_rate(now)
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_daily_order_limit_pass(self) -> None:
        harness = self._make_harness()
        result = harness.validate_daily_order_limit(date(2026, 4, 27))
        assert result.severity == ValidationSeverity.PASS

    def test_validate_daily_order_limit_exceeded(self) -> None:
        harness = SEBILiveValidationHarness(max_daily_orders=2)
        now = _utc_now()
        harness.record_order(now)
        harness.record_order(now)
        result = harness.validate_daily_order_limit(now.date())
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_audit_trail_pass(self) -> None:
        harness = self._make_harness()
        result = harness.validate_audit_trail(5)
        assert result.severity == ValidationSeverity.PASS

    def test_validate_audit_trail_fail(self) -> None:
        harness = self._make_harness()
        result = harness.validate_audit_trail(0)
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_static_ip_pass(self) -> None:
        harness = self._make_harness()
        result = harness.validate_static_ip("192.168.1.1", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.PASS

    def test_validate_static_ip_fail(self) -> None:
        harness = self._make_harness()
        result = harness.validate_static_ip("10.0.0.1", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_static_ip_empty(self) -> None:
        harness = self._make_harness()
        result = harness.validate_static_ip("", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_algo_id_pass(self) -> None:
        harness = self._make_harness()
        result = harness.validate_algo_id("ALGO-001")
        assert result.severity == ValidationSeverity.PASS

    def test_validate_algo_id_empty(self) -> None:
        harness = self._make_harness()
        result = harness.validate_algo_id("")
        assert result.severity == ValidationSeverity.FAIL

    def test_validate_algo_id_whitespace(self) -> None:
        harness = self._make_harness()
        result = harness.validate_algo_id("   ")
        assert result.severity == ValidationSeverity.FAIL

    def test_record_order_tracks_timestamps(self) -> None:
        harness = self._make_harness()
        now = _utc_now()
        harness.record_order(now)
        harness.record_order(now)
        result = harness.validate_order_rate(now)
        assert result.severity == ValidationSeverity.PASS

    def test_record_order_tracks_daily_count(self) -> None:
        harness = SEBILiveValidationHarness(max_daily_orders=10)
        now = _utc_now()
        harness.record_order(now)
        result = harness.validate_daily_order_limit(now.date())
        assert result.severity == ValidationSeverity.PASS

    def test_run_full_validation_all_pass(self) -> None:
        harness = self._make_harness()
        ist_noon = datetime(2026, 4, 27, 6, 30, 0, tzinfo=UTC)
        report = harness.run_full_validation(
            exchange="NSE",
            now_utc=ist_noon,
            source_ip="192.168.1.1",
            allowed_ips=("192.168.1.1",),
            algo_id="ALGO-001",
            audit_entry_count=5,
        )
        assert report.overall_pass is True
        assert report.failed_checks == 0
        assert report.total_checks == 6

    def test_run_full_validation_fails(self) -> None:
        harness = self._make_harness()
        early = datetime(2026, 4, 27, 2, 0, 0, tzinfo=UTC)
        report = harness.run_full_validation(
            exchange="NSE",
            now_utc=early,
            source_ip="10.0.0.1",
            allowed_ips=("192.168.1.1",),
            algo_id="",
            audit_entry_count=0,
        )
        assert report.overall_pass is False
        assert report.failed_checks > 0

    def test_run_full_validation_pass_rate(self) -> None:
        harness = self._make_harness()
        ist_noon = datetime(2026, 4, 27, 6, 30, 0, tzinfo=UTC)
        report = harness.run_full_validation(
            exchange="NSE",
            now_utc=ist_noon,
            source_ip="192.168.1.1",
            allowed_ips=("192.168.1.1",),
            algo_id="ALGO-001",
            audit_entry_count=5,
        )
        assert report.pass_rate == Decimal("100")

    def test_naive_datetime_rejected(self) -> None:
        harness = self._make_harness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.validate_order_timing(  # noqa: DTZ001
                "NSE",
                datetime(2026, 4, 27, 10, 0, 0),
            )

    def test_record_order_naive_datetime_rejected(self) -> None:
        harness = self._make_harness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.record_order(datetime(2026, 4, 27, 10, 0, 0))  # noqa: DTZ001


class TestLiveValidationReport:
    def test_pass_rate_zero_checks(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_utc_now(),
            results=[],
            overall_pass=True,
            total_checks=0,
            passed_checks=0,
            failed_checks=0,
            warnings=0,
        )
        assert report.pass_rate == Decimal("0")

    def test_pass_rate_calculation(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_utc_now(),
            results=[],
            overall_pass=False,
            total_checks=6,
            passed_checks=4,
            failed_checks=2,
            warnings=0,
        )
        expected = Decimal("4") / Decimal("6") * Decimal("100")
        assert report.pass_rate == expected
