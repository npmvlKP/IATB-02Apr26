"""
Pre-trade order validation with five risk gates + price reconciliation.

MITIGATION OF RISK 1 (Data Inconsistency):
- Scanner and execution both use KiteProvider as single source of truth
- Price reconciliation validates timestamp consistency, not cross-source discrepancies
- Eliminates 0.1-2% price discrepancies from multi-source architecture

MITIGATION OF RISK J.1 (SEBI Position Limit Enforcement):
- Integrated with PositionLimitGuard for exchange-level position limits
- Pre-check validates against NSE F&O, MCX, and CDS limits
- Real-time monitoring with 80% threshold alerts
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.exceptions import ConfigError
from iatb.core.types import Price
from iatb.data.price_reconciler import (
    PriceDataPoint,
    PriceReconciler,
    ReconciliationConfig,
    ReconciliationResult,
)
from iatb.execution.base import OrderRequest

if TYPE_CHECKING:
    from iatb.risk.position_limit_guard import (
        ExchangeType,
        PositionLimitGuard,
    )


@dataclass(frozen=True)
class PreTradeConfig:
    max_order_quantity: Decimal
    max_order_value: Decimal
    max_price_deviation_pct: Decimal
    max_position_per_symbol: Decimal
    max_portfolio_exposure: Decimal

    def __post_init__(self) -> None:
        for name, value in [
            ("max_order_quantity", self.max_order_quantity),
            ("max_order_value", self.max_order_value),
            ("max_position_per_symbol", self.max_position_per_symbol),
            ("max_portfolio_exposure", self.max_portfolio_exposure),
        ]:
            if value <= Decimal("0"):
                msg = f"{name} must be positive"
                raise ConfigError(msg)
        if self.max_price_deviation_pct <= Decimal("0"):
            msg = "max_price_deviation_pct must be positive"
            raise ConfigError(msg)


def validate_order(
    request: OrderRequest,
    config: PreTradeConfig,
    last_prices: dict[str, Decimal],
    current_positions: dict[str, Decimal],
    total_exposure: Decimal,
) -> OrderRequest:
    """Validate order against all pre-trade gates. Raises on failure."""
    price = _resolve_price(request, last_prices)
    _check_quantity(request, config)
    _check_notional(request, price, config)
    _check_price_deviation(request, price, last_prices, config)
    _check_position_limit(request, current_positions, config)
    _check_exposure(request, price, total_exposure, config)
    return request


def validate_order_with_position_limit_guard(
    request: OrderRequest,
    config: PreTradeConfig,
    last_prices: dict[str, Decimal],
    current_positions: dict[str, Decimal],
    total_exposure: Decimal,
    position_limit_guard: "PositionLimitGuard",
    exchange: "ExchangeType",
    price: Decimal | None = None,
) -> OrderRequest:
    """Validate order including SEBI position limits (RISK J.1).

    Standard pre-trade gates plus exchange-specific position limits.
    Raises ConfigError on any validation failure.
    """
    order_price = price if price is not None else _resolve_price(request, last_prices)
    _check_quantity(request, config)
    _check_notional(request, order_price, config)
    _check_price_deviation(request, order_price, last_prices, config)
    _check_position_limit(request, current_positions, config)
    _check_exposure(request, order_price, total_exposure, config)
    position_limit_guard.validate_order(
        exchange=exchange,
        symbol=request.symbol,
        quantity=request.quantity,
        price=order_price,
        now_utc=datetime.now(UTC),
    )
    return request


def _resolve_price(request: OrderRequest, last_prices: dict[str, Decimal]) -> Decimal:
    if request.price is not None:
        return request.price
    last = last_prices.get(request.symbol)
    if last is None or last <= Decimal("0"):
        msg = f"no valid last price for {request.symbol}"
        raise ConfigError(msg)
    return last


def _check_quantity(request: OrderRequest, config: PreTradeConfig) -> None:
    if request.quantity > config.max_order_quantity:
        msg = f"fat-finger: quantity {request.quantity} exceeds max {config.max_order_quantity}"
        raise ConfigError(msg)


def _check_notional(request: OrderRequest, price: Decimal, config: PreTradeConfig) -> None:
    notional = request.quantity * price
    if notional > config.max_order_value:
        msg = f"notional {notional} exceeds max {config.max_order_value}"
        raise ConfigError(msg)


def _check_price_deviation(
    request: OrderRequest,
    price: Decimal,
    last_prices: dict[str, Decimal],
    config: PreTradeConfig,
) -> None:
    last = last_prices.get(request.symbol)
    if last is None or last <= Decimal("0"):
        return
    deviation = abs(price - last) / last
    if deviation > config.max_price_deviation_pct:
        msg = f"price deviation {deviation:.4f} exceeds max {config.max_price_deviation_pct}"
        raise ConfigError(msg)


def _check_position_limit(
    request: OrderRequest,
    current_positions: dict[str, Decimal],
    config: PreTradeConfig,
) -> None:
    current = abs(current_positions.get(request.symbol, Decimal("0")))
    projected = current + request.quantity
    if projected > config.max_position_per_symbol:
        msg = f"position {projected} exceeds max {config.max_position_per_symbol}"
        raise ConfigError(msg)


def _check_exposure(
    request: OrderRequest,
    price: Decimal,
    total_exposure: Decimal,
    config: PreTradeConfig,
) -> None:
    order_notional = request.quantity * price
    projected = total_exposure + order_notional
    if projected > config.max_portfolio_exposure:
        msg = f"exposure {projected} exceeds max {config.max_portfolio_exposure}"
        raise ConfigError(msg)


def _create_price_data_points(
    scanner_price: Decimal,
    execution_price: Decimal,
    scanner_timestamp: datetime,
    execution_timestamp: datetime,
    symbol: str,
    prev_close_price: Decimal | None,
) -> tuple[PriceDataPoint, PriceDataPoint, Price | None]:
    """Create price data points for scanner and execution."""
    scanner_data = _create_scanner_data_point(scanner_price, scanner_timestamp, symbol)
    execution_data = _create_execution_data_point(execution_price, execution_timestamp, symbol)
    prev_close = Price(prev_close_price) if prev_close_price else None
    return scanner_data, execution_data, prev_close


def _perform_reconciliation(
    scanner_data: PriceDataPoint,
    execution_data: PriceDataPoint,
    prev_close: Price | None,
    config: ReconciliationConfig,
) -> ReconciliationResult:
    """Perform price reconciliation using PriceReconciler."""
    reconciler = PriceReconciler(config)
    return reconciler.reconcile_prices(
        scanner_price=scanner_data,
        execution_price=execution_data,
        prev_close_price=prev_close,
    )


def validate_with_price_reconciliation(
    scanner_price: Decimal,
    execution_price: Decimal,
    scanner_timestamp: datetime,
    execution_timestamp: datetime,
    symbol: str,
    prev_close_price: Decimal | None = None,
    reconciler_config: ReconciliationConfig | None = None,
) -> ReconciliationResult:
    """
    Validate prices between scanner and execution sources (both from Kite).

    MITIGATION OF RISK 1: Single-source architecture eliminates 0.1-2% discrepancies.
    Validates timestamp consistency, symbol mapping, data freshness, and CA detection.

    Args:
        scanner_price: Price from scanner (Kite, via DataProvider)
        execution_price: Price from execution (Kite, real-time)
        scanner_timestamp: Timestamp of scanner price data
        execution_timestamp: Timestamp of execution price data
        symbol: Trading symbol
        prev_close_price: Previous day's close price for CA detection
        reconciler_config: Configuration for reconciliation (uses defaults if None)

    Returns:
        ReconciliationResult with pass/fail status and detailed reason

    Raises:
        ConfigError: If timestamps are not UTC-aware or invalid
    """
    config = reconciler_config or ReconciliationConfig()
    scanner_data, execution_data, prev_close = _create_price_data_points(
        scanner_price,
        execution_price,
        scanner_timestamp,
        execution_timestamp,
        symbol,
        prev_close_price,
    )
    return _perform_reconciliation(scanner_data, execution_data, prev_close, config)


def _create_scanner_data_point(price: Decimal, timestamp: datetime, symbol: str) -> PriceDataPoint:
    """Create PriceDataPoint for scanner (Kite via DataProvider) source."""
    return PriceDataPoint(
        price=Price(price),
        timestamp=timestamp,
        source="kite",
        symbol=symbol,
        data_type="day",
    )


def _create_execution_data_point(
    price: Decimal, timestamp: datetime, symbol: str
) -> PriceDataPoint:
    """Create PriceDataPoint for execution (Kite) source."""
    return PriceDataPoint(
        price=Price(price),
        timestamp=timestamp,
        source="kite",
        symbol=symbol,
        data_type="tick",
    )


def create_reconciliation_config(
    max_price_deviation_pct: Decimal = Decimal("0.02"),
    max_timestamp_drift_seconds: int = 60,
    strict_eod_alignment: bool = True,
    detect_corporate_actions: bool = True,
    validate_symbol_mapping: bool = True,
    max_price_jump_pct: Decimal = Decimal("0.20"),
) -> ReconciliationConfig:
    """
    Create a ReconciliationConfig with specified parameters.

    Helper function to create configuration with production-safe defaults.

    Args:
        max_price_deviation_pct: Maximum allowed price deviation (default 2%)
        max_timestamp_drift_seconds: Maximum timestamp drift in seconds (default 60s)
        strict_eod_alignment: Enable strict EOD timestamp alignment (default True)
        detect_corporate_actions: Enable corporate action detection (default True)
        validate_symbol_mapping: Enable symbol mapping validation (default True)
        max_price_jump_pct: Maximum price jump before CA detection (default 20%)

    Returns:
        ReconciliationConfig instance
    """
    return ReconciliationConfig(
        max_price_deviation_pct=max_price_deviation_pct,
        max_timestamp_drift_seconds=max_timestamp_drift_seconds,
        strict_eod_alignment=strict_eod_alignment,
        detect_corporate_actions=detect_corporate_actions,
        validate_symbol_mapping=validate_symbol_mapping,
        max_price_jump_pct=max_price_jump_pct,
    )
