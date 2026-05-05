"""
Paper-trading executor with deterministic slippage simulation.

Slippage model
--------------
The slippage applied to each simulated fill is deterministic and composed of
three layers:

1. **Exchange-specific base slippage** (bps)
   - NSE Equity (SPOT): 3 bps
   - NSE F&O (FUTURES / OPTIONS): 2 bps
   - BSE: 5 bps
   - MCX (all segments): 8 bps
   - Fallback (any other exchange / segment): configurable default (5 bps)

2. **Volume-based adjustment** (logarithmic discount)
   - Higher order quantity receives a reduced slippage percentage.
   - Factor = 1 / (1 + 0.1 * log10(quantity + 1))
   - Minimum factor = 0.5 (slippage can at most be halved)
   - Maximum factor = 1.0 (no reduction for tiny quantities)

3. **Directional sign**
   - BUY:  fill_price = base_price + slippage
   - SELL: fill_price = base_price - slippage (clamped to >= 0)

Total slippage bps = exchange_base_bps * volume_adjustment
Price impact      = (total_slippage_bps / 10_000) * base_price
"""

import logging
import math
from decimal import Decimal
from itertools import count
from pathlib import Path
from typing import Final

from iatb.core.enums import Exchange, MarketType, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.storage.backup import export_trading_state, load_trading_state

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange-specific slippage defaults (basis points)
# ---------------------------------------------------------------------------
_EXCHANGE_BASE_SLIPPAGE: dict[tuple[Exchange, MarketType], Decimal] = {
    (Exchange.NSE, MarketType.SPOT): Decimal("3"),
    (Exchange.NSE, MarketType.FUTURES): Decimal("2"),
    (Exchange.NSE, MarketType.OPTIONS): Decimal("2"),
    (Exchange.BSE, MarketType.SPOT): Decimal("5"),
    (Exchange.MCX, MarketType.SPOT): Decimal("8"),
    (Exchange.MCX, MarketType.FUTURES): Decimal("8"),
    (Exchange.MCX, MarketType.OPTIONS): Decimal("8"),
}

# ---------------------------------------------------------------------------
# Volume adjustment constants
# ---------------------------------------------------------------------------
_VOLUME_ADJUSTMENT_MULTIPLIER: Decimal = Decimal("0.1")
_VOLUME_ADJUSTMENT_MIN_FACTOR: Decimal = Decimal("0.5")
_VOLUME_ADJUSTMENT_MAX_FACTOR: Decimal = Decimal("1.0")


def _resolve_base_slippage(exchange: Exchange, market_type: MarketType) -> Decimal:
    """Return the exchange- and segment-specific base slippage in bps."""
    return _EXCHANGE_BASE_SLIPPAGE.get((exchange, market_type), Decimal("5"))


def _volume_adjustment_factor(quantity: Decimal) -> Decimal:
    """Compute the volume-based slippage reduction factor.

    Higher quantities receive a lower effective slippage (better fill).
    The factor is bounded to prevent unrealistic extremes.
    """
    qty_float = float(quantity)  # float here is for math.log10 only
    if qty_float <= 0:
        return _VOLUME_ADJUSTMENT_MAX_FACTOR

    log_val = math.log10(qty_float + 1.0)  # float used in scientific computation
    factor = Decimal("1") / (Decimal("1") + _VOLUME_ADJUSTMENT_MULTIPLIER * Decimal(str(log_val)))

    # Clamp to [0.5, 1.0]
    if factor < _VOLUME_ADJUSTMENT_MIN_FACTOR:
        return _VOLUME_ADJUSTMENT_MIN_FACTOR
    if factor > _VOLUME_ADJUSTMENT_MAX_FACTOR:
        return _VOLUME_ADJUSTMENT_MAX_FACTOR
    return factor


def _compute_slippage_bps(
    exchange: Exchange,
    market_type: MarketType,
    quantity: Decimal,
    override_bps: Decimal | None,
) -> Decimal:
    """Calculate the total slippage in basis points.

    If ``override_bps`` is provided explicitly, it is used directly
    (no exchange-specific or volume adjustments) for backward
    compatibility.  Otherwise the deterministic model is applied:

    1. Exchange-specific base bps
    2. Volume discount on top
    """
    if override_bps is not None:
        return override_bps

    base_bps = _resolve_base_slippage(exchange, market_type)
    vol_factor = _volume_adjustment_factor(quantity)
    return base_bps * vol_factor


def _apply_slippage(
    base_price: Decimal,
    side: OrderSide,
    slippage_bps: Decimal,
) -> Decimal:
    """Apply the computed slippage to a base price."""
    slippage = (slippage_bps / Decimal("10000")) * base_price
    if side == OrderSide.BUY:
        return base_price + slippage
    return max(Decimal("0"), base_price - slippage)


# ---------------------------------------------------------------------------
# Slippage Validation Constants
# ---------------------------------------------------------------------------
_LIQUID_TARGET_SLIPPAGE_BPS: Decimal = Decimal("5")  # 5 bps for liquid instruments
_ILLIQUID_TARGET_SLIPPAGE_BPS: Decimal = Decimal("10")  # 10 bps for illiquid instruments
_VALIDATION_TOLERANCE_BPS: Decimal = Decimal("2")  # ±2 bps tolerance for validation


