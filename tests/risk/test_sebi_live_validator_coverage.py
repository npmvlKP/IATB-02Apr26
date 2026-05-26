"""Comprehensive coverage tests for iatb.risk.sebi_live_validator."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.sebi_live_validator import (
    LiveValidationReport,
    SEBILiveValidationHarness,
    SEBIMarketHours,
    ValidationResult,
    ValidationSeverity,
    _validate_utc,
)

_NOW = datetime(2026, 5, 25, 6, 0, tzinfo=UTC)


class TestValidationSeverity:
    def test_values(self) -> None:
        assert ValidationSeverity.PASS.value == "PASS"
        assert ValidationSeverity.WARNING.value == "WARNING"
        assert ValidationSeverity.FAIL.value == "FAIL"


class TestValidationResult:
    def test_fields(self) -> None:
        vr = ValidationResult(
            rule_id="SEBI-001",
            rule_name="Test Rule",
            severity=ValidationSeverity.PASS,
            message="passed",
        )
        assert vr.rule_id == "SEBI-001"
        assert vr.severity == ValidationSeverity.PASS

    def test_frozen(self) -> None:
        vr = ValidationResult(
            rule_id="SEBI-001",
            rule_name="Test",
            severity=ValidationSeverity.PASS,
            message="ok",
        )
        with pytest.raises(AttributeError):
            vr.rule_id = "other"

    def test_default_details(self) -> None:
        vr = ValidationResult(
            rule_id="SEBI-001",
            rule_name="Test",
            severity=ValidationSeverity.PASS,
            message="ok",
        )
        assert vr.details == {}


class TestLiveValidationReportPassRate:
    def test_full_pass_rate(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_NOW,
            results=[],
            overall_pass=True,
            total_checks=10,
            passed_checks=10,
            failed_checks=0,
            warnings=0,
        )
        assert report.pass_rate == Decimal("100")

    def test_zero_checks(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_NOW,
            results=[],
            overall_pass=True,
            total_checks=0,
            passed_checks=0,
            failed_checks=0,
            warnings=0,
        )
        assert report.pass_rate == Decimal("0")

    def test_partial_pass_rate(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_NOW,
            results=[],
            overall_pass=False,
            total_checks=10,
            passed_checks=8,
            failed_checks=2,
            warnings=0,
        )
        assert report.pass_rate == Decimal("80")

    def test_frozen(self) -> None:
        report = LiveValidationReport(
            timestamp_utc=_NOW,
            results=[],
            overall_pass=True,
            total_checks=1,
            passed_checks=1,
            failed_checks=0,
            warnings=0,
        )
        with pytest.raises(AttributeError):
            report.total_checks = 5


class TestSEBIMarketHours:
    def test_is_market_hours_during_session(self) -> None:
        mh = SEBIMarketHours(
            exchange="NSE",
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
        )
        during = datetime(2026, 5, 25, 5, 0, tzinfo=UTC)
        assert mh.is_market_hours(during) is True

    def test_is_market_hours_before_session(self) -> None:
        mh = SEBIMarketHours(
            exchange="NSE",
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
        )
        before = datetime(2026, 5, 25, 3, 0, tzinfo=UTC)
        assert mh.is_market_hours(before) is False

    def test_is_market_hours_after_session(self) -> None:
        mh = SEBIMarketHours(
            exchange="NSE",
            market_open=time(9, 15),
            market_close=time(15, 30),
            pre_open_start=time(9, 0),
        )
        after = datetime(2026, 5, 25, 11, 0, tzinfo=UTC)
        assert mh.is_market_hours(after) is False


class TestSEBILiveValidationHarnessInit:
    def test_valid_defaults(self) -> None:
        harness = SEBILiveValidationHarness()
        assert harness._max_order_rate == Decimal("10")

    def test_custom_params(self) -> None:
        harness = SEBILiveValidationHarness(
            max_order_rate_per_sec=Decimal("5"),
            max_daily_orders=500,
            min_audit_trail_entries=10,
        )
        assert harness._max_order_rate == Decimal("5")

    def test_zero_order_rate_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_order_rate_per_sec=Decimal("0"))

    def test_negative_order_rate_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_order_rate_per_sec=Decimal("-1"))

    def test_zero_daily_orders_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_daily_orders=0)

    def test_negative_daily_orders_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            SEBILiveValidationHarness(max_daily_orders=-1)


class TestValidateOrderTiming:
    def test_during_market_hours_passes(self) -> None:
        harness = SEBILiveValidationHarness()
        during_nse = datetime(2026, 5, 25, 5, 0, tzinfo=UTC)
        result = harness.validate_order_timing("NSE", during_nse)
        assert result.severity == ValidationSeverity.PASS

    def test_outside_market_hours_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        after_nse = datetime(2026, 5, 25, 11, 0, tzinfo=UTC)
        result = harness.validate_order_timing("NSE", after_nse)
        assert result.severity == ValidationSeverity.FAIL

    def test_unknown_exchange_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_order_timing("UNKNOWN", _NOW)
        assert result.severity == ValidationSeverity.FAIL

    def test_naive_datetime_raises(self) -> None:
        harness = SEBILiveValidationHarness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.validate_order_timing("NSE", datetime(2026, 5, 25, 10, 0))


class TestValidateOrderRate:
    def test_within_rate_passes(self) -> None:
        harness = SEBILiveValidationHarness(max_order_rate_per_sec=Decimal("10"))
        result = harness.validate_order_rate(_NOW)
        assert result.severity == ValidationSeverity.PASS

    def test_exceeding_rate_fails(self) -> None:
        harness = SEBILiveValidationHarness(max_order_rate_per_sec=Decimal("3"))
        for _ in range(3):
            harness.record_order(_NOW)
        result = harness.validate_order_rate(_NOW)
        assert result.severity == ValidationSeverity.FAIL

    def test_naive_datetime_raises(self) -> None:
        harness = SEBILiveValidationHarness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.validate_order_rate(datetime(2026, 5, 25, 10, 0))


class TestValidateDailyOrderLimit:
    def test_within_limit_passes(self) -> None:
        harness = SEBILiveValidationHarness(max_daily_orders=1000)
        result = harness.validate_daily_order_limit(date(2026, 5, 25))
        assert result.severity == ValidationSeverity.PASS

    def test_exceeding_limit_fails(self) -> None:
        harness = SEBILiveValidationHarness(max_daily_orders=2)
        harness.record_order(_NOW)
        harness.record_order(_NOW)
        result = harness.validate_daily_order_limit(_NOW.date())
        assert result.severity == ValidationSeverity.FAIL


class TestValidateAuditTrail:
    def test_sufficient_entries_passes(self) -> None:
        harness = SEBILiveValidationHarness(min_audit_trail_entries=5)
        result = harness.validate_audit_trail(10)
        assert result.severity == ValidationSeverity.PASS

    def test_insufficient_entries_fails(self) -> None:
        harness = SEBILiveValidationHarness(min_audit_trail_entries=10)
        result = harness.validate_audit_trail(3)
        assert result.severity == ValidationSeverity.FAIL

    def test_exact_entries_passes(self) -> None:
        harness = SEBILiveValidationHarness(min_audit_trail_entries=5)
        result = harness.validate_audit_trail(5)
        assert result.severity == ValidationSeverity.PASS


class TestValidateStaticIp:
    def test_allowed_ip_passes(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_static_ip("192.168.1.1", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.PASS

    def test_disallowed_ip_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_static_ip("1.2.3.4", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.FAIL

    def test_empty_ip_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_static_ip("", ("192.168.1.1",))
        assert result.severity == ValidationSeverity.FAIL


class TestValidateAlgoId:
    def test_valid_algo_id_passes(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_algo_id("ALGO-001")
        assert result.severity == ValidationSeverity.PASS

    def test_empty_algo_id_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_algo_id("")
        assert result.severity == ValidationSeverity.FAIL

    def test_whitespace_algo_id_fails(self) -> None:
        harness = SEBILiveValidationHarness()
        result = harness.validate_algo_id("  ")
        assert result.severity == ValidationSeverity.FAIL


class TestRecordOrder:
    def test_records_timestamp(self) -> None:
        harness = SEBILiveValidationHarness()
        harness.record_order(_NOW)
        assert len(harness._order_timestamps) == 1

    def test_increments_daily_count(self) -> None:
        harness = SEBILiveValidationHarness()
        harness.record_order(_NOW)
        assert harness._daily_order_count[_NOW.date()] == 1

    def test_naive_raises(self) -> None:
        harness = SEBILiveValidationHarness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.record_order(datetime(2026, 5, 25, 10, 0))

    def test_prunes_old_timestamps(self) -> None:
        harness = SEBILiveValidationHarness()
        old = _NOW - timedelta(minutes=10)
        harness.record_order(old)
        harness.record_order(_NOW)
        assert len(harness._order_timestamps) == 1


class TestRunFullValidation:
    def test_all_pass(self) -> None:
        harness = SEBILiveValidationHarness()
        during_nse = datetime(2026, 5, 25, 5, 0, tzinfo=UTC)
        report = harness.run_full_validation(
            exchange="NSE",
            now_utc=during_nse,
            source_ip="192.168.1.1",
            allowed_ips=("192.168.1.1",),
            algo_id="ALGO-001",
            audit_entry_count=10,
        )
        assert report.overall_pass is True
        assert report.failed_checks == 0

    def test_some_fail(self) -> None:
        harness = SEBILiveValidationHarness()
        after_nse = datetime(2026, 5, 25, 11, 0, tzinfo=UTC)
        report = harness.run_full_validation(
            exchange="NSE",
            now_utc=after_nse,
            source_ip="1.2.3.4",
            allowed_ips=("192.168.1.1",),
            algo_id="",
            audit_entry_count=0,
        )
        assert report.overall_pass is False
        assert report.failed_checks > 0

    def test_naive_raises(self) -> None:
        harness = SEBILiveValidationHarness()
        with pytest.raises(ConfigError, match="UTC"):
            harness.run_full_validation(
                exchange="NSE",
                now_utc=datetime(2026, 5, 25, 10, 0),
                source_ip="192.168.1.1",
                allowed_ips=("192.168.1.1",),
                algo_id="ALGO-001",
                audit_entry_count=10,
            )


class TestValidateUtc:
    def test_utc_passes(self) -> None:
        _validate_utc(_NOW)

    def test_naive_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 5, 25, 10, 0))
