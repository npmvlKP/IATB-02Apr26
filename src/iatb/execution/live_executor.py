"""
Live trading executor with real order routing through BrokerInterface.

Provides:
- Real order placement via BrokerInterface
- Slippage protection (max deviation from expected price)
- Order confirmation tracking with timeout
- Partial fill handling
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any

from iatb.broker.base import (
    BrokerInterface,
    ProductType,
    TransactionType,
)
from iatb.broker.base import (
    Exchange as BrokerExchange,
)
from iatb.broker.base import (
    Order as BrokerOrder,
)
from iatb.broker.base import (
    OrderStatus as BrokerOrderStatus,
)
from iatb.broker.base import (
    OrderType as BrokerOrderType,
)
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ExecutionError
from iatb.execution.base import ExecutionResult, Executor, OrderRequest

_LOGGER = logging.getLogger(__name__)

# Default configuration values
DEFAULT_CONFIRMATION_TIMEOUT_SECONDS: int = 30
# API boundary: timing parameter, not financial calculation
DEFAULT_CONFIRMATION_POLL_INTERVAL_SECONDS: float = 0.5
DEFAULT_SLIPPAGE_TOLERANCE_BPS: Decimal = Decimal("20")  # 0.20%


class LiveExecutor(Executor):
    """Live trading executor with real order routing.

    Routes orders through BrokerInterface with built-in protections:
    - Slippage protection: Rejects fills exceeding tolerance
    - Order confirmation: Polls until fill or timeout
    - Partial fill handling: Tracks cumulative fills

    Example:
        broker = ZerodhaBroker(token_manager=token_manager)
        await broker.authenticate()

        executor = LiveExecutor(broker=broker)
        result = executor.execute_order(
            OrderRequest(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=Decimal("10"),
                order_type=OrderType.MARKET
            )
        )
    """

    def __init__(
        self,
        *,
        broker: BrokerInterface,
        confirmation_timeout_seconds: int = DEFAULT_CONFIRMATION_TIMEOUT_SECONDS,
        # API boundary: timing parameter, not financial
        confirmation_poll_interval_seconds: float = DEFAULT_CONFIRMATION_POLL_INTERVAL_SECONDS,
        slippage_tolerance_bps: Decimal = DEFAULT_SLIPPAGE_TOLERANCE_BPS,
    ) -> None:
        """Initialize live executor.

        Args:
            broker: Broker interface instance for order routing.
            confirmation_timeout_seconds: Max seconds to wait for order confirmation.
            confirmation_poll_interval_seconds: Poll interval for order status.
            slippage_tolerance_bps: Max slippage tolerance in basis points.

        Raises:
            ValueError: If broker is None or parameters invalid.
        """
        if not broker:
            msg = "broker is required"
            raise ValueError(msg)
        if confirmation_timeout_seconds <= 0:
            msg = "confirmation_timeout_seconds must be positive"
            raise ValueError(msg)
        if confirmation_poll_interval_seconds <= 0:
            msg = "confirmation_poll_interval_seconds must be positive"
            raise ValueError(msg)
        if slippage_tolerance_bps < Decimal("0"):
            msg = "slippage_tolerance_bps cannot be negative"
            raise ValueError(msg)

        self._broker = broker
        self._confirmation_timeout_seconds = confirmation_timeout_seconds
        self._confirmation_poll_interval = confirmation_poll_interval_seconds
        self._slippage_tolerance_bps = slippage_tolerance_bps
        self._open_orders: set[str] = set()

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        """Execute order through broker with protections.

        Args:
            request: Order request details.

        Returns:
            ExecutionResult with order details.

        Raises:
            ExecutionError: If order execution fails.
            ConfigError: If slippage exceeds tolerance.
        """
        try:
            result = asyncio.run(self._execute_order_async(request))
            return result
        except asyncio.TimeoutError as e:
            msg = f"Order confirmation timeout after {self._confirmation_timeout_seconds}s"
            raise ExecutionError(msg) from e
        except Exception as e:
            msg = f"Order execution failed: {e!s}"
            raise ExecutionError(msg) from e

    async def _execute_order_async(self, request: OrderRequest) -> ExecutionResult:
        """Execute order asynchronously through broker.

        Args:
            request: Order request details.

        Returns:
            ExecutionResult with order details.
        """
        # Convert to broker types
        broker_request = self._convert_request_to_broker(request)

        # Place order with broker
        broker_order = await self._broker.place_order(**broker_request)
        self._open_orders.add(broker_order.order_id)

        # Wait for order confirmation/fill
        confirmed_order = await self._wait_for_confirmation(broker_order.order_id)

        # Check slippage if we have expected price
        if request.price is not None:
            self._validate_slippage(
                expected_price=request.price,
                filled_price=confirmed_order.average_price,
                side=request.side,
            )

        # Convert to ExecutionResult
        result = self._convert_broker_order_to_result(confirmed_order)
        return result

    def _convert_request_to_broker(self, request: OrderRequest) -> dict[str, Any]:
        """Convert OrderRequest to broker parameters.

        Args:
            request: Order request from core layer.

        Returns:
            Dictionary of broker-compatible parameters.
        """
        broker_exchange = self._map_exchange(request.exchange)
        broker_transaction_type = self._map_side(request.side)
        broker_order_type = self._map_order_type(request.order_type)

        params: dict[str, Any] = {
            "symbol": request.symbol,
            "exchange": broker_exchange,
            "transaction_type": broker_transaction_type,
            "order_type": broker_order_type,
            "quantity": int(request.quantity),
            "product_type": ProductType.INTRADAY,
        }

        if request.price is not None:
            params["price"] = request.price

        return params

    @staticmethod
    def _map_exchange(exchange: Exchange) -> BrokerExchange:
        """Map core Exchange enum to broker Exchange enum.

        Args:
            exchange: Core exchange enum.

        Returns:
            Broker exchange enum.
        """
        exchange_map = {
            Exchange.NSE: BrokerExchange.NSE,
            Exchange.BSE: BrokerExchange.BSE,
            Exchange.MCX: BrokerExchange.MCX,
            Exchange.CDS: BrokerExchange.MCX,  # Fallback
            Exchange.BINANCE: BrokerExchange.MCX,  # Fallback
            Exchange.COINDCX: BrokerExchange.MCX,  # Fallback
        }
        return exchange_map.get(exchange, BrokerExchange.NSE)

    @staticmethod
    def _map_side(side: OrderSide) -> TransactionType:
        """Map OrderSide to TransactionType.

        Args:
            side: Core order side.

        Returns:
            Broker transaction type.
        """
        side_map = {
            OrderSide.BUY: TransactionType.BUY,
            OrderSide.SELL: TransactionType.SELL,
        }
        return side_map[side]

    @staticmethod
    def _map_order_type(order_type: OrderType) -> BrokerOrderType:
        """Map core OrderType to broker OrderType.

        Args:
            order_type: Core order type.

        Returns:
            Broker order type.
        """
        type_map = {
            OrderType.MARKET: BrokerOrderType.MARKET,
            OrderType.LIMIT: BrokerOrderType.LIMIT,
            OrderType.STOP_LOSS: BrokerOrderType.STOP_LOSS,
            OrderType.STOP_LOSS_MARKET: BrokerOrderType.STOP_LOSS_MARKET,
        }
        return type_map[order_type]

    @staticmethod
    def _map_broker_status(broker_status: BrokerOrderStatus) -> OrderStatus:
        """Map broker OrderStatus to core OrderStatus.

        Args:
            broker_status: Broker order status.

        Returns:
            Core order status.
        """
        status_map = {
            BrokerOrderStatus.PENDING: OrderStatus.PENDING,
            BrokerOrderStatus.OPEN: OrderStatus.OPEN,
            BrokerOrderStatus.COMPLETE: OrderStatus.FILLED,
            BrokerOrderStatus.REJECTED: OrderStatus.REJECTED,
            BrokerOrderStatus.CANCELLED: OrderStatus.CANCELLED,
            BrokerOrderStatus.EXPIRED: OrderStatus.EXPIRED,
            BrokerOrderStatus.TRIGGER_PENDING: OrderStatus.PENDING,
            BrokerOrderStatus.VALIDATION_PENDING: OrderStatus.PENDING,
        }
        return status_map.get(broker_status, OrderStatus.PENDING)

    def _is_terminal_status(self, order: BrokerOrder) -> bool:
        """Check if order status is terminal.

        Args:
            order: Broker order to check.

        Returns:
            True if order is in terminal state.
        """
        return order.status in (
            BrokerOrderStatus.COMPLETE,
            BrokerOrderStatus.REJECTED,
            BrokerOrderStatus.CANCELLED,
            BrokerOrderStatus.EXPIRED,
        )

    def _has_partial_fill(self, order: BrokerOrder) -> bool:
        """Check if order has partial fill.

        Args:
            order: Broker order to check.

        Returns:
            True if order has partial fill.
        """
        return order.filled_quantity > 0 and order.filled_quantity < order.quantity

    def _check_order_status(self, order: BrokerOrder, order_id: str) -> BrokerOrder:
        """Check order status and handle terminal states.

        Args:
            order: Broker order to check.
            order_id: Order ID for error messages.

        Returns:
            The order if it's in a terminal state.

        Raises:
            ExecutionError: If order is rejected.
        """
        if self._is_terminal_status(order):
            if order.status == BrokerOrderStatus.REJECTED:
                msg = f"Order {order_id} was rejected"
                raise ExecutionError(msg)
            return order

        if self._has_partial_fill(order):
            return order

        return None  # type: ignore[return-value]

    async def _wait_for_confirmation(self, order_id: str) -> BrokerOrder:
        """Wait for order confirmation/fill with timeout.

        Polls broker for order status until filled, rejected, cancelled,
        or timeout occurs.

        Args:
            order_id: Order ID to track.

        Returns:
            Confirmed broker order.

        Raises:
            asyncio.TimeoutError: If timeout occurs.
            ExecutionError: If order is rejected.
            RuntimeError: If loop exits unexpectedly.
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self._confirmation_timeout_seconds:
                msg = f"Order {order_id} confirmation timeout after {elapsed:.1f}s"
                raise asyncio.TimeoutError(msg)

            # Fetch order status
            orders = await self._broker.get_orders()
            order = next((o for o in orders if o.order_id == order_id), None)

            if not order:
                _LOGGER.warning("Order %s not found in order list", order_id)
                await asyncio.sleep(self._confirmation_poll_interval)
                continue

            # Check terminal states
            result = self._check_order_status(order, order_id)
            if result is not None:
                return result

            # Wait before next poll
            await asyncio.sleep(self._confirmation_poll_interval)  # type: ignore[unreachable]

    def _validate_slippage(
        self,
        expected_price: Decimal,
        filled_price: Decimal | None,
        side: OrderSide,
    ) -> None:
        """Validate that slippage is within tolerance.

        Args:
            expected_price: Expected fill price.
            filled_price: Actual fill price.
            side: Order side (BUY or SELL).

        Raises:
            ExecutionError: If slippage exceeds tolerance.
        """
        if filled_price is None:
            _LOGGER.warning("No fill price available for slippage check")
            return

        # Calculate slippage in basis points
        if side == OrderSide.BUY:
            slippage = (filled_price - expected_price) / expected_price
        else:  # SELL
            slippage = (expected_price - filled_price) / expected_price

        slippage_bps = slippage * Decimal("10000")

        if slippage_bps > self._slippage_tolerance_bps:
            msg = (
                f"Slippage exceeded tolerance: {slippage_bps:.2f} bps > "
                f"{self._slippage_tolerance_bps:.2f} bps. "
                f"Expected: {expected_price}, Filled: {filled_price}"
            )
            raise ExecutionError(msg)

        _LOGGER.debug(
            "Slippage within tolerance: %.2f bps (max: %.2f bps)",
            slippage_bps,
            self._slippage_tolerance_bps,
        )

    def _convert_broker_order_to_result(self, broker_order: BrokerOrder) -> ExecutionResult:
        """Convert broker Order to ExecutionResult.

        Args:
            broker_order: Broker order object.

        Returns:
            ExecutionResult for core layer.
        """
        status = self._map_broker_status(broker_order.status)

        # Handle partial fills
        if (
            broker_order.filled_quantity > 0
            and broker_order.filled_quantity < broker_order.quantity
        ):
            status = OrderStatus.PARTIALLY_FILLED

        filled_qty = Decimal(str(broker_order.filled_quantity))
        avg_price = (
            Decimal(str(broker_order.average_price)) if broker_order.average_price else Decimal("0")
        )

        message = f"broker order: {broker_order.order_id} ({status.value})"

        return ExecutionResult(
            order_id=broker_order.order_id,
            status=status,
            filled_quantity=filled_qty,
            average_price=avg_price,
            message=message,
        )

    def cancel_all(self) -> int:
        """Cancel all open orders.

        Returns:
            Number of cancelled orders.
        """
        try:
            count = asyncio.run(self._cancel_all_async())
            return count
        except Exception as e:
            _LOGGER.error("Failed to cancel all orders: %s", e)
            return 0

    async def _cancel_all_async(self) -> int:
        """Cancel all open orders asynchronously.

        Returns:
            Number of cancelled orders.
        """
        if not self._open_orders:
            return 0

        cancelled_count = 0
        for order_id in list(self._open_orders):
            try:
                await self._broker.cancel_order(order_id=order_id)
                cancelled_count += 1
            except Exception as e:
                _LOGGER.warning("Failed to cancel order %s: %s", order_id, e)

        self._open_orders.clear()
        return cancelled_count

    def close_order(self, order_id: str) -> bool:
        """Close a specific order by ID.

        Args:
            order_id: The order ID to close.

        Returns:
            True if order was found and closed, False otherwise.
        """
        try:
            result = asyncio.run(self._close_order_async(order_id))
            return result
        except Exception as e:
            _LOGGER.error("Failed to close order %s: %s", order_id, e)
            return False

    async def _close_order_async(self, order_id: str) -> bool:
        """Close a specific order asynchronously.

        Args:
            order_id: The order ID to close.

        Returns:
            True if order was found and closed, False otherwise.
        """
        if order_id not in self._open_orders:
            return False

        try:
            await self._broker.cancel_order(order_id=order_id)
            self._open_orders.discard(order_id)
            return True
        except Exception as e:
            _LOGGER.warning("Failed to close order %s: %s", order_id, e)
            return False
