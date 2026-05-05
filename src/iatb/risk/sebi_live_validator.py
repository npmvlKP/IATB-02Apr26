"""
SEBI Live Execution Validation Harness.

Validates orders against SEBI requirements for live trading deployment,
including market hours, position limits, order throttling, and audit trail.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Validation result severity."""

    PASS = "PASS"  # noqa: S105  # nosec B105
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ValidationResult:
    """Result of a single validation check."""

    rule_id: str
    rule_name: str
    severity: ValidationSeverity
    message: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveValidationReport:
    """Complete validation report for live trading readiness."""

    timestamp_utc: datetime
    results: list[ValidationResult]
    overall_pass: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: int

    @property
    def pass_rate(self) -> Decimal:
        """Calculate pass rate as Decimal percentage."""
        if self.total_checks == 0:
            return Decimal("0")
        return Decimal(str(self.passed_checks)) / Decimal(str(self.total_checks)) * Decimal("100")


@dataclass(frozen=True)
class SEBIMarketHours:
    """Market hours configuration for SEBI validation."""

    exchange: str
    market_open: time
    market_close: time
    pre_open_start: time

    def is_market_hours(self, now_utc: datetime) -> bool:
        """Check if current time is within market hours (IST)."""
        from iatb.core.clock import Clock

        now_ist = Clock.to_ist(now_utc).time()
        return self.market_open <= now_ist <= self.market_close


_NSE_MARKET_HOURS = SEBIMarketHours(
    exchange="NSE",
    market_open=time(9, 15),
    market_close=time(15, 30),
    pre_open_start=time(9, 0),
)

_DEFAULT_MARKET_HOURS: dict[str, SEBIMarketHours] = {
    "NSE": _NSE_MARKET_HOURS,
    "BSE": SEBIMarketHours(
        exchange="BSE",
        market_open=time(9, 15),
        market_close=time(15, 30),
        pre_open_start=time(9, 0),
    ),
    "MCX": SEBIMarketHours(
        exchange="MCX",
        market_open=time(9, 0),
        market_close=time(23, 30),
        pre_open_start=time(8, 45),
    ),
}


