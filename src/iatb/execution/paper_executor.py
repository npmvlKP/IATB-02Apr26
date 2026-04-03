"""
Paper-trading executor with deterministic slippage simulation.
"""

from decimal import Decimal

from iatb.core.enums import OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest


class PaperExecutor(Executor):
    """Default executor for safe simulation in non-live mode."""

    def __init__(self, slippage_bps: Decimal = Decimal("5")) -> None:
        if slippage_bps < Decimal("0"):
            msg = "slippage_bps cannot be negative"
            raise ConfigError(msg)
        self._slippage_bps = slippage_bps
        self._counter = 0
        self._open_orders: set[str] = set()

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self._counter += 1
        order_id = f"PAPER-{self._counter:06d}"
        base_price = request.price if request.price is not None else Decimal("100")
        fill_price = _apply_slippage(base_price, request.side, self._slippage_bps)
        self._open_orders.add(order_id)
        self._open_orders.remove(order_id)
        return ExecutionResult(
            order_id, OrderStatus.FILLED, request.quantity, fill_price, "paper fill"
        )

    def cancel_all(self) -> int:
        count = len(self._open_orders)
        self._open_orders.clear()
        return count


def _apply_slippage(base_price: Decimal, side: OrderSide, slippage_bps: Decimal) -> Decimal:
    slippage = (slippage_bps / Decimal("10000")) * base_price
    if side == OrderSide.BUY:
        return base_price + slippage
    return max(Decimal("0"), base_price - slippage)
