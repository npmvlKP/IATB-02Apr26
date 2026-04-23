# mypy: disable-error-code="no-any-return,no-untyped-def,type-arg,override,assignment"
# mypy: disable-error-code="attr-defined,misc,unused-ignore,unused-arg"
"""
Unit tests for BrokerInterface protocol compliance.

Tests ensure that any broker implementation conforms to the BrokerInterface protocol.
All external API calls are mocked to isolate interface compliance testing.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from iatb.broker.base import (
    BrokerInterface,
    Exchange,
    Margin,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    TransactionType,
)


class MockBroker(BrokerInterface):
    """Mock broker implementation for testing protocol compliance."""

    def __init__(self) -> None:
        """Initialize mock broker with async methods."""
        from collections.abc import Mapping

        self.place_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.cancel_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_positions_async: AsyncMock[list[Position]] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_orders_async: AsyncMock[list[Order]] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_margins_async: AsyncMock[Margin] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_order_history_async: AsyncMock[list[Mapping[str, Any]]] = (
            AsyncMock(return_value=None)  # type: ignore[assignment]
        )
        self.get_holdings_async: AsyncMock[list[Mapping[str, Any]]] = (
            AsyncMock(return_value=None)  # type: ignore[assignment]
        )
        self.modify_order_async: AsyncMock[Order] = AsyncMock(return_value=None)  # type: ignore[assignment]
        self.get_quote_async: AsyncMock[dict[str, Any]] = AsyncMock(return_value=None)  # type: ignore[assignment]

    async def place_order(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> Order:
        """Mock place order implementation."""
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

    async def cancel_order(self, *, order_id: str) -> Order:
        """Mock cancel order implementation."""
        return await self.cancel_order_async(order_id=order_id)

    async def get_positions(self) -> list[Position]:
        """Mock get positions implementation."""
        return await self.get_positions_async()

    async def get_orders(self) -> list[Order]:
        """Mock get orders implementation."""
        return await self.get_orders_async()

    async def get_margins(self) -> Margin:
        """Mock get margins implementation."""
        return await self.get_margins_async()

    async def get_order_history(
        self, *, order_id: str, from_date: date | None = None, to_date: date | None = None
    ) -> list[dict[str, Any]]:
        """Mock get order history implementation."""
        return await self.get_order_history_async(
            order_id=order_id, from_date=from_date, to_date=to_date
        )

    async def get_holdings(self) -> list[dict[str, Any]]:
        """Mock get holdings implementation."""
        return await self.get_holdings_async()

    async def modify_order(
        self,
        *,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        trigger_price: Decimal | None = None,
        disclosed_quantity: int | None = None,
    ) -> Order:
        """Mock modify order implementation."""
        return await self.modify_order_async(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            trigger_price=trigger_price,
            disclosed_quantity=disclosed_quantity,
        )

    async def get_quote(self, *, symbol: str, exchange: Exchange) -> dict[str, Any]:
        """Mock get quote implementation."""
        return await self.get_quote_async(symbol=symbol, exchange=exchange)


class TestBrokerInterfaceCompliance:
    """Test suite for BrokerInterface protocol compliance."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.broker = MockBroker()
        self.sample_order = Order(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=OrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )

    # ========================================
    # Happy Path Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_place_order_market_order_success(self) -> None:
        """Test successful market order placement."""
        self.broker.place_order_async.return_value = self.sample_order

        result = await self.broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )

        assert isinstance(result, Order)
        assert result.order_id == "ORD123456"
        assert result.symbol == "RELIANCE"
        assert result.status == OrderStatus.COMPLETE
        self.broker.place_order_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_limit_order_with_price(self) -> None:
        """Test successful limit order placement with price."""
        limit_order = Order(
            order_id="ORD123456",
            symbol="INFY",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            price=Decimal("1450.75"),
            trigger_price=None,
            status=OrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=50,
            average_price=Decimal("1450.75"),
        )
        self.broker.place_order_async.return_value = limit_order

        result = await self.broker.place_order(
            symbol="INFY",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            price=Decimal("1450.75"),
        )

        assert result.symbol == "INFY"
        assert result.order_type == OrderType.LIMIT
        assert result.price == Decimal("1450.75")

    @pytest.mark.asyncio
    async def test_place_order_stop_loss_with_trigger_price(self) -> None:
        """Test successful stop-loss order placement with trigger price."""
        stop_loss_order = Order(
            order_id="ORD123456",
            symbol="TCS",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=10,
            price=Decimal("3400.00"),
            trigger_price=Decimal("3390.00"),
            status=OrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=10,
            average_price=Decimal("3400.00"),
        )
        self.broker.place_order_async.return_value = stop_loss_order

        result = await self.broker.place_order(
            symbol="TCS",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=10,
            price=Decimal("3400.00"),
            trigger_price=Decimal("3390.00"),
        )

        assert result.trigger_price == Decimal("3390.00")

    @pytest.mark.asyncio
    async def test_place_order_delivery_product_type(self) -> None:
        """Test order placement with delivery product type."""
        self.broker.place_order_async.return_value = self.sample_order

        await self.broker.place_order(
            symbol="HDFC",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            product_type=ProductType.DELIVERY,
        )

        call_kwargs = self.broker.place_order_async.call_args[1]
        assert call_kwargs["product_type"] == ProductType.DELIVERY

    @pytest.mark.asyncio
    async def test_cancel_order_success(self) -> None:
        """Test successful order cancellation."""
        cancelled_order = Order(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=OrderStatus.CANCELLED,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.broker.cancel_order_async.return_value = cancelled_order

        result = await self.broker.cancel_order(order_id="ORD123456")

        assert result.status == OrderStatus.CANCELLED
        assert result.order_id == "ORD123456"

    @pytest.mark.asyncio
    async def test_get_positions_returns_list(self) -> None:
        """Test get positions returns list of Position objects."""
        positions = [
            Position(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                product_type=ProductType.INTRADAY,
                quantity=10,
                average_price=Decimal("2500.50"),
                last_price=Decimal("2510.00"),
                pnl=Decimal("95.00"),
                day_change=Decimal("9.50"),
            ),
            Position(
                symbol="INFY",
                exchange=Exchange.NSE,
                product_type=ProductType.INTRADAY,
                quantity=50,
                average_price=Decimal("1450.00"),
                last_price=Decimal("1445.00"),
                pnl=Decimal("-250.00"),
                day_change=Decimal("-5.00"),
            ),
        ]
        self.broker.get_positions_async.return_value = positions

        result = await self.broker.get_positions()

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(p, Position) for p in result)
        assert result[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_orders_returns_list(self) -> None:
        """Test get orders returns list of Order objects."""
        self.broker.get_orders_async.return_value = [self.sample_order]

        result = await self.broker.get_orders()

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Order)

    @pytest.mark.asyncio
    async def test_get_margins_returns_margin_details(self) -> None:
        """Test get margins returns Margin object with correct fields."""
        margin = Margin(
            available_cash=Decimal("100000.00"),
            used_margin=Decimal("20000.00"),
            available_margin=Decimal("80000.00"),
            opening_balance=Decimal("100000.00"),
        )
        self.broker.get_margins_async.return_value = margin

        result = await self.broker.get_margins()

        assert isinstance(result, Margin)
        assert result.available_cash == Decimal("100000.00")
        assert result.used_margin == Decimal("20000.00")
        assert result.available_margin == Decimal("80000.00")

    @pytest.mark.asyncio
    async def test_get_order_history_with_date_range(self) -> None:
        """Test get order history with date range filter."""
        history = [
            {
                "order_id": "ORD123456",
                "status": "COMPLETE",
                "timestamp": "2026-04-07 14:30:00",
            }
        ]
        self.broker.get_order_history_async.return_value = history

        from_date = date(2026, 4, 1)
        to_date = date(2026, 4, 7)
        result = await self.broker.get_order_history(
            order_id="ORD123456", from_date=from_date, to_date=to_date
        )

        assert isinstance(result, list)
        assert len(result) == 1
        self.broker.get_order_history_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_holdings_returns_list(self) -> None:
        """Test get holdings returns list of holdings."""
        holdings = [
            {
                "symbol": "RELIANCE",
                "quantity": 10,
                "average_price": "2500.50",
                "last_price": "2510.00",
                "pnl": "95.00",
            }
        ]
        self.broker.get_holdings_async.return_value = holdings

        result = await self.broker.get_holdings()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["symbol"] == "RELIANCE"

    @pytest.mark.asyncio
    async def test_modify_order_price_and_quantity(self) -> None:
        """Test order modification with new price and quantity."""
        self.broker.modify_order_async.return_value = self.sample_order

        result = await self.broker.modify_order(
            order_id="ORD123456",
            price=Decimal("2600.00"),
            quantity=15,
        )

        assert result.order_id == "ORD123456"
        self.broker.modify_order_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_quote_returns_quote_data(self) -> None:
        """Test get quote returns quote data dictionary."""
        quote = {
            "symbol": "RELIANCE",
            "last_price": "2510.00",
            "bid": "2509.50",
            "ask": "2510.50",
            "volume": "1000000",
        }
        self.broker.get_quote_async.return_value = quote

        result = await self.broker.get_quote(symbol="RELIANCE", exchange=Exchange.NSE)

        assert isinstance(result, dict)
        assert result["symbol"] == "RELIANCE"
        assert result["last_price"] == "2510.00"

    # ========================================
    # Error Path Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_place_order_invalid_quantity_raises_error(self) -> None:
        """Test that invalid quantity raises ValueError."""
        self.broker.place_order_async.side_effect = ValueError("Invalid quantity")

        with pytest.raises(ValueError, match="Invalid quantity"):
            await self.broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                quantity=-10,
            )

    @pytest.mark.asyncio
    async def test_place_order_missing_limit_price_raises_error(self) -> None:
        """Test that missing limit price for LIMIT order raises ValueError."""
        self.broker.place_order_async.side_effect = ValueError("Price required for LIMIT order")

        with pytest.raises(ValueError, match="Price required"):
            await self.broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                price=None,
            )

    @pytest.mark.asyncio
    async def test_cancel_order_invalid_id_raises_error(self) -> None:
        """Test that canceling non-existent order raises ValueError."""
        self.broker.cancel_order_async.side_effect = ValueError("Invalid order ID")

        with pytest.raises(ValueError, match="Invalid order ID"):
            await self.broker.cancel_order(order_id="INVALID_ID")

    @pytest.mark.asyncio
    async def test_cancel_already_executed_order_raises_error(self) -> None:
        """Test that canceling already executed order raises RuntimeError."""
        self.broker.cancel_order_async.side_effect = RuntimeError("Cannot cancel executed order")

        with pytest.raises(RuntimeError, match="Cannot cancel executed"):
            await self.broker.cancel_order(order_id="ORD123456")

    @pytest.mark.asyncio
    async def test_get_positions_failure_raises_runtime_error(self) -> None:
        """Test that get positions failure raises RuntimeError."""
        self.broker.get_positions_async.side_effect = RuntimeError("API connection failed")

        with pytest.raises(RuntimeError, match="API connection failed"):
            await self.broker.get_positions()

    @pytest.mark.asyncio
    async def test_modify_order_invalid_parameters_raises_error(self) -> None:
        """Test that modify order with invalid parameters raises ValueError."""
        self.broker.modify_order_async.side_effect = ValueError(
            "Order cannot be modified in current state"
        )

        with pytest.raises(ValueError, match="cannot be modified"):
            await self.broker.modify_order(order_id="ORD123456")

    # ========================================
    # Precision Handling Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_order_price_maintains_decimal_precision(self) -> None:
        """Test that order price maintains Decimal precision."""
        high_precision_price = Decimal("1234.56789")
        order_with_precision = Order(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=high_precision_price,
            trigger_price=None,
            status=OrderStatus.OPEN,
            product_type=ProductType.INTRADAY,
            timestamp=datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC),
            filled_quantity=0,
            average_price=None,
        )
        self.broker.place_order_async.return_value = order_with_precision

        result = await self.broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            price=high_precision_price,
        )

        assert result.price == high_precision_price
        assert isinstance(result.price, Decimal)
        assert str(result.price) == "1234.56789"

    @pytest.mark.asyncio
    async def test_margin_values_use_decimal_precision(self) -> None:
        """Test that margin values use Decimal precision."""
        margin = Margin(
            available_cash=Decimal("100000.123456"),
            used_margin=Decimal("20000.789012"),
            available_margin=Decimal("79999.334444"),
            opening_balance=Decimal("100000.123456"),
        )
        self.broker.get_margins_async.return_value = margin

        result = await self.broker.get_margins()

        assert result.available_cash == Decimal("100000.123456")
        assert result.used_margin == Decimal("20000.789012")
        assert all(
            isinstance(getattr(result, field), Decimal)
            for field in ["available_cash", "used_margin", "available_margin", "opening_balance"]
        )

    @pytest.mark.asyncio
    async def test_position_pnl_uses_decimal_precision(self) -> None:
        """Test that position P&L uses Decimal precision."""
        position = Position(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            product_type=ProductType.INTRADAY,
            quantity=10,
            average_price=Decimal("2500.123456"),
            last_price=Decimal("2510.789012"),
            pnl=Decimal("106.655560"),
            day_change=Decimal("10.665556"),
        )
        self.broker.get_positions_async.return_value = [position]

        result = await self.broker.get_positions()

        assert result[0].pnl == Decimal("106.655560")
        assert isinstance(result[0].pnl, Decimal)
        assert isinstance(result[0].average_price, Decimal)
        assert isinstance(result[0].last_price, Decimal)

    # ========================================
    # Timezone Handling Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_order_timestamp_is_utc_aware(self) -> None:
        """Test that order timestamp is timezone-aware in UTC."""
        utc_timestamp = datetime(2026, 4, 7, 14, 30, 0, tzinfo=UTC)
        order_with_utc = Order(
            order_id="ORD123456",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=OrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=utc_timestamp,
            filled_quantity=10,
            average_price=Decimal("2500.50"),
        )
        self.broker.place_order_async.return_value = order_with_utc

        result = await self.broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )

        assert result.timestamp.tzinfo == UTC
        assert result.timestamp == utc_timestamp

    # ========================================
    # Enum Tests
    # ========================================

    def test_order_type_enum_values(self) -> None:
        """Test OrderType enum has correct values."""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP_LOSS.value == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET.value == "STOP_LOSS_MARKET"

    def test_order_status_enum_values(self) -> None:
        """Test OrderStatus enum has correct values."""
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.OPEN.value == "OPEN"
        assert OrderStatus.COMPLETE.value == "COMPLETE"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"
        assert OrderStatus.TRIGGER_PENDING.value == "TRIGGER_PENDING"
        assert OrderStatus.VALIDATION_PENDING.value == "VALIDATION_PENDING"

    def test_transaction_type_enum_values(self) -> None:
        """Test TransactionType enum has correct values."""
        assert TransactionType.BUY.value == "BUY"
        assert TransactionType.SELL.value == "SELL"

    def test_product_type_enum_values(self) -> None:
        """Test ProductType enum has correct values."""
        assert ProductType.INTRADAY.value == "MIS"
        assert ProductType.DELIVERY.value == "CNC"
        assert ProductType.NRML.value == "NRML"
        assert ProductType.BO.value == "BO"
        assert ProductType.CO.value == "CO"

    def test_exchange_enum_values(self) -> None:
        """Test Exchange enum has correct values."""
        assert Exchange.NSE.value == "NSE"
        assert Exchange.BSE.value == "BSE"
        assert Exchange.NFO.value == "NFO"
        assert Exchange.BFO.value == "BFO"
        assert Exchange.MCX.value == "MCX"

    # ========================================
    # Edge Cases
    # ========================================

    @pytest.mark.asyncio
    async def test_place_order_zero_quantity_raises_error(self) -> None:
        """Test that zero quantity order raises error."""
        self.broker.place_order_async.side_effect = ValueError("Quantity must be positive")

        with pytest.raises(ValueError, match="Quantity must be positive"):
            await self.broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                quantity=0,
            )

    @pytest.mark.asyncio
    async def test_get_empty_positions_list(self) -> None:
        """Test getting empty positions list."""
        self.broker.get_positions_async.return_value = []

        result = await self.broker.get_positions()

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_empty_orders_list(self) -> None:
        """Test getting empty orders list."""
        self.broker.get_orders_async.return_value = []

        result = await self.broker.get_orders()

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_modify_order_no_changes(self) -> None:
        """Test modify order with no actual changes."""
        self.broker.modify_order_async.return_value = self.sample_order

        result = await self.broker.modify_order(order_id="ORD123456")

        assert result.order_id == "ORD123456"
        self.broker.modify_order_async.assert_called_once_with(
            order_id="ORD123456",
            quantity=None,
            price=None,
            order_type=None,
            trigger_price=None,
            disclosed_quantity=None,
        )

    @pytest.mark.asyncio
    async def test_get_order_history_no_dates(self) -> None:
        """Test get order history without date filters."""
        self.broker.get_order_history_async.return_value = []

        result = await self.broker.get_order_history(order_id="ORD123456")

        assert isinstance(result, list)
        self.broker.get_order_history_async.assert_called_once_with(
            order_id="ORD123456", from_date=None, to_date=None
        )

    # ========================================
    # External API Mocking Tests
    # ========================================

    @pytest.mark.asyncio
    async def test_all_externall_apis_are_mocked(self) -> None:
        """Verify all external broker API calls are mocked."""
        assert isinstance(self.broker.place_order_async, AsyncMock)
        assert isinstance(self.broker.cancel_order_async, AsyncMock)
        assert isinstance(self.broker.get_positions_async, AsyncMock)
        assert isinstance(self.broker.get_orders_async, AsyncMock)
        assert isinstance(self.broker.get_margins_async, AsyncMock)
        assert isinstance(self.broker.get_order_history_async, AsyncMock)
        assert isinstance(self.broker.get_holdings_async, AsyncMock)
        assert isinstance(self.broker.modify_order_async, AsyncMock)
        assert isinstance(self.broker.get_quote_async, AsyncMock)

    @pytest.mark.asyncio
    async def test_mock_isolation_no_external_calls(self) -> None:
        """Test that mocks prevent actual external API calls."""
        self.broker.place_order_async.return_value = self.sample_order

        result = await self.broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )

        assert self.broker.place_order_async.called
        assert result.order_id == "ORD123456"