def validate_fill_against_market(
    fill_price: Decimal,
    market_price: Decimal,
    side: OrderSide,
    target_slippage_bps: Decimal,
    tolerance_bps: Decimal = _VALIDATION_TOLERANCE_BPS,
) -> tuple[bool, str, Decimal]:
    """Validate that a paper fill is within acceptable slippage bounds.

    Compares the actual fill price against an expected price based on
    the market price and target slippage. This validates that the
    deterministic slippage model produces realistic fills.

    Args:
        fill_price: The actual price from paper executor.
        market_price: The reference market price (base price).
        side: Order side (BUY or SELL).
        target_slippage_bps: Expected slippage in basis points.
        tolerance_bps: Acceptable deviation from target (default: 2 bps).

    Returns:
        A tuple of (is_valid, message, actual_slippage_bps).
        - is_valid: True if fill is within tolerance
        - message: Human-readable validation result
        - actual_slippage_bps: Actual slippage applied in basis points
    """
    # Calculate expected slippage amount (for reference)
    _expected_slippage_amount = (target_slippage_bps / Decimal("10000")) * market_price

    # Calculate actual slippage in bps
    price_diff = abs(fill_price - market_price)
    actual_slippage_bps = (price_diff / market_price) * Decimal("10000")

    # Calculate deviation from target
    deviation_bps = abs(actual_slippage_bps - target_slippage_bps)

    # Check if within tolerance
    is_valid = deviation_bps <= tolerance_bps

    # Build message
    if is_valid:
        message = (
            f"Fill validated: {actual_slippage_bps:.2f} bps slippage "
            f"(target: {target_slippage_bps} bps ±{tolerance_bps} bps)"
        )
    else:
        message = (
            f"Fill out of bounds: {actual_slippage_bps:.2f} bps slippage "
            f"(target: {target_slippage_bps} bps ±{tolerance_bps} bps, "
            f"deviation: {deviation_bps:.2f} bps)"
        )

    return is_valid, message, actual_slippage_bps


def is_liquid_instrument(exchange: Exchange, market_type: MarketType) -> bool:
    """Determine if an instrument is considered liquid based on exchange/segment.

    Liquid instruments have lower target slippage (5 bps vs 10 bps).

    Args:
        exchange: The exchange identifier.
        market_type: The market type/segment.

    Returns:
        True if liquid, False if illiquid.
    """
    # NSE F&O (futures and options) are highly liquid
    if exchange == Exchange.NSE and market_type in (MarketType.FUTURES, MarketType.OPTIONS):
        return True

    # NSE Equity (SPOT) is generally liquid
    if exchange == Exchange.NSE and market_type == MarketType.SPOT:
        return True

    # BSE is moderately liquid
    if exchange == Exchange.BSE and market_type == MarketType.SPOT:
        return True

    # MCX and other exchanges are less liquid
    return False


class PaperExecutor(Executor):
    """Default executor for safe simulation in non-live mode."""

    def __init__(
        self,
        slippage_bps: Decimal | None = None,
        state_persistence_path: Path | None = None,
        crash_recovery_mode: bool = False,
    ) -> None:
        if slippage_bps is not None and slippage_bps < Decimal("0"):
            msg = "slippage_bps cannot be negative"
            raise ConfigError(msg)
        self._slippage_bps: Decimal | None = slippage_bps
        # Use itertools.count() for thread-safe counter
        self._counter: Final = count(start=1)
        self._open_orders: set[str] = set()
        self._crash_recovery_mode: bool = crash_recovery_mode
        self._state_persistence_path = state_persistence_path

        # Load trading state if persistence path is provided
        self._load_trading_state()

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        order_id = f"PAPER-{next(self._counter):06d}"
        base_price = request.price if request.price is not None else Decimal("100")

        effective_slippage = _compute_slippage_bps(
            request.exchange,
            request.market_type,
            request.quantity,
            self._slippage_bps,
        )
        fill_price = _apply_slippage(base_price, request.side, effective_slippage)
        self._open_orders.add(order_id)
        result = ExecutionResult(
            order_id, OrderStatus.FILLED, request.quantity, fill_price, "paper fill"
        )

        # Persist state after order fill if persistence path is configured
        if self._state_persistence_path:
            self._export_trading_state()

        return result

    def cancel_all(self) -> int:
        """Cancel all open orders and return count of cancelled orders."""
        count_val = len(self._open_orders)
        self._open_orders.clear()
        return count_val

    def _load_trading_state(self) -> None:
        """Load positions and pending orders from persisted state."""
        if self._state_persistence_path is None:
            return
        try:
            positions, pending_orders = load_trading_state(self._state_persistence_path)
            # For paper executor, we primarily care about pending orders to avoid duplicates
            # In a full implementation, we would also restore positions
            # For now, we'll log that we loaded state
            _LOGGER.info(
                "Loaded trading state: %d positions, %d pending orders",
                len(positions),
                len(pending_orders),
            )
            # Note: PaperExecutor doesn't maintain position state, but OrderManager does
            # The positions would be handled by OrderManager.load_state()
        except Exception as exc:
            _LOGGER.warning("Failed to load trading state: %s", exc)

    def _export_trading_state(self) -> None:
        """Export current positions and pending orders for crash recovery."""
        if not self._state_persistence_path:
            return

        try:
            # PaperExecutor doesn't track positions, so export empty dict
            positions: dict[str, tuple[Decimal, Decimal]] = {}

            # Export open orders as pending orders
            pending_orders: dict[str, dict[str, str]] = {}
            for order_id in self._open_orders:
                pending_orders[order_id] = {
                    "status": OrderStatus.OPEN.value,
                    "executor": "paper",
                }

            # Export the state
            export_trading_state(
                positions=positions,
                pending_orders=pending_orders,
                output_path=self._state_persistence_path,
            )
            _LOGGER.info("Trading state exported for crash recovery")
        except Exception as exc:
            _LOGGER.error("Failed to export trading state: %s", exc)

    def close_order(self, order_id: str) -> bool:
        """Close a specific order by ID.

        Args:
            order_id: The order ID to close.

        Returns:
            True if order was found and closed, False otherwise.
        """
        if order_id in self._open_orders:
            self._open_orders.remove(order_id)
            return True
        return False
