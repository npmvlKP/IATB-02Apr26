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
from decimal import Decimal
from itertools import count as _itertools_count
from pathlib import Path
from typing import Any

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
    if quantity <= 0:
        return _VOLUME_ADJUSTMENT_MAX_FACTOR

    try:
        log_val = (quantity + Decimal("1")).ln() / Decimal("10").ln()
    except Exception:
        log_val = Decimal("0")
    factor = Decimal("1") / (Decimal("1") + _VOLUME_ADJUSTMENT_MULTIPLIER * log_val)

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
    2. Volume-adjustment factor (log10, bounded [0.5, 1.0])
    3. Return total bps
    """
    if override_bps is not None:
        return override_bps

    base_bps = _resolve_base_slippage(exchange, market_type)
    volume_factor = _volume_adjustment_factor(quantity)
    return base_bps * volume_factor


def apply_slippage(
    base_price: Decimal,
    bps: Decimal,
    side: OrderSide,
) -> Decimal:
    """Apply the computed slippage to a base price.

    BUY  -> fill_price = base_price + impact
    SELL -> fill_price = base_price - impact (clamped to >= 0)
    """
    impact = (bps / Decimal("10000")) * base_price
    if side == OrderSide.BUY:
        return base_price + impact
    # SELL
    result = base_price - impact
    if result < Decimal("0"):
        return Decimal("0")
    return result


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
_LIQUID_TARGET_SLIPPAGE_BPS: Decimal = Decimal("5")
_ILLIQUID_TARGET_SLIPPAGE_BPS: Decimal = Decimal("10")
_VALIDATION_TOLERANCE_BPS: Decimal = Decimal("2")


def is_liquid_instrument(
    symbol: str,
    exchange: Exchange,
    market_type: MarketType,
) -> bool:
    """Return whether an instrument is considered liquid."""
    # NSE spot instruments are generally liquid
    key = (exchange, market_type)
    if key in _EXCHANGE_BASE_SLIPPAGE:
        base = _EXCHANGE_BASE_SLIPPAGE[key]
        return base <= Decimal("3")
    return False


def validate_fill_against_market(
    filled_price: Decimal,
    market_price: Decimal,
    side: OrderSide,
    base_slippage_bps: Decimal,
) -> bool:
    """Validate that a paper fill is within acceptable slippage bounds."""
    tolerance = base_slippage_bps + _VALIDATION_TOLERANCE_BPS
    if market_price == Decimal("0"):
        return True  # Can't validate against zero market price
    if side == OrderSide.BUY:
        max_price = market_price * (Decimal("1") + tolerance / Decimal("10000"))
        return filled_price <= max_price
    # SELL
    min_price = market_price * (Decimal("1") - tolerance / Decimal("10000"))
    return filled_price >= min_price


# ---------------------------------------------------------------------------
# PaperExecutor implementation
# ---------------------------------------------------------------------------


class PaperExecutor(Executor):
    """Default executor for safe simulation in non-live mode.

    * Uses the deterministic slippage model above.
    * Optionally persists / restores state via ``export_trading_state`` /
    ``load_trading_state`` for crash-recovery.
    * Thread-safe via internal ``count``-based order-id generation.
    """

    _order_id_counter: Any
    _positions: dict[str, tuple[Decimal, Decimal]]
    _open_orders: dict[str, dict[str, Any]]

    _slippage_override_bps: Decimal | None
    """If set, used directly instead of the deterministic model."""

    def __init__(
        self,
        *,
        slippage_bps: Decimal | None = None,
        crash_recovery_mode: bool = False,
        state_file: str | None = None,
        state_persistence_path: Path | str | None = None,
    ) -> None:
        if slippage_bps is not None and slippage_bps < Decimal("0"):
            msg = "slippage_bps cannot be negative"
            raise ConfigError(msg)

        self._order_id_counter = _itertools_count(start=1)
        self._positions: dict[str, tuple[Decimal, Decimal]] = {}
        self._open_orders: dict[str, dict[str, Any]] = {}
        self._slippage_override_bps = slippage_bps
        self._crash_recovery_mode = crash_recovery_mode
        self._state_persistence_path: Path | None = (
            Path(state_persistence_path) if state_persistence_path is not None else None
        )
        self._state_file = (
            str(self._state_persistence_path)
            if self._state_persistence_path is not None
            else state_file
        )

        if self._state_persistence_path is not None:
            self._restore_state(self._state_persistence_path)
        elif self._state_file is not None:
            self._restore_state(Path(self._state_file))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _restore_state(self, path: Path) -> None:
        """Load positions and pending orders from a persisted state."""
        if not path.exists():
            _LOGGER.warning("State file not found: %s", path)
            return
        try:
            positions, pending_orders = load_trading_state(path)
            self._positions = positions
            self._open_orders = pending_orders
        except Exception as exc:
            _LOGGER.error("Failed to restore state from %s: %s", path, exc)

    def _persist_state(self, path: Path) -> None:
        """Persist current positions and pending orders."""
        export_trading_state(
            positions=self._positions,
            pending_orders=self._open_orders,
            output_path=path,
        )

    def _next_order_id(self) -> str:
        """Generate a unique order id."""
        return f"PAPER-{next(self._order_id_counter):06d}"

    # ------------------------------------------------------------------
    # Public API (Executor interface)
    # ------------------------------------------------------------------
    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        """Simulate execution with deterministic slippage."""
        order_id = self._next_order_id()
        bps = _compute_slippage_bps(
            exchange=request.exchange,
            market_type=request.market_type,
            quantity=request.quantity,
            override_bps=self._slippage_override_bps,
        )
        base_price = request.price if request.price is not None else Decimal("100")
        fill_price = apply_slippage(base_price=base_price, bps=bps, side=request.side)
        self._update_positions(request.symbol, request.side, request.quantity, fill_price)
        self._open_orders[order_id] = {
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "price": fill_price,
            "status": OrderStatus.FILLED,
        }
        self._maybe_persist_state()
        return ExecutionResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=fill_price,
        )

    def _update_positions(
        self, symbol: str, side: OrderSide, quantity: Decimal, fill_price: Decimal
    ) -> None:
        """Update internal position book after a fill."""
        if side == OrderSide.BUY:
            current_qty, current_avg = self._positions.get(symbol, (Decimal("0"), Decimal("0")))
            new_qty = current_qty + quantity
            new_avg = (
                ((current_qty * current_avg) + (quantity * fill_price)) / new_qty
                if new_qty > Decimal("0")
                else fill_price
            )
            self._positions[symbol] = (new_qty, new_avg)
        else:
            current_qty, current_avg = self._positions.get(symbol, (Decimal("0"), Decimal("0")))
            new_qty = current_qty - quantity if current_qty > quantity else Decimal("0")
            self._positions[symbol] = (
                (new_qty, current_avg) if new_qty > Decimal("0") else (Decimal("0"), Decimal("0"))
            )

    def _maybe_persist_state(self) -> None:
        """Persist state to disk if a persistence path is configured."""
        persistence_path = self._state_persistence_path or (
            Path(self._state_file) if self._state_file else None
        )
        if persistence_path is not None:
            self._persist_state(persistence_path)

    def cancel_all(self) -> int:
        """Cancel all pending orders (simplified for paper trading)."""
        # In paper trading, orders fill immediately; nothing to cancel
        count = len(self._open_orders)
        self._open_orders.clear()
        return count

    def close_order(self, order_id: str) -> bool:
        """Close an order (simplified for paper trading)."""
        # In paper trading, orders fill immediately; nothing to close
        if order_id in self._open_orders:
            del self._open_orders[order_id]
            return True
        return False

    def get_positions(self) -> dict[str, tuple[Decimal, Decimal]]:
        """Return current positions."""
        return dict(self._positions)
