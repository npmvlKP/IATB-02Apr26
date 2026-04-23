# mypy: disable-error-code="no-any-return,no-untyped-def,type-arg,override,assignment,attr-defined"
"""
Unit tests for LiveExecutor with real order routing through BrokerInterface.

Covers:
- Broker interface compliance
- Live executor order routing
- Mode switching (between exchanges, order types, etc.)
- Safety guards (slippage protection, confirmation timeout, partial fills)
All external API calls are mocked.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
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
from iatb.execution.base import OrderRequest
from iatb.execution.live_executor import LiveExecutor


class MockBroker(BrokerInterface):
    """Mock broker for testing LiveExecutor."""

    def __init__(self) -> None:
        """Initialize mock broker with async methods."""
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from iatb.broker.base import Margin, Order, Position

        self.place_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.cancel_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_positions_async: AsyncMock[list[Position]] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_orders_async: AsyncMock[list[Order]] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_margins_async: AsyncMock[Margin] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_order_history_async: AsyncMock[list[dict[str, Any]]] = (
            AsyncMock(return_value=None)  # type: ignore[assignment]
        )
        self.get_holdings_async: AsyncMock[list[dict[str, Any]]] = (
            AsyncMock(return_value=None)  # type: ignore[assignment]
        )
        self.modify_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_quote_async: AsyncMock[dict[str, Any]] = AsyncMock(return_value=None)  # type: ignore[assignment]

    async def place_order(
        self,
        *,
        symbol: str,
        exchange: BrokerExchange,
        transaction_type: TransactionType,
        order_type: BrokerOrderType,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> BrokerOrder:
        """Mock place order."""
        return await self.place_order_async(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            order_type=order_type,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            product_type=product_type,
        )

    async def cancel_order(self, *, order_id: str) -> BrokerOrder:
        """Mock cancel order."""
        return await self.cancel_order_async(order_id=order_id)

    async def get_positions(self) -> list:
        """Mock get positions."""
        return await self.get_positions_async()

    async def get_orders(self) -> list[BrokerOrder]:
        """Mock get orders."""
        return await self.get_orders_async()

    async def get_margins(self) -> object:
        """Mock get margins."""
        return await self.get_margins_async()

    async def get_order_history(self, *, order_id: str, from_date=None, to_date=None) -> list:
        """Mock get order history."""
        return await self.get_order_history_async(
            order_id=order_id, from_date=from_date, to_date=to_date
        )

    async def get_holdings(self) -> list:
        """Mock get holdings."""
        return await self.get_holdings_async()

    async def modify_order(
        self,
        *,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: BrokerOrderType | None = None,
        trigger_price: Decimal | None = None,
        disclosed_quantity: int | None = None,
    ) -> BrokerOrder:
        """Mock modify order."""
        return await self.modify_order_async(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            trigger_price=trigger_price,
            disclosed_quantity=disclosed_quantity,
        )

    async def get_quote(self, *, symbol: str, exchange: BrokerExchange) -> dict:
        """Mock get quote."""
        return await self.get_quote_async(symbol=symbol, exchange=exchange)


class TestLiveExecutor:
    """Test suite for LiveExecutor."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_broker = MockBroker()
        self.executor = LiveExecutor(broker=self.mock_broker)

        # Sample broker order response
        self.sample_broker_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )

    # ========================================
    # Happy Path Tests
    # ========================================

    def test_initialization_with_broker(self) -> None:
        """Test executor initializes correctly with broker."""
        assert self.executor._broker is not None
        assert self.executor._confirmation_timeout_seconds == 30
        assert self.executor._slippage_tolerance_bps == Decimal("20")

    def test_initialization_with_custom_parameters(self) -> None:
        """Test executor initializes with custom parameters."""
        executor = LiveExecutor(
            broker=self.mock_broker,
            confirmation_timeout_seconds=60,
            slippage_tolerance_bps=Decimal("50"),
        )
        assert executor._confirmation_timeout_seconds == 60
        assert executor._slippage_tolerance_bps == Decimal("50")

    def test_execute_market_order_success(self) -> None:
        """Test successful market order execution."""
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
        )

        result = self.executor.execute_order(request)

        assert result.order_id == "ORD123456"
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")
        assert result.average_price == Decimal("2500.50")

    def test_execute_limit_order_with_price(self) -> None:
        """Test successful limit order execution."""
        limit_order = BrokerOrder(
            order_id="ORD123456",
            symbol="INFY",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.LIMIT,
            quantity=50,
            price=Decimal("1450.75"),
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=50,
            average_price=Decimal("1450.75"),
        )
        self.mock_broker.place_order_async.return_value = limit_order
        self.mock_broker.get_orders_async.return_value = [limit_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="INFY",
            side=OrderSide.BUY,
            quantity=Decimal("50"),
            order_type=OrderType.LIMIT,
            price=Decimal("1450.75"),
        )

        result = self.executor.execute_order(request)

        assert result.order_id == "ORD123456"
        assert result.average_price == Decimal("1450.75")

    def test_execute_sell_order(self) -> None:
        """Test successful sell order execution."""
        sell_order = BrokerOrder(
            order_id="ORD123456",
            symbol="TCS",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("3400.00"),
        )
        self.mock_broker.place_order_async.return_value = sell_order
        self.mock_broker.get_orders_async.return_value = [sell_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.SELL,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
        )

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.FILLED

    # ========================================
    # Mode Switching Tests
    # ========================================

    def test_exchange_mapping_nse(self) -> None:
        """Test exchange mapping for NSE."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["exchange"] == BrokerExchange.NSE

    def test_exchange_mapping_bse(self) -> None:
        """Test exchange mapping for BSE."""
        request = OrderRequest(
            exchange=Exchange.BSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["exchange"] == BrokerExchange.BSE

    def test_exchange_mapping_mcx(self) -> None:
        """Test exchange mapping for MCX."""
        request = OrderRequest(
            exchange=Exchange.MCX,
            symbol="CRUDEOIL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["exchange"] == BrokerExchange.MCX

    def test_order_type_mapping_market(self) -> None:
        """Test order type mapping for MARKET."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["order_type"] == BrokerOrderType.MARKET

    def test_order_type_mapping_limit(self) -> None:
        """Test order type mapping for LIMIT."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=Decimal("2500.00"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["order_type"] == BrokerOrderType.LIMIT

    def test_order_type_mapping_stop_loss(self) -> None:
        """Test order type mapping for STOP_LOSS."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.STOP_LOSS,
            price=Decimal("2510.00"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["order_type"] == BrokerOrderType.STOP_LOSS

    def test_transaction_type_mapping_buy(self) -> None:
        """Test transaction type mapping for BUY."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["transaction_type"] == TransactionType.BUY

    def test_transaction_type_mapping_sell(self) -> None:
        """Test transaction type mapping for SELL."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.SELL,
            quantity=Decimal("10"),
        )
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        self.executor.execute_order(request)

        call_kwargs = self.mock_broker.place_order_async.call_args[1]
        assert call_kwargs["transaction_type"] == TransactionType.SELL

    # ========================================
    # Safety Guard Tests
    # ========================================

    def test_slippage_protection_within_tolerance_buy(self) -> None:
        """Test slippage protection within tolerance for BUY order."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=Decimal("2500.00"),
        )

        # Fill within tolerance (0.10% slippage)
        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.LIMIT,
            quantity=10,
            price=Decimal("2500.00"),
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2502.50"),  # 10 bps slippage
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.FILLED

    def test_slippage_protection_exceeds_tolerance_buy(self) -> None:
        """Test slippage protection rejects order exceeding tolerance for BUY."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=Decimal("2500.00"),
        )

        # Fill exceeds tolerance (0.30% slippage)
        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.LIMIT,
            quantity=10,
            price=Decimal("2500.00"),
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2507.50"),  # 30 bps slippage
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        with pytest.raises(ExecutionError, match="Slippage exceeded tolerance"):
            self.executor.execute_order(request)

    def test_slippage_protection_within_tolerance_sell(self) -> None:
        """Test slippage protection within tolerance for SELL order."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.SELL,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=Decimal("2500.00"),
        )

        # Fill within tolerance (0.10% slippage)
        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=BrokerOrderType.LIMIT,
            quantity=10,
            price=Decimal("2500.00"),
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2497.50"),  # 10 bps slippage
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.FILLED

    def test_confirmation_timeout_raises_error(self) -> None:
        """Test that confirmation timeout raises ExecutionError."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        pending_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.PENDING,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.place_order_async.return_value = pending_order
        self.mock_broker.get_orders_async.return_value = [pending_order]

        # Set very short timeout for testing
        executor = LiveExecutor(
            broker=self.mock_broker,
            confirmation_timeout_seconds=1,
        )

        with pytest.raises(ExecutionError, match="confirmation timeout"):
            executor.execute_order(request)

    def test_partial_fill_handling(self) -> None:
        """Test handling of partial fills."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        partial_fill_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.OPEN,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=5,
            average_price=Decimal("2500.50"),
        )
        self.mock_broker.place_order_async.return_value = partial_fill_order
        self.mock_broker.get_orders_async.return_value = [partial_fill_order]

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.PARTIALLY_FILLED
        assert result.filled_quantity == Decimal("5")

    def test_rejected_order_raises_error(self) -> None:
        """Test that rejected order raises ExecutionError."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        rejected_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.REJECTED,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.place_order_async.return_value = rejected_order
        self.mock_broker.get_orders_async.return_value = [rejected_order]

        with pytest.raises(ExecutionError, match="was rejected"):
            self.executor.execute_order(request)

    # ========================================
    # Error Path Tests
    # ========================================

    def test_initialization_without_broker_raises_error(self) -> None:
        """Test that initialization without broker raises ValueError."""
        with pytest.raises(ValueError, match="broker is required"):
            LiveExecutor(broker=None)

    def test_initialization_invalid_timeout_raises_error(self) -> None:
        """Test that invalid confirmation timeout raises ValueError."""
        with pytest.raises(ValueError, match="confirmation_timeout_seconds must be positive"):
            LiveExecutor(broker=self.mock_broker, confirmation_timeout_seconds=0)

    def test_initialization_invalid_poll_interval_raises_error(self) -> None:
        """Test that invalid poll interval raises ValueError."""
        with pytest.raises(ValueError, match="confirmation_poll_interval_seconds must be positive"):
            LiveExecutor(broker=self.mock_broker, confirmation_poll_interval_seconds=-0.5)

    def test_initialization_negative_slippage_tolerance_raises_error(self) -> None:
        """Test that negative slippage tolerance raises ValueError."""
        with pytest.raises(ValueError, match="slippage_tolerance_bps cannot be negative"):
            LiveExecutor(broker=self.mock_broker, slippage_tolerance_bps=Decimal("-10"))

    def test_broker_place_order_failure_raises_error(self) -> None:
        """Test that broker place order failure raises ExecutionError."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        self.mock_broker.place_order_async.side_effect = RuntimeError("API connection failed")

        with pytest.raises(ExecutionError, match="Order execution failed"):
            self.executor.execute_order(request)

    # ========================================
    # Precision Handling Tests
    # ========================================

    def test_decimal_precision_in_price(self) -> None:
        """Test that Decimal precision is maintained for price."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.LIMIT,
            price=Decimal("1234.5678"),
        )

        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.LIMIT,
            quantity=10,
            price=Decimal("1234.5678"),
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("1234.5678"),
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        result = self.executor.execute_order(request)

        assert result.average_price == Decimal("1234.5678")
        assert isinstance(result.average_price, Decimal)

    def test_decimal_precision_in_quantity(self) -> None:
        """Test that Decimal precision is maintained for quantity."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10.5"),
        )

        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        result = self.executor.execute_order(request)

        assert isinstance(result.filled_quantity, Decimal)
        assert result.filled_quantity == Decimal("10")

    # ========================================
    # Timezone Handling Tests
    # ========================================

    def test_order_timestamp_is_utc_aware(self) -> None:
        """Test that order timestamp is timezone-aware in UTC."""
        utc_timestamp = datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC)

        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=utc_timestamp,
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        self.executor.execute_order(request)

        # Verify the timestamp in the broker order is UTC-aware
        assert filled_order.timestamp.tzinfo == UTC

    # ========================================
    # Order Management Tests
    # ========================================

    def test_cancel_all_orders(self) -> None:
        """Test cancelling all open orders."""
        # Add some open orders to the executor
        self.executor._open_orders.add("ORD001")
        self.executor._open_orders.add("ORD002")
        self.executor._open_orders.add("ORD003")

        cancelled_order = BrokerOrder(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.CANCELLED,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.cancel_order_async.return_value = cancelled_order

        cancelled_count = self.executor.cancel_all()

        assert cancelled_count == 3
        assert len(self.executor._open_orders) == 0

    def test_cancel_all_empty_orders(self) -> None:
        """Test cancelling all orders when none are open."""
        cancelled_count = self.executor.cancel_all()

        assert cancelled_count == 0
        self.mock_broker.cancel_order_async.assert_not_called()

    def test_close_specific_order(self) -> None:
        """Test closing a specific order by ID."""
        self.executor._open_orders.add("ORD001")
        self.executor._open_orders.add("ORD002")

        cancelled_order = BrokerOrder(
            order_id="ORD001",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.CANCELLED,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.cancel_order_async.return_value = cancelled_order

        result = self.executor.close_order("ORD001")

        assert result is True
        assert "ORD001" not in self.executor._open_orders
        assert "ORD002" in self.executor._open_orders

    def test_close_nonexistent_order(self) -> None:
        """Test closing a non-existent order returns False."""
        result = self.executor.close_order("NONEXISTENT")

        assert result is False
        self.mock_broker.cancel_order_async.assert_not_called()

    # ========================================
    # Order Status Mapping Tests
    # ========================================

    def test_map_broker_status_complete_to_filled(self) -> None:
        """Test mapping COMPLETE status to FILLED."""
        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.FILLED

    def test_map_broker_status_cancelled(self) -> None:
        """Test mapping CANCELLED status."""
        cancelled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.CANCELLED,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.place_order_async.return_value = cancelled_order
        self.mock_broker.get_orders_async.return_value = [cancelled_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.CANCELLED

    def test_map_broker_status_pending(self) -> None:
        """Test mapping PENDING status."""
        pending_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.PENDING,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.mock_broker.place_order_async.return_value = pending_order
        self.mock_broker.get_orders_async.return_value = [pending_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        # Should timeout since order never completes
        executor = LiveExecutor(
            broker=self.mock_broker,
            confirmation_timeout_seconds=1,
        )

        with pytest.raises(ExecutionError, match="confirmation timeout"):
            executor.execute_order(request)

    # ========================================
    # Edge Cases
    # ========================================

    def test_order_without_price_skips_slippage_check(self) -> None:
        """Test that market orders without price skip slippage check."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            price=None,  # No expected price
        )

        filled_order = BrokerOrder(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=BrokerExchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=BrokerOrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2600.00"),  # Large slippage, but no check
        )
        self.mock_broker.place_order_async.return_value = filled_order
        self.mock_broker.get_orders_async.return_value = [filled_order]

        result = self.executor.execute_order(request)

        assert result.status == OrderStatus.FILLED
        assert result.average_price == Decimal("2600.00")

    def test_order_not_found_in_broker_list(self) -> None:
        """Test handling when order is not found in broker's order list."""
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = []  # Order not found

        # Should timeout since order is never found
        executor = LiveExecutor(
            broker=self.mock_broker,
            confirmation_timeout_seconds=1,
        )

        with pytest.raises(ExecutionError, match="confirmation timeout"):
            executor.execute_order(request)

    def test_close_order_failure_handles_gracefully(self) -> None:
        """Test that close order handles failures gracefully."""
        self.executor._open_orders.add("ORD001")

        self.mock_broker.cancel_order_async.side_effect = RuntimeError("Cancel failed")

        result = self.executor.close_order("ORD001")

        # Should return False on failure but not crash
        assert result is False
        assert "ORD001" in self.executor._open_orders

    # ========================================
    # External API Mocking Tests
    # ========================================

    def test_all_broker_methods_are_mocked(self) -> None:
        """Verify all broker API calls are properly mocked."""
        assert isinstance(self.mock_broker.place_order_async, AsyncMock)
        assert isinstance(self.mock_broker.cancel_order_async, AsyncMock)
        assert isinstance(self.mock_broker.get_orders_async, AsyncMock)

    def test_mock_isolation_prevents_external_calls(self) -> None:
        """Test that mocks prevent actual external API calls."""
        self.mock_broker.place_order_async.return_value = self.sample_broker_order
        self.mock_broker.get_orders_async.return_value = [self.sample_broker_order]

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
        )

        result = self.executor.execute_order(request)

        # Verify only mocks were called
        assert self.mock_broker.place_order_async.called
        assert self.mock_broker.get_orders_async.called
        assert result.order_id == "ORD123456"
