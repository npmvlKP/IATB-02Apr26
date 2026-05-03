"""
Paper-trading executor with deterministic slippage simulation.
"""

import logging
from decimal import Decimal
from itertools import count
from pathlib import Path
from typing import Any, Final

from iatb.core.enums import OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.storage.backup import export_trading_state, load_trading_state

_LOGGER = logging.getLogger(__name__)


class PaperExecutor(Executor):
    """Default executor for safe simulation in non-live mode."""

    def __init__(
        self,
        slippage_bps: Decimal = Decimal("5"),
        state_persistence_path: Path | None = None,
        crash_recovery_mode: bool = False,
    ) -> None:
        if slippage_bps < Decimal("0"):
            msg = "slippage_bps cannot be negative"
            raise ConfigError(msg)
        self._slippage_bps = slippage_bps
        # Use itertools.count() for thread-safe counter
        self._counter: Final = count(start=1)
        self._open_orders: set[str] = set()
        self._crash_recovery_mode: bool = crash_recovery_mode
        self._state_persistence_path = state_persistence_path

        # Load trading state if persistence path is provided
        self._load_trading_state()

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        # Thread-safe counter using itertools.count()
        order_id = f"PAPER-{next(self._counter):06d}"
        base_price = request.price if request.price is not None else Decimal("100")
        fill_price = _apply_slippage(base_price, request.side, self._slippage_bps)
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
        count = len(self._open_orders)
        self._open_orders.clear()
        return count

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
            pending_orders: dict[str, dict[str, Any]] = {}
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


def _apply_slippage(base_price: Decimal, side: OrderSide, slippage_bps: Decimal) -> Decimal:
    slippage = (slippage_bps / Decimal("10000")) * base_price
    if side == OrderSide.BUY:
        return base_price + slippage
    return max(Decimal("0"), base_price - slippage)
