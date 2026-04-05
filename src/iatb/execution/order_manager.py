"""
Order lifecycle manager with safety pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import OrderStatus
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
        if self._daily_loss_guard and result.filled_quantity > Decimal("0"):
            entry_price = request.price or self._last_prices.get(
                request.symbol,
                result.average_price,
            )
            pnl = (result.average_price - entry_price) * result.filled_quantity
            now = datetime.now(UTC)
            self._daily_loss_guard.record_trade(pnl, now)

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
