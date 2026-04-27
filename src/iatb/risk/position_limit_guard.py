"""
SEBI Position Limit Enforcement for exchange-level position limits.

Implements position limit checks for NSE F&O, MCX, and CDS exchanges
with real-time monitoring and alerting at 80% threshold.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from iatb.core.exceptions import ConfigError
from iatb.core.observability.alerting import (
    AlertLevel,
    MultiChannelAlertManager,
)
from iatb.core.observability.metrics import record_risk_check_duration

_LOGGER = logging.getLogger(__name__)


class ExchangeType(str, Enum):
    """Supported exchanges for position limits."""

    NSE_FO = "NSE_FO"
    MCX = "MCX"
    CDS = "CDS"
    NSE_EQ = "NSE_EQ"
    BSE_EQ = "BSE_EQ"


@dataclass(frozen=True)
class PositionLimitConfig:
    """Configuration for exchange-specific position limits."""

    exchange: ExchangeType
    max_quantity_per_symbol: Decimal
    max_notional_per_symbol: Decimal
    max_total_notional: Decimal
    alert_threshold_pct: Decimal = Decimal("0.8")

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.max_quantity_per_symbol <= Decimal("0"):
            msg = "max_quantity_per_symbol must be positive"
            raise ConfigError(msg)
        if self.max_notional_per_symbol <= Decimal("0"):
            msg = "max_notional_per_symbol must be positive"
            raise ConfigError(msg)
        if self.max_total_notional <= Decimal("0"):
            msg = "max_total_notional must be positive"
            raise ConfigError(msg)
        if self.alert_threshold_pct <= Decimal("0") or self.alert_threshold_pct > Decimal("1"):
            msg = "alert_threshold_pct must be in (0, 1]"
            raise ConfigError(msg)


@dataclass(frozen=True)
class PositionState:
    """Snapshot of position state for a symbol."""

    exchange: ExchangeType
    symbol: str
    current_quantity: Decimal
    current_notional: Decimal
    limit_quantity: Decimal
    limit_notional: Decimal
    total_notional_used: Decimal
    total_notional_limit: Decimal


class PositionLimitGuard:
    """Enforces SEBI position limits at exchange level.

    Validates orders against exchange-specific position limits and
    monitors positions in real-time with alerting at 80% threshold.
    """

    def __init__(
        self,
        limits: list[PositionLimitConfig],
        alert_manager: MultiChannelAlertManager | None = None,
    ) -> None:
        """Initialize position limit guard.

        Args:
            limits: List of position limit configurations per exchange.
            alert_manager: Optional alert manager for limit breach alerts.

        Raises:
            ConfigError: If validation fails.
        """
        if not limits:
            msg = "limits cannot be empty"
            raise ConfigError(msg)
        self._limits: dict[ExchangeType, PositionLimitConfig] = {}
        for limit in limits:
            if limit.exchange in self._limits:
                msg = f"duplicate limit configuration for {limit.exchange}"
                raise ConfigError(msg)
            self._limits[limit.exchange] = limit

        self._positions: dict[str, tuple[Decimal, Decimal]] = {}
        self._symbol_exchange: dict[str, ExchangeType] = {}
        self._exchange_totals: dict[ExchangeType, Decimal] = {
            exchange: Decimal("0") for exchange in self._limits
        }
        self._alert_manager = alert_manager
        self._alerted_symbols: set[str] = set()
        self._last_alert_time: dict[str, datetime] = {}
        self._monitoring_task: asyncio.Task[None] | None = None

    def get_limit_config(self, exchange: ExchangeType) -> PositionLimitConfig:
        """Get limit configuration for an exchange.

        Args:
            exchange: Exchange type.

        Returns:
            Position limit configuration.

        Raises:
            ConfigError: If exchange not configured.
        """
        config = self._limits.get(exchange)
        if config is None:
            msg = f"no position limit configured for {exchange}"
            raise ConfigError(msg)
        return config

    def _validate_price(self, price: Decimal, symbol: str) -> None:
        """Validate price is positive.

        Args:
            price: Order price.
            symbol: Trading symbol.

        Raises:
            ConfigError: If price is invalid.
        """
        if price <= Decimal("0"):
            msg = f"no valid last price: {price} for {symbol}"
            _LOGGER.error(
                "Invalid price",
                extra={
                    "symbol": symbol,
                    "price": str(price),
                },
            )
            raise ConfigError(msg)

    def _calculate_projected_values(
        self,
        exchange: ExchangeType,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, PositionLimitConfig]:
        """Calculate projected position values.

        Args:
            exchange: Exchange type.
            symbol: Trading symbol.
            quantity: Order quantity.
            price: Order price.

        Returns:
            Tuple of (current_qty, projected_qty, projected_notional,
                     exchange_total, config).
        """
        config = self.get_limit_config(exchange)
        current_qty, current_notional = self._positions.get(symbol, (Decimal("0"), Decimal("0")))
        projected_qty = current_qty + quantity
        projected_notional = current_notional + (quantity * price)
        exchange_total = self._exchange_totals[exchange]
        return current_qty, projected_qty, projected_notional, exchange_total, config

    def _check_quantity_limit(
        self,
        projected_qty: Decimal,
        limit: Decimal,
        symbol: str,
        exchange: ExchangeType,
    ) -> None:
        """Check if quantity would breach limit.

        Args:
            projected_qty: Projected quantity after order.
            limit: Quantity limit.
            symbol: Trading symbol.
            exchange: Exchange type.

        Raises:
            ConfigError: If limit would be breached.
        """
        if projected_qty >= limit:
            msg = (
                f"quantity {projected_qty} meets or exceeds limit "
                f"{limit} for {symbol} on {exchange}"
            )
            _LOGGER.error(
                "Position limit breached (quantity)",
                extra={
                    "symbol": symbol,
                    "exchange": exchange.value,
                    "projected_qty": str(projected_qty),
                    "limit_qty": str(limit),
                },
            )
            raise ConfigError(msg)

    def _check_notional_limit(
        self,
        projected_notional: Decimal,
        limit: Decimal,
        symbol: str,
        exchange: ExchangeType,
    ) -> None:
        """Check if notional would breach limit.

        Args:
            projected_notional: Projected notional after order.
            limit: Notional limit.
            symbol: Trading symbol.
            exchange: Exchange type.

        Raises:
            ConfigError: If limit would be breached.
        """
        if projected_notional >= limit:
            msg = (
                f"notional {projected_notional} meets or exceeds limit "
                f"{limit} for {symbol} on {exchange}"
            )
            _LOGGER.error(
                "Position limit breached (notional)",
                extra={
                    "symbol": symbol,
                    "exchange": exchange.value,
                    "projected_notional": str(projected_notional),
                    "limit_notional": str(limit),
                },
            )
            raise ConfigError(msg)

    def _check_exchange_total_limit(
        self,
        projected_total: Decimal,
        limit: Decimal,
        exchange: ExchangeType,
    ) -> None:
        """Check if exchange total notional would breach limit.

        Args:
            projected_total: Projected exchange total after order.
            limit: Exchange total notional limit.
            exchange: Exchange type.

        Raises:
            ConfigError: If limit would be breached.
        """
        if projected_total >= limit:
            msg = (
                f"exchange total notional {projected_total} meets or exceeds limit "
                f"{limit} for {exchange}"
            )
            _LOGGER.error(
                "Position limit breached (exchange total)",
                extra={
                    "exchange": exchange.value,
                    "projected_total": str(projected_total),
                    "limit_total": str(limit),
                },
            )
            raise ConfigError(msg)

    def _build_position_state(
        self,
        exchange: ExchangeType,
        symbol: str,
        current_qty: Decimal,
        price: Decimal,
        exchange_total: Decimal,
        config: PositionLimitConfig,
    ) -> PositionState:
        return PositionState(
            exchange=exchange,
            symbol=symbol,
            current_quantity=current_qty,
            current_notional=current_qty * price,
            limit_quantity=config.max_quantity_per_symbol,
            limit_notional=config.max_notional_per_symbol,
            total_notional_used=exchange_total,
            total_notional_limit=config.max_total_notional,
        )

    def validate_order(
        self,
        exchange: ExchangeType,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
        now_utc: datetime,
    ) -> PositionState:
        """Validate order against position limits.

        Args:
            exchange: Exchange type.
            symbol: Trading symbol.
            quantity: Order quantity (always positive).
            price: Order price.
            now_utc: Current UTC datetime.

        Returns:
            Current position state after validation.

        Raises:
            ConfigError: If order would breach limits or price is invalid.
        """
        _validate_utc(now_utc)
        self._validate_price(price, symbol)
        self._symbol_exchange[symbol] = exchange

        (
            current_qty,
            projected_qty,
            projected_notional,
            exchange_total,
            config,
        ) = self._calculate_projected_values(exchange, symbol, quantity, price)

        projected_total = exchange_total + (quantity * price)

        # Timing parameter, not financial: record risk check duration (0.0 for pre-check)
        record_risk_check_duration("position_limit_guard_validate_order", 0.0)

        self._check_quantity_limit(projected_qty, config.max_quantity_per_symbol, symbol, exchange)
        self._check_notional_limit(
            projected_notional, config.max_notional_per_symbol, symbol, exchange
        )
        self._check_exchange_total_limit(projected_total, config.max_total_notional, exchange)

        return self._build_position_state(
            exchange, symbol, current_qty, price, exchange_total, config
        )

    def update_position(
        self,
        exchange: ExchangeType,
        symbol: str,
        quantity_delta: Decimal,
        price: Decimal,
        now_utc: datetime,
    ) -> None:
        """Update position after order fill.

        Args:
            exchange: Exchange type.
            symbol: Trading symbol.
            quantity_delta: Change in quantity (positive for buy, negative for sell).
            price: Fill price.
            now_utc: Current UTC datetime.
        """
        _validate_utc(now_utc)
        self.get_limit_config(exchange)
        self._symbol_exchange[symbol] = exchange

        current_qty, current_notional = self._positions.get(symbol, (Decimal("0"), Decimal("0")))
        new_qty = current_qty + quantity_delta
        notional_delta = abs(quantity_delta) * price
        new_notional = current_notional + notional_delta

        if new_qty <= Decimal("0"):
            self._positions.pop(symbol, None)
            self._alerted_symbols.discard(symbol)
        else:
            self._positions[symbol] = (new_qty, new_notional)

        self._exchange_totals[exchange] += notional_delta

        _LOGGER.info(
            "Position updated",
            extra={
                "symbol": symbol,
                "exchange": exchange.value,
                "quantity_delta": str(quantity_delta),
                "new_quantity": str(new_qty),
                "new_notional": str(new_notional),
            },
        )

    def _validate_monitoring_interval(self, interval_seconds: int) -> None:
        """Validate monitoring interval parameter.

        Args:
            interval_seconds: Monitoring interval in seconds.

        Raises:
            ConfigError: If interval is invalid.
        """
        if interval_seconds <= 0:
            msg = "interval_seconds must be positive"
            raise ConfigError(msg)

    async def start_monitoring(
        self,
        interval_seconds: int = 60,
        check_alerts: bool = True,
    ) -> asyncio.Task[None]:
        """Start background position monitoring loop.

        Args:
            interval_seconds: Monitoring interval in seconds.
            check_alerts: Whether to check and send alerts.

        Returns:
            Async task for the monitoring loop.

        Raises:
            ConfigError: If interval is invalid.
        """
        self._validate_monitoring_interval(interval_seconds)

        _LOGGER.info(
            "Starting position limit monitoring",
            extra={"interval_seconds": interval_seconds, "check_alerts": check_alerts},
        )

        async def _monitor() -> None:
            while True:
                try:
                    if check_alerts:
                        self._check_alert_thresholds(datetime.now(UTC))
                    await asyncio.sleep(interval_seconds)
                except Exception:
                    _LOGGER.error("Position monitoring error", exc_info=True)
                    await asyncio.sleep(interval_seconds)

        self._monitoring_task = asyncio.create_task(_monitor())
        return self._monitoring_task

    async def stop_monitoring(self) -> None:
        """Stop the background monitoring task."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                _LOGGER.info("Position monitoring task cancelled")
        self._monitoring_task = None

    def _check_alert_thresholds(self, now_utc: datetime) -> None:
        """Check and send alerts for positions approaching limits.

        Args:
            now_utc: Current UTC datetime.
        """
        for symbol, (qty, notional) in self._positions.items():
            if not qty:
                continue

            config = self._get_symbol_config(symbol)
            if config is None:
                continue

            qty_pct = qty / config.max_quantity_per_symbol
            notional_pct = notional / config.max_notional_per_symbol

            alert_key = f"{config.exchange.value}:{symbol}"
            should_alert = (
                qty_pct >= config.alert_threshold_pct or notional_pct >= config.alert_threshold_pct
            )

            if not should_alert:
                self._alerted_symbols.discard(alert_key)
                continue

            if alert_key in self._alerted_symbols:
                last_alert = self._last_alert_time.get(alert_key)
                if last_alert and (now_utc - last_alert).total_seconds() < 300:
                    continue

            self._send_limit_alert(
                config,
                symbol,
                qty,
                notional,
                qty_pct,
                notional_pct,
                now_utc,
            )
            self._alerted_symbols.add(alert_key)
            self._last_alert_time[alert_key] = now_utc

    def _get_symbol_config(self, symbol: str) -> PositionLimitConfig | None:
        """Get limit config for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Limit configuration if found, None otherwise.
        """
        if symbol not in self._positions:
            return None
        exchange = self._symbol_exchange.get(symbol)
        if exchange is not None:
            return self._limits.get(exchange)
        for limit_config in self._limits.values():
            return limit_config
        return None

    def _send_limit_alert(
        self,
        config: PositionLimitConfig,
        symbol: str,
        qty: Decimal,
        notional: Decimal,
        qty_pct: Decimal,
        notional_pct: Decimal,
        now_utc: datetime,
    ) -> None:
        """Send alert for approaching limit.

        Args:
            config: Limit configuration.
            symbol: Trading symbol.
            qty: Current quantity.
            notional: Current notional.
            qty_pct: Quantity as percentage of limit.
            notional_pct: Notional as percentage of limit.
            now_utc: Current UTC datetime.
        """
        if self._alert_manager is None:
            return

        message = (
            f"Position approaching limit:\n"
            f"  Exchange: {config.exchange.value}\n"
            f"  Symbol: {symbol}\n"
            f"  Quantity: {qty} / {config.max_quantity_per_symbol} "
            f"({qty_pct:.1%})\n"
            f"  Notional: {notional} / {config.max_notional_per_symbol} "
            f"({notional_pct:.1%})\n"
            f"  Time (UTC): {now_utc.isoformat()}"
        )

        _LOGGER.warning(
            "Position limit alert",
            extra={
                "symbol": symbol,
                "exchange": config.exchange.value,
                "qty_pct": str(qty_pct),
                "notional_pct": str(notional_pct),
            },
        )

        self._alert_manager.send_alert(
            level=AlertLevel.WARNING,
            message=f"Position Limit Alert: {symbol}\n{message}",
            rule_name="position_limit_approaching",
        )

    def get_position_state(self, symbol: str) -> PositionState | None:
        """Get current position state for a symbol.

        Args:
            symbol: Trading symbol.

        Returns:
            Position state if position exists, None otherwise.
        """
        if symbol not in self._positions:
            return None

        qty, notional = self._positions[symbol]
        config = self._get_symbol_config(symbol)
        if config is None:
            return None

        exchange_total = self._exchange_totals.get(config.exchange, Decimal("0"))

        return PositionState(
            exchange=config.exchange,
            symbol=symbol,
            current_quantity=qty,
            current_notional=notional,
            limit_quantity=config.max_quantity_per_symbol,
            limit_notional=config.max_notional_per_symbol,
            total_notional_used=exchange_total,
            total_notional_limit=config.max_total_notional,
        )

    def get_exchange_summary(self, exchange: ExchangeType) -> dict[str, Decimal]:
        """Get position summary for an exchange.

        Args:
            exchange: Exchange type.

        Returns:
            Dictionary with total_notional and position_count.
        """
        config = self.get_limit_config(exchange)
        return {
            "total_notional": self._exchange_totals[exchange],
            "total_notional_limit": config.max_total_notional,
            "position_count": Decimal(str(self._get_position_count_for_exchange(exchange))),
        }

    def _get_position_count_for_exchange(self, exchange: ExchangeType) -> int:
        """Count positions for an exchange.

        Args:
            exchange: Exchange type.

        Returns:
            Number of positions.
        """
        count = 0
        for symbol, (qty, _) in self._positions.items():
            if qty > Decimal("0"):
                config = self._get_symbol_config(symbol)
                if config and config.exchange == exchange:
                    count += 1
        return count

    def reset(self, now_utc: datetime) -> None:
        """Reset all positions (typically at end of trading day).

        Args:
            now_utc: Current UTC datetime.
        """
        _validate_utc(now_utc)
        self._positions.clear()
        self._alerted_symbols.clear()
        self._last_alert_time.clear()
        for exchange in self._exchange_totals:
            self._exchange_totals[exchange] = Decimal("0")
        _LOGGER.info("Position limit guard reset", extra={"timestamp_utc": now_utc.isoformat()})


def _validate_utc(dt: datetime) -> None:
    """Validate datetime is UTC-aware.

    Args:
        dt: Datetime to validate.

    Raises:
        ConfigError: If datetime is not UTC-aware.
    """
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC-aware"
        raise ConfigError(msg)


def create_default_limits() -> list[PositionLimitConfig]:
    """Create default SEBI-compliant position limits.

    Returns:
        List of default position limit configurations.
    """
    return [
        PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("10000"),
            max_notional_per_symbol=Decimal("50000000"),
            max_total_notional=Decimal("500000000"),
        ),
        PositionLimitConfig(
            exchange=ExchangeType.MCX,
            max_quantity_per_symbol=Decimal("1000"),
            max_notional_per_symbol=Decimal("100000000"),
            max_total_notional=Decimal("1000000000"),
        ),
        PositionLimitConfig(
            exchange=ExchangeType.CDS,
            max_quantity_per_symbol=Decimal("10000"),
            max_notional_per_symbol=Decimal("50000000"),
            max_total_notional=Decimal("200000000"),
        ),
    ]
