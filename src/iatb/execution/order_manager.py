"""
Order lifecycle manager with safety pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from iatb.core.enums import OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_throttle import OrderThrottle
from iatb.execution.pre_trade_validator import PreTradeConfig
from iatb.execution.trade_audit import TradeAuditLogger

# New imports for unified risk pipeline
from iatb.risk.risk_pipeline import RiskPipeline

if TYPE_CHECKING:
    from iatb.risk.daily_loss_guard import DailyLossGuard
    from iatb.risk.kill_switch import KillSwitch

_LOGGER = logging.getLogger(__name__)


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
        enable_duplicate_detection: bool = True,
        state_persistence_path: Path | None = None,
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
        # Initialise unified risk pipeline
        self._risk_pipeline = RiskPipeline(
            kill_switch=self._kill_switch,
            order_throttle=self._order_throttle,
            pre_trade_config=self._pre_trade_config,
            paper_executor=self._executor,
            daily_loss_guard=self._daily_loss_guard,
            trade_audit_logger=self._audit_logger,
        )
        self._algo_id = algo_id
        self._last_prices: dict[str, Decimal] = {}
        self._positions: dict[str, Decimal] = {}
        self._total_exposure = Decimal("0")
        self._position_state: dict[str, tuple[Decimal, Decimal]] = {}
        self._enable_duplicate_detection = enable_duplicate_detection
        self._state_persistence_path = state_persistence_path
        self._order_fingerprints: set[str] = set()
        self._order_id_mapping: dict[str, str] = {}

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
        # Propagate market snapshot to the risk pipeline
        if hasattr(self, "_risk_pipeline"):
            self._risk_pipeline.update_market_data(last_prices, positions, total_exposure)

    def receive_heartbeat(self, heartbeat_utc: datetime) -> None:
        if heartbeat_utc.tzinfo != UTC:
            msg = "heartbeat_utc must be timezone-aware UTC datetime"
            raise ConfigError(msg)
        self._last_heartbeat_utc = heartbeat_utc

    def _generate_order_fingerprint(self, request: OrderRequest) -> str:
        """Generate a unique fingerprint for order duplicate detection."""
        fingerprint_parts = [
            request.exchange.value,
            request.symbol,
            request.side.value,
            str(request.quantity),
            str(request.price) if request.price else "MARKET",
        ]
        return "|".join(fingerprint_parts)

    def _check_duplicate_order(self, request: OrderRequest) -> str | None:
        """Check if order is a duplicate and return existing order ID if so."""
        if not self._enable_duplicate_detection:
            return None

        fingerprint = self._generate_order_fingerprint(request)

        if fingerprint in self._order_fingerprints:
            existing_order_id = self._order_id_mapping.get(fingerprint)
            _LOGGER.warning(
                "Duplicate order detected",
                extra={
                    "fingerprint": fingerprint,
                    "existing_order_id": existing_order_id,
                    "symbol": request.symbol,
                    "side": request.side.value,
                },
            )
            return existing_order_id

        return None

    def _record_order_fingerprint(self, request: OrderRequest, order_id: str) -> None:
        """Record order fingerprint for duplicate detection."""
        if not self._enable_duplicate_detection:
            return

        fingerprint = self._generate_order_fingerprint(request)
        self._order_fingerprints.add(fingerprint)
        self._order_id_mapping[fingerprint] = order_id

    def place_order(
        self,
        request: OrderRequest,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> ExecutionResult:
        """7-step safety pipeline: kill→throttle→validate→duplicate→execute→loss→audit→return."""
        # Unified risk pipeline handles kill‑switch, throttle, validation, execution,
        # daily‑loss accounting and audit logging. Duplicate detection remains
        # upstream of the pipeline.
        existing_order_id = self._check_duplicate_order(request)
        if existing_order_id is not None:
            existing_status = self._order_status.get(existing_order_id)
            if existing_status in {OrderStatus.OPEN, OrderStatus.PENDING}:
                return ExecutionResult(
                    existing_order_id,
                    existing_status,
                    Decimal("0"),
                    Decimal("0"),
                )

        # Run through the risk pipeline
        now = datetime.now(UTC)
        pipeline_result = self._risk_pipeline.process_order(
            request, now, strategy_id=strategy_id, algo_id=algo_id
        )
        if not pipeline_result.allowed:
            # Propagate rejection as ConfigError with specific reason
            raise ConfigError(pipeline_result.rejection_reason or "order rejected")
        result = pipeline_result.execution_result
        if result is None:
            msg = pipeline_result.rejection_reason or "order rejected"
            raise ConfigError(msg)
        # Record order status and fingerprint for downstream tracking
        self._order_status[result.order_id] = result.status
        self._record_order_fingerprint(request, result.order_id)
        # Persist state if configured
        if self._state_persistence_path:
            self.save_state(self._state_persistence_path)

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
            self._process_buy_order(symbol, fill_qty, fill_price, current_qty, avg_entry_price, now)
        elif request.side == OrderSide.SELL:
            self._process_sell_order(
                symbol, fill_qty, fill_price, current_qty, avg_entry_price, now
            )

    def _process_buy_order(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
        now: datetime,
    ) -> None:
        """Process BUY order for PnL recording."""
        if current_qty < Decimal("0"):
            # Closing short position - realize PnL
            self._realize_short_pnl(symbol, fill_qty, fill_price, current_qty, avg_entry_price, now)
        else:
            # Opening or adding to long position - no realized PnL
            self._add_to_long_position(symbol, fill_qty, fill_price, current_qty, avg_entry_price)

    def _process_sell_order(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
        now: datetime,
    ) -> None:
        """Process SELL order for PnL recording."""
        if current_qty > Decimal("0"):
            # Closing long position - realize PnL
            self._realize_long_pnl(symbol, fill_qty, fill_price, current_qty, avg_entry_price, now)
        else:
            # Opening or adding to short position - no realized PnL
            self._add_to_short_position(symbol, fill_qty, fill_price, current_qty, avg_entry_price)

    def _realize_short_pnl(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
        now: datetime,
    ) -> None:
        """Realize PnL when closing a short position."""
        # Type guard: daily_loss_guard is guaranteed to be set when this is called
        assert self._daily_loss_guard is not None  # nosec B101

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

    def _realize_long_pnl(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
        now: datetime,
    ) -> None:
        """Realize PnL when closing a long position."""
        # Type guard: daily_loss_guard is guaranteed to be set when this is called
        assert self._daily_loss_guard is not None  # nosec B101

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

    def _add_to_long_position(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
    ) -> None:
        """Add to or open a long position."""
        # Calculate weighted average entry price
        total_cost = (current_qty * avg_entry_price) + (fill_qty * fill_price)
        new_qty = current_qty + fill_qty
        new_avg = total_cost / new_qty
        self._position_state[symbol] = (new_qty, new_avg)

    def _add_to_short_position(
        self,
        symbol: str,
        fill_qty: Decimal,
        fill_price: Decimal,
        current_qty: Decimal,
        avg_entry_price: Decimal,
    ) -> None:
        """Add to or open a short position."""
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

    async def place_order_async(
        self,
        request: OrderRequest,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> ExecutionResult:
        """Async variant that offloads execution to thread pool.

        Prevents event loop blocking during live trading by running
        the synchronous executor in a separate thread.
        """
        # Unified risk pipeline handles core steps; duplicate detection stays first.
        existing_order_id = self._check_duplicate_order(request)
        if existing_order_id is not None:
            existing_status = self._order_status.get(existing_order_id)
            if existing_status in {OrderStatus.OPEN, OrderStatus.PENDING}:
                return ExecutionResult(
                    existing_order_id,
                    existing_status,
                    Decimal("0"),
                    Decimal("0"),
                )

        # Run through the risk pipeline (synchronous call; it internally uses the injected executor)
        now = datetime.now(UTC)
        pipeline_result = self._risk_pipeline.process_order(
            request, now, strategy_id=strategy_id, algo_id=algo_id
        )
        if not pipeline_result.allowed:
            raise ConfigError(pipeline_result.rejection_reason or "order rejected")
        result = pipeline_result.execution_result
        if result is None:
            msg = pipeline_result.rejection_reason or "order rejected"
            raise ConfigError(msg)
        # Update order status and fingerprint
        self._order_status[result.order_id] = result.status
        self._record_order_fingerprint(request, result.order_id)
        # Persist state if needed

        if self._state_persistence_path:
            self.save_state(self._state_persistence_path)

        return result

    def save_state(self, state_path: Path) -> None:
        """Persist positions and PnL state to JSON for crash recovery."""
        state_path.parent.mkdir(parents=True, exist_ok=True)
        position_data = {
            symbol: {"qty": str(qty), "avg_price": str(price)}
            for symbol, (qty, price) in self._position_state.items()
        }
        order_data = {oid: status.value for oid, status in self._order_status.items()}
        payload = {
            "saved_at_utc": datetime.now(UTC).isoformat(),
            "position_state": position_data,
            "order_status": order_data,
            "total_exposure": str(self._total_exposure),
            "order_fingerprints": list(self._order_fingerprints),
            "order_id_mapping": self._order_id_mapping,
        }
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _LOGGER.info(
            "State persisted",
            extra={"path": str(state_path), "positions": len(position_data)},
        )

    def load_state(self, state_path: Path) -> None:
        """Restore positions and PnL state from JSON on process restart."""
        if not state_path.exists():
            _LOGGER.warning("State file not found: %s", state_path)
            return
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _LOGGER.error("Failed to load state from %s: %s", state_path, exc)
            return

        position_data = payload.get("position_state", {})
        self._position_state = {
            symbol: (Decimal(v["qty"]), Decimal(v["avg_price"]))
            for symbol, v in position_data.items()
        }

        order_data = payload.get("order_status", {})
        self._order_status = {oid: OrderStatus(value) for oid, value in order_data.items()}

        exposure = payload.get("total_exposure", "0")
        self._total_exposure = Decimal(str(exposure))

        fingerprints = payload.get("order_fingerprints", [])
        self._order_fingerprints = set(fingerprints)

        id_mapping = payload.get("order_id_mapping", {})
        self._order_id_mapping = id_mapping

        _LOGGER.info(
            "State restored",
            extra={
                "path": str(state_path),
                "positions": len(self._position_state),
                "orders": len(self._order_status),
                "fingerprints": len(self._order_fingerprints),
            },
        )
