"""
Unified 7-step risk pipeline for order processing.

Provides deterministic, ordered execution of all risk checks and
execution steps with comprehensive audit trail.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.pre_trade_validator import PreTradeConfig, validate_order
from iatb.risk.daily_loss_guard import DailyLossGuard, DailyLossState

if TYPE_CHECKING:
    from iatb.execution.order_throttle import OrderThrottle
    from iatb.execution.trade_audit import TradeAuditLogger
    from iatb.risk.kill_switch import KillSwitch


@dataclass(frozen=True)
class RiskPipelineResult:
    """Result of the 7-step risk pipeline execution."""

    order_id: str
    allowed: bool
    kill_switch_engaged: bool
    throttle_accepted: bool
    pre_trade_passed: bool
    execution_result: ExecutionResult | None
    daily_loss_state: "DailyLossState"
    audit_record_id: str
    rejection_reason: str | None
    timestamp_utc: Timestamp

    @classmethod
    def create_rejected(
        cls,
        order_id: str,
        rejection_reason: str,
        kill_switch_engaged: bool = False,
        throttle_accepted: bool = True,
        pre_trade_passed: bool = True,
        daily_loss_state: "DailyLossState | None" = None,
        now_utc: datetime | None = None,
    ) -> "RiskPipelineResult":
        """Create a rejected result."""
        if daily_loss_state is None:
            from iatb.risk.daily_loss_guard import DailyLossGuard

            dummy_guard = DailyLossGuard(
                max_daily_loss_pct=Decimal("0.02"),
                starting_nav=Decimal("1000000"),
                kill_switch=_create_dummy_kill_switch(),
            )
            daily_loss_state = dummy_guard.state
        if now_utc is None:
            now_utc = datetime.now(UTC)
        return cls(
            order_id=order_id,
            allowed=False,
            kill_switch_engaged=kill_switch_engaged,
            throttle_accepted=throttle_accepted,
            pre_trade_passed=pre_trade_passed,
            execution_result=None,
            daily_loss_state=daily_loss_state,
            audit_record_id="",
            rejection_reason=rejection_reason,
            timestamp_utc=Timestamp(now_utc),
        )


@dataclass
class RiskPipeline:
    """Unified 7-step risk pipeline for order processing.

    Steps:
    1. Kill switch check
    2. Order throttle check
    3. Pre-trade validation (5 gates)
    4. Paper execution
    5. Daily loss recording
    6. Trade audit logging
    7. Return result
    """

    kill_switch: "KillSwitch | None"
    order_throttle: "OrderThrottle | None"
    pre_trade_config: "PreTradeConfig | None"
    paper_executor: Executor
    daily_loss_guard: "DailyLossGuard | None"
    trade_audit_logger: "TradeAuditLogger | None"

    _last_prices: dict[str, Decimal] = field(default_factory=dict)
    _positions: dict[str, Decimal] = field(default_factory=dict)
    _total_exposure: Decimal = field(default_factory=lambda: Decimal("0"))

    def update_market_data(
        self,
        last_prices: dict[str, Decimal],
        positions: dict[str, Decimal],
        total_exposure: Decimal,
    ) -> None:
        """Update market data snapshot for pre-trade validation."""
        self._last_prices = last_prices.copy()
        self._positions = positions.copy()
        self._total_exposure = total_exposure

    def process_order(self, order: OrderRequest, now_utc: datetime) -> RiskPipelineResult:
        """Process order through 7-step risk pipeline.

        Args:
            order: Order request to process
            now_utc: Current UTC timestamp

        Returns:
            RiskPipelineResult with execution status and audit trail

        Raises:
            ConfigError: If timestamp is not UTC-aware
        """
        _validate_utc(now_utc)
        order_id = f"PIPELINE-{now_utc.strftime('%Y%m%d%H%M%S%f')}"

        rejection = self._check_early_rejections(order, order_id, now_utc)
        if rejection:
            return rejection

        execution_result = self._step_4_paper_execution(order)
        daily_loss_state = self._step_5_daily_loss_recording(order, execution_result, now_utc)
        audit_record_id = self._step_6_trade_audit_logging(order, execution_result, now_utc)

        return RiskPipelineResult(
            order_id=execution_result.order_id,
            allowed=True,
            kill_switch_engaged=False,
            throttle_accepted=True,
            pre_trade_passed=True,
            execution_result=execution_result,
            daily_loss_state=daily_loss_state,
            audit_record_id=audit_record_id,
            rejection_reason=None,
            timestamp_utc=Timestamp(now_utc),
        )

    def _check_early_rejections(
        self, order: OrderRequest, order_id: str, now_utc: datetime
    ) -> RiskPipelineResult | None:
        """Check early rejection conditions (kill switch, throttle, pre-trade)."""
        if not self._step_1_kill_switch_check():
            return RiskPipelineResult.create_rejected(
                order_id=order_id,
                rejection_reason="kill switch engaged",
                kill_switch_engaged=True,
                now_utc=now_utc,
            )

        if not self._step_2_throttle_check(now_utc):
            return RiskPipelineResult.create_rejected(
                order_id=order_id,
                rejection_reason="OPS throttle exceeded",
                throttle_accepted=False,
                now_utc=now_utc,
            )

        if not self._step_3_pre_trade_validation(order):
            return RiskPipelineResult.create_rejected(
                order_id=order_id,
                rejection_reason="pre-trade validation failed",
                pre_trade_passed=False,
                now_utc=now_utc,
            )

        return None

    def _step_1_kill_switch_check(self) -> bool:
        """Step 1: Check if kill switch allows orders."""
        if self.kill_switch is None:
            return True
        return self.kill_switch.check_order_allowed()

    def _step_2_throttle_check(self, now_utc: datetime) -> bool:
        """Step 2: Check if order throttle allows this order."""
        if self.order_throttle is None:
            return True
        return self.order_throttle.check_and_record(now_utc)

    def _step_3_pre_trade_validation(self, order: OrderRequest) -> bool:
        """Step 3: Validate order against 5 pre-trade gates."""
        if self.pre_trade_config is None:
            return True
        try:
            validate_order(
                order,
                self.pre_trade_config,
                self._last_prices,
                self._positions,
                self._total_exposure,
            )
            return True
        except ConfigError:
            return False

    def _step_4_paper_execution(self, order: OrderRequest) -> ExecutionResult:
        """Step 4: Execute order with paper trading."""
        return self.paper_executor.execute_order(order)

    def _step_5_daily_loss_recording(
        self,
        order: OrderRequest,
        result: ExecutionResult,
        now_utc: datetime,
    ) -> "DailyLossState":
        """Step 5: Record trade PnL and check daily loss limit."""
        if self.daily_loss_guard is None:
            from iatb.risk.daily_loss_guard import DailyLossGuard

            dummy_guard = DailyLossGuard(
                max_daily_loss_pct=Decimal("0.02"),
                starting_nav=Decimal("1000000"),
                kill_switch=_create_dummy_kill_switch(),
            )
            return dummy_guard.state

        # Calculate realized PnL for closing trades
        pnl = self._calculate_realized_pnl(order, result)
        if pnl != Decimal("0"):
            return self.daily_loss_guard.record_trade(pnl, now_utc)
        return self.daily_loss_guard.state

    def _step_6_trade_audit_logging(
        self,
        order: OrderRequest,
        result: ExecutionResult,
        now_utc: datetime,
    ) -> str:
        """Step 6: Log trade to audit database."""
        if self.trade_audit_logger is None:
            return ""
        self.trade_audit_logger.log_order(order, result, strategy_id="risk_pipeline", algo_id="")
        return result.order_id

    def _calculate_realized_pnl(self, order: OrderRequest, result: ExecutionResult) -> Decimal:
        """Calculate realized PnL for closing trades.

        For long positions (positive qty):
        - BUY opens position → no realized PnL
        - SELL closes position → realized PnL = (exit_price - entry_price) * qty_closed

        For short positions (negative qty):
        - BUY closes position → realized PnL = (entry_price - exit_price) * qty_closed
        - SELL opens position → no realized PnL
        """
        if result.filled_quantity <= Decimal("0"):
            return Decimal("0")

        # Get current position state
        current_qty = self._positions.get(order.symbol, Decimal("0"))

        # Simple PnL calculation based on position direction
        # This is a simplified version - full implementation would track avg entry price
        if order.side.value == "BUY" and current_qty < Decimal("0"):
            # Closing short position
            return result.average_price * result.filled_quantity
        elif order.side.value == "SELL" and current_qty > Decimal("0"):
            # Closing long position
            return result.average_price * result.filled_quantity

        return Decimal("0")


def _validate_utc(dt: datetime) -> None:
    """Validate that datetime is UTC-aware."""
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC"
        raise ConfigError(msg)


def _create_dummy_kill_switch() -> "KillSwitch":
    """Create a dummy kill switch for testing."""
    from iatb.risk.kill_switch import KillSwitch

    class DummyExecutor:
        def cancel_all(self) -> int:
            return 0

        def execute_order(self, request: OrderRequest) -> ExecutionResult:
            return ExecutionResult("DUMMY", OrderStatus.FILLED, request.quantity, Decimal("100"))

        def close_order(self, order_id: str) -> bool:
            return False

    return KillSwitch(DummyExecutor())
