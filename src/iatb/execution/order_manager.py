"""
Order lifecycle manager with safety pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest

if TYPE_CHECKING:
    from iatb.execution.order_throttle import OrderThrottle
    from iatb.execution.pre_trade_validator import PreTradeConfig
    from iatb.execution.trade_audit import TradeAuditLogger
    from iatb.risk.daily_loss_guard import DailyLossGuard
    from iatb.risk.kill_switch import KillSwitch


class OrderManager:
    """Tracks order lifecycle with kill switch, validation, and audit."""

    def __init__(
        self,
        executor: Executor,
        heartbeat_timeout_seconds: int = 30,
        kill_switch: KillSwitch | None = None,
        pre_trade_config: PreTradeConfig | None = None,
        daily_loss_guard: DailyLossGuard | None = None,
        audit_logger: TradeAuditLogger | None = None,
        order_throttle: OrderThrottle | None = None,
        algo_id: str = "",
    ) -> None:
        if heartbeat_timeout_seconds <= 0:
            msg = "heartbeat_timeout_seconds must be positive"
            raise ConfigError(msg)
        self._executor = executor
        self._heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)
        self._last_heartbeat_utc: datetime | None = None
        self._order_status: dict[str, OrderStatus] = {}
        self._kill_switch = kill_switch
        self._pre_trade_config = pre_trade_config
        self._daily_loss_guard = daily_loss_guard
        self._audit_logger = audit_logger
        self._order_throttle = order_throttle
        self._algo_id = algo_id
        self._last_prices: dict[str, Decimal] = {}
        self._positions: dict[str, Decimal] = {}
        self._total_exposure = Decimal("0")
        # Position tracking for PnL: symbol -> (position_qty, avg_entry_price)
        self._position_state: dict[str, tuple[Decimal, Decimal]] = {}

    def update_market_data(
        self,
        last_prices: dict[str, Decimal],
        positions: dict[str, Decimal],
        total_exposure: Decimal,
    ) -> None:
        """Refresh market state for pre-trade validation."""
        self._last_prices = last_prices
        self._positions = positions
        self._total_exposure = total_exposure

    def receive_heartbeat(self, heartbeat_utc: datetime) -> None:
        if heartbeat_utc.tzinfo != UTC:
            msg = "heartbeat_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        self._last_heartbeat_utc = heartbeat_utc

    def place_order(
        self,
        request: OrderRequest,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> ExecutionResult:
        """7-step safety pipeline: kill→throttle→validate→execute→loss→audit→return."""
        self._gate_kill_switch()
        self._gate_throttle()
        self._gate_pre_trade(request)
        result = self._executor.execute_order(request)
        self._order_status[result.order_id] = result.status
        self._record_pnl(request, result)
        effective_algo_id = algo_id or self._algo_id
        self._audit(request, result, strategy_id, effective_algo_id)
        return result

    def _gate_kill_switch(self) -> None:
        if self._kill_switch and not self._kill_switch.check_order_allowed():
            msg = "order rejected: kill switch engaged"
            raise ConfigError(msg)

    def _gate_throttle(self) -> None:
        if self._order_throttle:
            now = datetime.now(UTC)
            if not self._order_throttle.check_and_record(now):
                msg = "order rejected: OPS throttle exceeded"
                raise ConfigError(msg)

    def _gate_pre_trade(self, request: OrderRequest) -> None:
        if self._pre_trade_config:
            from iatb.execution.pre_trade_validator import validate_order

            validate_order(
                request,
                self._pre_trade_config,
                self._last_prices,
                self._positions,
                self._total_exposure,
            )

    def _record_pnl(self, request: OrderRequest, result: ExecutionResult) -> None:
        """Record realized PnL only on closing trades.

        For long positions (positive qty):
        - BUY opens position → no realized PnL
        - SELL closes position → realized PnL = (exit_price - entry_price) * qty_closed

        For short positions (negative qty):
        - BUY closes position → realized PnL = (entry_price - exit_price) * qty_closed
        - SELL opens position → no realized PnL
        """
        if not self._daily_loss_guard or result.filled_quantity <= Decimal("0"):
            return

        symbol = request.symbol
        fill_qty = result.filled_quantity
        fill_price = result.average_price

        # Get current position state
        current_qty, avg_entry_price = self._position_state.get(
            symbol, (Decimal("0"), Decimal("0"))
        )

        now = datetime.now(UTC)

        if request.side == OrderSide.BUY:
            # BUY order
            if current_qty < Decimal("0"):
                # Closing short position - realize PnL
                # For short: PnL = (entry - exit) * qty_closed
                qty_to_close = min(fill_qty, abs(current_qty))
                realized_pnl = (avg_entry_price - fill_price) * qty_to_close
                self._daily_loss_guard.record_trade(realized_pnl, now)

                # Update remaining short position
                remaining_short = -current_qty - qty_to_close
                if remaining_short > Decimal("0"):
                    # Still short, keep avg entry price
                    self._position_state[symbol] = (-remaining_short, avg_entry_price)
                else:
                    # Position closed or flipped to long
                    qty_opening_long = fill_qty - qty_to_close
                    if qty_opening_long > Decimal("0"):
                        # New long position at fill price
                        self._position_state[symbol] = (qty_opening_long, fill_price)
                    else:
                        # Flat position
                        self._position_state[symbol] = (Decimal("0"), Decimal("0"))
            else:
                # Opening or adding to long position - no realized PnL
                # Calculate weighted average entry price
                total_cost = (current_qty * avg_entry_price) + (fill_qty * fill_price)
                new_qty = current_qty + fill_qty
                new_avg = total_cost / new_qty
                self._position_state[symbol] = (new_qty, new_avg)

        elif request.side == OrderSide.SELL:
            # SELL order
            if current_qty > Decimal("0"):
                # Closing long position - realize PnL
                # For long: PnL = (exit - entry) * qty_closed
                qty_to_close = min(fill_qty, current_qty)
                realized_pnl = (fill_price - avg_entry_price) * qty_to_close
                self._daily_loss_guard.record_trade(realized_pnl, now)

                # Update remaining long position
                remaining_long = current_qty - qty_to_close
                if remaining_long > Decimal("0"):
                    # Still long, keep avg entry price
                    self._position_state[symbol] = (remaining_long, avg_entry_price)
                else:
                    # Position closed or flipped to short
                    qty_opening_short = fill_qty - qty_to_close
                    if qty_opening_short > Decimal("0"):
                        # New short position at fill price
                        self._position_state[symbol] = (-qty_opening_short, fill_price)
                    else:
                        # Flat position
                        self._position_state[symbol] = (Decimal("0"), Decimal("0"))
            else:
                # Opening or adding to short position - no realized PnL
                # Calculate weighted average entry price for short
                abs_current_qty = abs(current_qty)
                total_cost = (abs_current_qty * avg_entry_price) + (fill_qty * fill_price)
                new_abs_qty = abs_current_qty + fill_qty
                new_avg = total_cost / new_abs_qty
                self._position_state[symbol] = (-new_abs_qty, new_avg)

    def _audit(
        self,
        request: OrderRequest,
        result: ExecutionResult,
        strategy_id: str,
        algo_id: str,
    ) -> None:
        if self._audit_logger:
            self._audit_logger.log_order(request, result, strategy_id, algo_id)

    def check_dead_man_switch(self, now_utc: datetime) -> bool:
        if now_utc.tzinfo != UTC:
            msg = "now_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        if self._last_heartbeat_utc is None:
            return self._trigger_cancel_all()
        stale = now_utc - self._last_heartbeat_utc > self._heartbeat_timeout
        return self._trigger_cancel_all() if stale else False

    def get_order_status(self, order_id: str) -> OrderStatus | None:
        return self._order_status.get(order_id)

    def _trigger_cancel_all(self) -> bool:
        cancelled_count = self._executor.cancel_all()
        if cancelled_count > 0:
            for key in self._order_status:
                if self._order_status[key] in {OrderStatus.OPEN, OrderStatus.PENDING}:
                    self._order_status[key] = OrderStatus.CANCELLED
        return True