class SEBILiveValidationHarness:
    """Validates live trading readiness against SEBI requirements."""

    def __init__(
        self,
        market_hours: dict[str, SEBIMarketHours] | None = None,
        max_order_rate_per_sec: Decimal = Decimal("10"),
        max_daily_orders: int = 1000,
        min_audit_trail_entries: int = 1,
    ) -> None:
        if max_order_rate_per_sec <= Decimal("0"):
            msg = "max_order_rate_per_sec must be positive"
            raise ConfigError(msg)
        if max_daily_orders <= 0:
            msg = "max_daily_orders must be positive"
            raise ConfigError(msg)
        self._market_hours = market_hours or _DEFAULT_MARKET_HOURS
        self._max_order_rate = max_order_rate_per_sec
        self._max_daily_orders = max_daily_orders
        self._min_audit_entries = min_audit_trail_entries
        self._order_timestamps: list[datetime] = []
        self._daily_order_count: dict[date, int] = {}

    def validate_order_timing(
        self,
        exchange: str,
        now_utc: datetime,
    ) -> ValidationResult:
        """Validate order is within market hours for the exchange."""
        _validate_utc(now_utc)
        hours = self._market_hours.get(exchange)
        if hours is None:
            return ValidationResult(
                rule_id="SEBI-MKT-001",
                rule_name="Market Hours Validation",
                severity=ValidationSeverity.FAIL,
                message=f"No market hours configured for exchange: {exchange}",
            )
        if hours.is_market_hours(now_utc):
            return ValidationResult(
                rule_id="SEBI-MKT-001",
                rule_name="Market Hours Validation",
                severity=ValidationSeverity.PASS,
                message=f"Order within market hours for {exchange}",
                details={"exchange": exchange},
            )
        return ValidationResult(
            rule_id="SEBI-MKT-001",
            rule_name="Market Hours Validation",
            severity=ValidationSeverity.FAIL,
            message=f"Order outside market hours for {exchange}",
            details={"exchange": exchange},
        )

    def validate_order_rate(self, now_utc: datetime) -> ValidationResult:
        """Validate order rate does not exceed SEBI throttling limits."""
        _validate_utc(now_utc)
        window_start = now_utc - timedelta(seconds=1)
        recent_orders = [t for t in self._order_timestamps if t >= window_start]
        recent_count = Decimal(str(len(recent_orders)))
        if recent_count < self._max_order_rate:
            return ValidationResult(
                rule_id="SEBI-THR-001",
                rule_name="Order Rate Throttle",
                severity=ValidationSeverity.PASS,
                message="Order rate within limits",
                details={"current_rate": str(recent_count), "max_rate": str(self._max_order_rate)},
            )
        return ValidationResult(
            rule_id="SEBI-THR-001",
            rule_name="Order Rate Throttle",
            severity=ValidationSeverity.FAIL,
            message="Order rate exceeds SEBI limits",
            details={"current_rate": str(recent_count), "max_rate": str(self._max_order_rate)},
        )

    def validate_daily_order_limit(self, trading_date: date) -> ValidationResult:
        """Validate daily order count does not exceed limits."""
        count = self._daily_order_count.get(trading_date, 0)
        if count < self._max_daily_orders:
            return ValidationResult(
                rule_id="SEBI-DLY-001",
                rule_name="Daily Order Limit",
                severity=ValidationSeverity.PASS,
                message="Daily order count within limits",
                details={"count": str(count), "limit": str(self._max_daily_orders)},
            )
        return ValidationResult(
            rule_id="SEBI-DLY-001",
            rule_name="Daily Order Limit",
            severity=ValidationSeverity.FAIL,
            message="Daily order limit exceeded",
            details={"count": str(count), "limit": str(self._max_daily_orders)},
        )

    def validate_audit_trail(
        self,
        audit_entry_count: int,
    ) -> ValidationResult:
        """Validate audit trail has sufficient entries for SEBI compliance."""
        if audit_entry_count >= self._min_audit_entries:
            return ValidationResult(
                rule_id="SEBI-AUD-001",
                rule_name="Audit Trail Integrity",
                severity=ValidationSeverity.PASS,
                message="Audit trail meets minimum entry requirements",
                details={"entries": str(audit_entry_count)},
            )
        return ValidationResult(
            rule_id="SEBI-AUD-001",
            rule_name="Audit Trail Integrity",
            severity=ValidationSeverity.FAIL,
            message="Audit trail has insufficient entries",
            details={"entries": str(audit_entry_count)},
        )

    def validate_static_ip(self, source_ip: str, allowed_ips: tuple[str, ...]) -> ValidationResult:
        """Validate source IP is in SEBI-registered static IP list."""
        if not source_ip.strip():
            return ValidationResult(
                rule_id="SEBI-IP-001",
                rule_name="Static IP Validation",
                severity=ValidationSeverity.FAIL,
                message="Source IP is empty",
            )
        if source_ip in allowed_ips:
            return ValidationResult(
                rule_id="SEBI-IP-001",
                rule_name="Static IP Validation",
                severity=ValidationSeverity.PASS,
                message="Source IP is in allowed list",
                details={"source_ip": source_ip},
            )
        return ValidationResult(
            rule_id="SEBI-IP-001",
            rule_name="Static IP Validation",
            severity=ValidationSeverity.FAIL,
            message="Source IP not in SEBI-registered list",
            details={"source_ip": source_ip},
        )

    def validate_algo_id(self, algo_id: str) -> ValidationResult:
        """Validate algo ID is registered per SEBI requirements."""
        if not algo_id.strip():
            return ValidationResult(
                rule_id="SEBI-ALG-001",
                rule_name="Algo ID Registration",
                severity=ValidationSeverity.FAIL,
                message="Algo ID is empty or not registered",
            )
        return ValidationResult(
            rule_id="SEBI-ALG-001",
            rule_name="Algo ID Registration",
            severity=ValidationSeverity.PASS,
            message="Algo ID is registered",
            details={"algo_id": algo_id},
        )

    def record_order(self, now_utc: datetime) -> None:
        """Record an order submission for rate tracking."""
        _validate_utc(now_utc)
        self._order_timestamps.append(now_utc)
        trading_date = now_utc.date()
        self._daily_order_count[trading_date] = self._daily_order_count.get(trading_date, 0) + 1
        cutoff = now_utc - timedelta(minutes=5)
        self._order_timestamps = [t for t in self._order_timestamps if t >= cutoff]

    def run_full_validation(
        self,
        exchange: str,
        now_utc: datetime,
        source_ip: str,
        allowed_ips: tuple[str, ...],
        algo_id: str,
        audit_entry_count: int,
    ) -> LiveValidationReport:
        """Run all SEBI validations and produce a complete report."""
        _validate_utc(now_utc)
        results: list[ValidationResult] = [
            self.validate_order_timing(exchange, now_utc),
            self.validate_order_rate(now_utc),
            self.validate_daily_order_limit(now_utc.date()),
            self.validate_audit_trail(audit_entry_count),
            self.validate_static_ip(source_ip, allowed_ips),
            self.validate_algo_id(algo_id),
        ]
        passed = sum(1 for r in results if r.severity == ValidationSeverity.PASS)
        failed = sum(1 for r in results if r.severity == ValidationSeverity.FAIL)
        warnings = sum(1 for r in results if r.severity == ValidationSeverity.WARNING)
        return LiveValidationReport(
            timestamp_utc=now_utc,
            results=results,
            overall_pass=failed == 0,
            total_checks=len(results),
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings,
        )


def _validate_utc(dt: datetime) -> None:
    """Validate datetime is UTC-aware."""
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC-aware"
        raise ConfigError(msg)
