"""
Price reconciliation module to validate single-source data consistency.

MITIGATION OF RISK 1 (Data Inconsistency):
- Scanner and execution both use KiteProvider as single source of truth
- Eliminates 0.1-2% price discrepancies from multi-source architecture
- Validates timestamp consistency between scanner fetch and execution

Previous Risk (now mitigated):
Scanner analyzed jugaad-data prices while execution happened via Zerodha,
causing price discrepancies due to:
- Different timestamp granularity (jugaad: daily EOD vs Kite: real-time)
- Corporate action adjustments (splits, dividends)
- Symbol mapping differences (RELIANCE vs RELIANCE-EQ)

Current Architecture (single-source truth):
- Scanner fetches data via DataProvider (KiteProvider)
- Execution uses Kite/Zerodha
- Both use same data source, eliminating discrepancies
- Reconciler validates timestamp alignment and data freshness
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from iatb.core.exceptions import ConfigError
from iatb.core.types import Price


@dataclass(frozen=True)
class ReconciliationConfig:
    """Configuration for price reconciliation checks."""

    # Maximum allowed price deviation between sources (e.g., 2%)
    max_price_deviation_pct: Decimal = Decimal("0.02")

    # Maximum allowed timestamp drift between sources (e.g., 1 minute)
    max_timestamp_drift_seconds: int = 60

    # Enable/disable strict timestamp alignment for EOD data
    strict_eod_alignment: bool = True

    # Enable/disable corporate action detection
    detect_corporate_actions: bool = True

    # Enable/disable symbol mapping validation
    validate_symbol_mapping: bool = True

    # Maximum allowed price jump (potential split/bonus detection)
    max_price_jump_pct: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.max_price_deviation_pct <= Decimal("0"):
            msg = "max_price_deviation_pct must be positive"
            raise ConfigError(msg)
        if self.max_timestamp_drift_seconds <= 0:
            msg = "max_timestamp_drift_seconds must be positive"
            raise ConfigError(msg)
        if self.max_price_jump_pct <= Decimal("0"):
            msg = "max_price_jump_pct must be positive"
            raise ConfigError(msg)


@dataclass(frozen=True)
class PriceDataPoint:
    """Price data from a specific source with metadata."""

    price: Price
    timestamp: datetime
    source: str  # "jugaad", "kite", "kite_ws", etc.
    symbol: str
    data_type: Literal["tick", "minute", "day"]

    def __post_init__(self) -> None:
        """Ensure UTC timestamp."""
        if self.timestamp.tzinfo != UTC:
            msg = f"timestamp must be UTC-aware, got {self.timestamp.tzinfo}"
            raise ConfigError(msg)


@dataclass(frozen=True)
class ReconciliationResult:
    """Result of price reconciliation check."""

    passed: bool
    deviation_pct: Decimal
    reason: str
    severity: Literal["info", "warning", "error", "critical"]


class PriceReconciler:
    """
    Reconciles prices between data sources to validate consistency.

    In the single-source architecture (KiteProvider as truth), this validates:
    - Timestamp consistency between scanner fetch and execution time
    - Symbol mapping correctness
    - Data freshness (scanner data not too old)
    - Corporate action detection (unexpected price jumps)
    """

    def __init__(self, config: ReconciliationConfig) -> None:
        """Initialize reconciler with configuration."""
        self._config = config

    def reconcile_prices(
        self,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
        prev_close_price: Price | None = None,
    ) -> ReconciliationResult:
        """
        Reconcile scanner price with execution price (both from Kite).

        Args:
            scanner_price: Price from scanner (Kite, via DataProvider)
            execution_price: Price from execution (Kite, real-time)
            prev_close_price: Previous day's close price for corporate action detection

        Returns:
            ReconciliationResult with pass/fail status and details
        """
        # 1. Validate symbol mapping
        if self._config.validate_symbol_mapping:
            symbol_result = self._validate_symbol_mapping(scanner_price, execution_price)
            if not symbol_result.passed:
                return symbol_result

        # 2. Check timestamp alignment
        timestamp_result = self._check_timestamp_alignment(scanner_price, execution_price)
        if not timestamp_result.passed and self._config.strict_eod_alignment:
            return timestamp_result

        # 3. Check price deviation
        price_result = self._check_price_deviation(scanner_price, execution_price)
        if not price_result.passed:
            # If price deviation is high, check for corporate actions
            if self._config.detect_corporate_actions and prev_close_price:
                ca_result = self._detect_corporate_action(
                    scanner_price, execution_price, prev_close_price
                )
                if ca_result.passed:
                    # Corporate action detected, deviation is expected
                    return ca_result
            return price_result

        return price_result

    def _validate_symbol_mapping(
        self,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
    ) -> ReconciliationResult:
        """Validate that symbols are correctly mapped between sources."""
        # Normalize symbols for comparison
        scanner_symbol = self._normalize_symbol(scanner_price.symbol)
        execution_symbol = self._normalize_symbol(execution_price.symbol)

        if scanner_symbol != execution_symbol:
            return ReconciliationResult(
                passed=False,
                deviation_pct=Decimal("0"),
                reason=(
                    f"Symbol mismatch: scanner='{scanner_price.symbol}' "
                    f"vs execution='{execution_price.symbol}'"
                ),
                severity="critical",
            )

        return ReconciliationResult(
            passed=True,
            deviation_pct=Decimal("0"),
            reason="Symbol mapping validated",
            severity="info",
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for comparison (e.g., RELIANCE-EQ -> RELIANCE)."""
        # Remove common suffixes
        symbol = symbol.replace("-EQ", "").replace("-BE", "")
        # Convert to uppercase
        symbol = symbol.upper()
        # Strip whitespace
        symbol = symbol.strip()
        return symbol

    def _check_timestamp_alignment(
        self,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
    ) -> ReconciliationResult:
        """
        Check timestamp alignment between data sources.

        For EOD data from scanner, allow 1-day drift from current time.
        For real-time data, allow only configured drift (e.g., 60 seconds).
        """
        # Check scanner timestamp
        scanner_result = self._check_scanner_timestamp(scanner_price)
        if not scanner_result.passed:
            return scanner_result

        # Check execution timestamp
        exec_result = self._check_execution_timestamp(execution_price)
        if not exec_result.passed:
            return exec_result

        return ReconciliationResult(
            passed=True,
            deviation_pct=Decimal("0"),
            reason="Timestamp alignment validated",
            severity="info",
        )

    def _check_scanner_timestamp(self, scanner_price: PriceDataPoint) -> ReconciliationResult:
        """Check scanner price timestamp validity."""
        now = datetime.now(UTC)

        if scanner_price.data_type == "day":
            days_diff = (now - scanner_price.timestamp).days
            if days_diff > 1:
                return ReconciliationResult(
                    passed=False,
                    deviation_pct=Decimal("0"),
                    reason=(
                        f"Scanner price too old: {days_diff} days old, "
                        f"timestamp={scanner_price.timestamp}"
                    ),
                    severity="error",
                )
        else:
            drift = abs((now - scanner_price.timestamp).total_seconds())
            if drift > self._config.max_timestamp_drift_seconds:
                return ReconciliationResult(
                    passed=False,
                    deviation_pct=Decimal("0"),
                    reason=(
                        f"Scanner price timestamp drift too high: "
                        f"{drift}s > {self._config.max_timestamp_drift_seconds}s"
                    ),
                    severity="warning",
                )

        return ReconciliationResult(
            passed=True,
            deviation_pct=Decimal("0"),
            reason="Scanner timestamp valid",
            severity="info",
        )

    def _check_execution_timestamp(self, execution_price: PriceDataPoint) -> ReconciliationResult:
        """Check execution price timestamp validity."""
        now = datetime.now(UTC)
        exec_drift = abs((now - execution_price.timestamp).total_seconds())

        if exec_drift > self._config.max_timestamp_drift_seconds:
            return ReconciliationResult(
                passed=False,
                deviation_pct=Decimal("0"),
                reason=(
                    f"Execution price timestamp drift too high: "
                    f"{exec_drift}s > {self._config.max_timestamp_drift_seconds}s"
                ),
                severity="error",
            )

        return ReconciliationResult(
            passed=True,
            deviation_pct=Decimal("0"),
            reason="Execution timestamp valid",
            severity="info",
        )

    def _check_price_deviation(
        self,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
    ) -> ReconciliationResult:
        """
        Check if price deviation between sources exceeds threshold.

        For EOD scanner data, compare with current market price.
        Allow higher tolerance due to intraday movement.
        """
        if scanner_price.price <= Decimal("0") or execution_price.price <= Decimal("0"):
            return ReconciliationResult(
                passed=False,
                deviation_pct=Decimal("0"),
                reason="Invalid price (zero or negative)",
                severity="critical",
            )

        deviation = abs(scanner_price.price - execution_price.price) / scanner_price.price

        if deviation > self._config.max_price_deviation_pct:
            # Severity: critical if >5%, error if >2% (default threshold)
            severity: Literal["info", "warning", "error", "critical"] = (
                "critical" if deviation >= Decimal("0.05") else "error"
            )
            return ReconciliationResult(
                passed=False,
                deviation_pct=deviation,
                reason=(
                    f"Price deviation {deviation:.4f} ({deviation*100:.2f}%) "
                    f"exceeds max {self._config.max_price_deviation_pct:.4f} "
                    f"({self._config.max_price_deviation_pct*100:.2f}%). "
                    f"Scanner: {scanner_price.price}, "
                    f"Execution: {execution_price.price}"
                ),
                severity=severity,
            )

        return ReconciliationResult(
            passed=True,
            deviation_pct=deviation,
            reason=(
                f"Price deviation {deviation:.4f} within threshold "
                f"({self._config.max_price_deviation_pct:.4f})"
            ),
            severity="info",
        )

    def _detect_corporate_action(
        self,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
        prev_close_price: Price,
    ) -> ReconciliationResult:
        """
        Detect if price deviation is due to corporate action (split, bonus, dividend).

        Corporate actions cause sudden large price changes that are legitimate.
        """
        scanner_vs_prev = self._calculate_deviation(scanner_price.price, prev_close_price)
        exec_vs_prev = self._calculate_deviation(execution_price.price, prev_close_price)

        # Check for corporate action pattern
        ca_result = self._check_ca_pattern(
            scanner_vs_prev, exec_vs_prev, scanner_price, execution_price, prev_close_price
        )
        if ca_result:
            return ca_result

        # Check for market movement pattern
        mm_result = self._check_market_movement(
            scanner_vs_prev, exec_vs_prev, scanner_price, execution_price
        )
        if mm_result:
            return mm_result

        # Inconclusive - treat as error
        deviation = self._calculate_deviation(scanner_price.price, execution_price.price)
        return ReconciliationResult(
            passed=False,
            deviation_pct=deviation,
            reason="Price deviation detected but corporate action status unclear",
            severity="error",
        )

    def _calculate_deviation(self, price1: Price, price2: Price) -> Decimal:
        """Calculate percentage deviation between two prices."""
        return abs(price1 - price2) / price2

    def _check_ca_pattern(
        self,
        scanner_vs_prev: Decimal,
        exec_vs_prev: Decimal,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
        prev_close_price: Price,
    ) -> ReconciliationResult | None:
        """Check if price pattern indicates corporate action."""
        if scanner_vs_prev < Decimal("0.01") and exec_vs_prev > self._config.max_price_jump_pct:
            direction = "DOWN" if execution_price.price < prev_close_price else "UP"
            return ReconciliationResult(
                passed=True,
                deviation_pct=exec_vs_prev,
                reason=(
                    f"Corporate action detected: Price moved {direction} "
                    f"{exec_vs_prev:.4f} from prev_close {prev_close_price}. "
                    f"Scanner EOD: {scanner_price.price}, "
                    f"Current: {execution_price.price}"
                ),
                severity="warning",
            )
        return None

    def _check_market_movement(
        self,
        scanner_vs_prev: Decimal,
        exec_vs_prev: Decimal,
        scanner_price: PriceDataPoint,
        execution_price: PriceDataPoint,
    ) -> ReconciliationResult | None:
        """Check if price pattern indicates normal market movement."""
        if abs(scanner_vs_prev - exec_vs_prev) < Decimal("0.02"):
            deviation = self._calculate_deviation(scanner_price.price, execution_price.price)
            return ReconciliationResult(
                passed=True,
                deviation_pct=deviation,
                reason="Price deviation due to market movement, not corporate action",
                severity="info",
            )
        return None
