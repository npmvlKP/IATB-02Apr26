"""
Tests for ZerodhaBroker implementation.

Tests cover:
- Happy path scenarios
- Edge cases
- Error handling
- Type conversions
- Rate limiting and retry logic integration
- Mock external API calls
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from iatb.broker import (
    Exchange,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    ZerodhaBroker,
    ZerodhaTokenManager,
)
from iatb.core.exceptions import ConfigError


@pytest.fixture
def mock_token_manager() -> ZerodhaTokenManager:
    """Create a mock token manager."""
    manager = MagicMock(spec=ZerodhaTokenManager)
    manager.get_access_token.return_value = "test_access_token_12345"
    manager.get_kite_client.return_value = MagicMock()

    # Make get_kite_client return an async function
    async def mock_get_kite_client(**kwargs: Any) -> Any:  # noqa: ANN401
        return MagicMock()

    manager.get_kite_client = mock_get_kite_client
    return manager


@pytest.fixture
def mock_kite_client() -> MagicMock:
    """Create a mock KiteConnect client."""
    client = MagicMock()
    client.place_order.return_value = {"order_id": "ORD123456"}
    client.cancel_order.return_value = {"order_id": "ORD123456"}
    client.modify_order.return_value = {"order_id": "ORD123456"}
    client.positions.return_value = {"day": []}
    client.orders.return_value = []
    client.margins.return_value = {
        "equity": {
            "available": {"cash": 100000.0, "live_balance": 80000.0},
            "used": {"margin": 20000.0},
            "net": 100000.0,
        }
    }
    client.order_history.return_value = []
    client.holdings.return_value = []
    client.quote.return_value = {
        "NSE:RELIANCE": {
            "last_price": 2500.0,
            "volume": 1000000,
            "instrument_token": "256265",
        }
    }
    return client


@pytest.fixture
def broker(mock_token_manager: ZerodhaTokenManager, mock_kite_client: MagicMock) -> ZerodhaBroker:
    """Create a ZerodhaBroker instance with mocked dependencies."""
    broker = ZerodhaBroker(token_manager=mock_token_manager)
    broker._client = mock_kite_client
    broker._authenticated = True
    return broker


class TestZerodhaBrokerInit:
    """Test ZerodhaBroker initialization."""

    def test_init_with_token_manager(self, mock_token_manager: ZerodhaTokenManager) -> None:
        """Test successful initialization with token manager."""
        broker = ZerodhaBroker(token_manager=mock_token_manager)
        assert broker._token_manager == mock_token_manager
        assert broker._client is None
        assert not broker._authenticated

    def test_init_without_token_manager_raises_error(self) -> None:
        """Test that initialization without token manager raises error."""
        with pytest.raises(ValueError, match="token_manager is required"):
            ZerodhaBroker(token_manager=None)  # type: ignore[arg-type]

    def test_init_with_custom_rate_limiter(self, mock_token_manager: ZerodhaTokenManager) -> None:
        """Test initialization with custom rate limiter."""
        from iatb.data.rate_limiter import RateLimiter

        custom_limiter = RateLimiter(requests_per_second=5.0, burst_capacity=20)
        broker = ZerodhaBroker(token_manager=mock_token_manager, rate_limiter=custom_limiter)
        assert broker._rate_limiter == custom_limiter


class TestZerodhaBrokerAuthentication:
    """Test authentication methods."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_token_manager: ZerodhaTokenManager) -> None:
        """Test successful authentication."""
        broker = ZerodhaBroker(token_manager=mock_token_manager)
        await broker.authenticate()
        assert broker._authenticated is True
        assert broker._client is not None

    @pytest.mark.asyncio
    async def test_authenticate_without_token_raises_error(
        self, mock_token_manager: ZerodhaTokenManager
    ) -> None:
        """Test authentication without access token raises error."""
        mock_token_manager.get_access_token.return_value = None
        broker = ZerodhaBroker(token_manager=mock_token_manager)
        with pytest.raises(ConfigError, match="No access token available"):
            await broker.authenticate()

    @pytest.mark.asyncio
    async def test_ensure_authenticated_calls_authenticate(
        self, mock_token_manager: ZerodhaTokenManager
    ) -> None:
        """Test that _ensure_authenticated calls authenticate when not authenticated."""
        broker = ZerodhaBroker(token_manager=mock_token_manager)
        assert not broker._authenticated
        await broker._ensure_authenticated()
        assert broker._authenticated is True


class TestZerodhaBrokerPlaceOrder:
    """Test place_order method."""

    @pytest.mark.asyncio
    async def test_place_market_order(self, broker: ZerodhaBroker) -> None:
        """Test placing a market order."""
        order = await broker.place_order(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        assert order.order_id == "ORD123456"
        assert order.symbol == "RELIANCE"
        assert order.exchange == Exchange.NSE
        assert order.transaction_type == TransactionType.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 10
        assert order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_place_limit_order(self, broker: ZerodhaBroker) -> None:
        """Test placing a limit order."""
        order = await broker.place_order(
            symbol="INFY",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("1500.50"),
        )
        assert order.price == Decimal("1500.50")
        assert order.order_type == OrderType.LIMIT

    @pytest.mark.asyncio
    async def test_place_stop_loss_order(self, broker: ZerodhaBroker) -> None:
        """Test placing a stop loss order."""
        order = await broker.place_order(
            symbol="TCS",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=OrderType.STOP_LOSS,
            quantity=10,
            price=Decimal("3500.00"),
            trigger_price=Decimal("3450.00"),
        )
        assert order.trigger_price == Decimal("3450.00")
        assert order.order_type == OrderType.STOP_LOSS

    @pytest.mark.asyncio
    async def test_place_limit_order_without_price_raises_error(
        self, broker: ZerodhaBroker
    ) -> None:
        """Test that placing limit order without price raises error."""
        with pytest.raises(ValueError, match="price is required for LIMIT orders"):
            await broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
            )

    @pytest.mark.asyncio
    async def test_place_stop_loss_without_trigger_price_raises_error(
        self, broker: ZerodhaBroker
    ) -> None:
        """Test that placing stop loss order without trigger price raises error."""
        with pytest.raises(ValueError, match="trigger_price is required for STOP_LOSS orders"):
            await broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.STOP_LOSS,
                quantity=10,
                price=Decimal("2500.00"),
            )

    @pytest.mark.asyncio
    async def test_place_order_with_invalid_quantity_raises_error(
        self, broker: ZerodhaBroker
    ) -> None:
        """Test that placing order with invalid quantity raises error."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            await broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                quantity=0,
            )

    @pytest.mark.asyncio
    async def test_place_order_with_different_product_types(self, broker: ZerodhaBroker) -> None:
        """Test placing orders with different product types."""
        for product_type in [
            ProductType.INTRADAY,
            ProductType.DELIVERY,
            ProductType.NRML,
        ]:
            order = await broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                quantity=10,
                product_type=product_type,
            )
            assert order.product_type == product_type


class TestZerodhaBrokerCancelOrder:
    """Test cancel_order method."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, broker: ZerodhaBroker) -> None:
        """Test successful order cancellation."""
        broker._client.orders.return_value = [
            {
                "order_id": "ORD123456",
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "transaction_type": "BUY",
                "order_type": "MARKET",
                "quantity": 10,
                "price": "",
                "trigger_price": "",
                "status": "CANCELLED",
                "product": "MIS",
                "order_timestamp": datetime.now(UTC).isoformat(),
                "filled_quantity": 0,
                "average_price": "",
            }
        ]
        order = await broker.cancel_order(order_id="ORD123456")
        assert order.order_id == "ORD123456"
        assert order.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_order_without_order_id_raises_error(self, broker: ZerodhaBroker) -> None:
        """Test that canceling without order_id raises error."""
        with pytest.raises(ValueError, match="order_id is required"):
            await broker.cancel_order(order_id="")  # type: ignore[arg-type]


class TestZerodhaBrokerGetPositions:
    """Test get_positions method."""

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, broker: ZerodhaBroker) -> None:
        """Test getting positions when none exist."""
        broker._client.positions.return_value = {"day": []}
        positions = await broker.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_with_data(self, broker: ZerodhaBroker) -> None:
        """Test getting positions with data."""
        broker._client.positions.return_value = {
            "day": [
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "product": "MIS",
                    "quantity": 10,
                    "average_price": 2500.0,
                    "last_price": 2520.0,
                    "pnl": 200.0,
                    "day_change": 200.0,
                }
            ]
        }
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].exchange == Exchange.NSE
        assert positions[0].product_type == ProductType.INTRADAY
        assert positions[0].quantity == 10
        assert positions[0].average_price == Decimal("2500.0")
        assert positions[0].pnl == Decimal("200.0")

    @pytest.mark.asyncio
    async def test_get_positions_filters_zero_quantity(self, broker: ZerodhaBroker) -> None:
        """Test that positions with zero quantity are filtered out."""
        broker._client.positions.return_value = {
            "day": [
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "product": "MIS",
                    "quantity": 0,
                    "average_price": 2500.0,
                    "last_price": 2520.0,
                    "pnl": 0.0,
                    "day_change": 0.0,
                },
                {
                    "tradingsymbol": "INFY",
                    "exchange": "NSE",
                    "product": "MIS",
                    "quantity": 10,
                    "average_price": 1500.0,
                    "last_price": 1510.0,
                    "pnl": 100.0,
                    "day_change": 100.0,
                },
            ]
        }
        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "INFY"


class TestZerodhaBrokerGetOrders:
    """Test get_orders method."""

    @pytest.mark.asyncio
    async def test_get_orders_empty(self, broker: ZerodhaBroker) -> None:
        """Test getting orders when none exist."""
        broker._client.orders.return_value = []
        orders = await broker.get_orders()
        assert orders == []

    @pytest.mark.asyncio
    async def test_get_orders_with_data(self, broker: ZerodhaBroker) -> None:
        """Test getting orders with data."""
        broker._client.orders.return_value = [
            {
                "order_id": "ORD123456",
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "transaction_type": "BUY",
                "order_type": "MARKET",
                "quantity": 10,
                "price": "",
                "trigger_price": "",
                "status": "COMPLETE",
                "product": "MIS",
                "order_timestamp": datetime.now(UTC).isoformat(),
                "filled_quantity": 10,
                "average_price": "2500.0",
            }
        ]
        orders = await broker.get_orders()
        assert len(orders) == 1
        assert orders[0].order_id == "ORD123456"
        assert orders[0].symbol == "RELIANCE"
        assert orders[0].status == OrderStatus.COMPLETE
        assert orders[0].filled_quantity == 10
        assert orders[0].average_price == Decimal("2500.0")


class TestZerodhaBrokerGetMargins:
    """Test get_margins method."""

    @pytest.mark.asyncio
    async def test_get_margins(self, broker: ZerodhaBroker) -> None:
        """Test getting margin details."""
        margins = await broker.get_margins()
        assert margins.available_cash == Decimal("100000.0")
        assert margins.used_margin == Decimal("20000.0")
        assert margins.available_margin == Decimal("80000.0")
        assert margins.opening_balance == Decimal("100000.0")


class TestZerodhaBrokerGetOrderHistory:
    """Test get_order_history method."""

    @pytest.mark.asyncio
    async def test_get_order_history(self, broker: ZerodhaBroker) -> None:
        """Test getting order history."""
        broker._client.order_history.return_value = [
            {"status": "OPEN", "timestamp": datetime.now(UTC).isoformat()},
            {"status": "COMPLETE", "timestamp": datetime.now(UTC).isoformat()},
        ]
        history = await broker.get_order_history(order_id="ORD123456")
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_get_order_history_without_order_id_raises_error(
        self, broker: ZerodhaBroker
    ) -> None:
        """Test that getting history without order_id raises error."""
        with pytest.raises(ValueError, match="order_id is required"):
            await broker.get_order_history(order_id="")  # type: ignore[arg-type]


class TestZerodhaBrokerGetHoldings:
    """Test get_holdings method."""

    @pytest.mark.asyncio
    async def test_get_holdings(self, broker: ZerodhaBroker) -> None:
        """Test getting holdings."""
        broker._client.holdings.return_value = [
            {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "quantity": 10,
                "average_price": 2500.0,
                "last_price": 2600.0,
                "pnl": 1000.0,
            }
        ]
        holdings = await broker.get_holdings()
        assert len(holdings) == 1
        assert holdings[0]["tradingsymbol"] == "RELIANCE"


class TestZerodhaBrokerModifyOrder:
    """Test modify_order method."""

    @pytest.mark.asyncio
    async def test_modify_order_price(self, broker: ZerodhaBroker) -> None:
        """Test modifying order price."""
        broker._client.orders.return_value = [
            {
                "order_id": "ORD123456",
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "quantity": 10,
                "price": "2550.0",
                "trigger_price": "",
                "status": "OPEN",
                "product": "MIS",
                "order_timestamp": datetime.now(UTC).isoformat(),
                "filled_quantity": 0,
                "average_price": "",
            }
        ]
        order = await broker.modify_order(order_id="ORD123456", price=Decimal("2550.00"))
        assert order.price == Decimal("2550.0")

    @pytest.mark.asyncio
    async def test_modify_order_quantity(self, broker: ZerodhaBroker) -> None:
        """Test modifying order quantity."""
        broker._client.orders.return_value = [
            {
                "order_id": "ORD123456",
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "quantity": 20,
                "price": "2500.0",
                "trigger_price": "",
                "status": "OPEN",
                "product": "MIS",
                "order_timestamp": datetime.now(UTC).isoformat(),
                "filled_quantity": 0,
                "average_price": "",
            }
        ]
        order = await broker.modify_order(order_id="ORD123456", quantity=20)
        assert order.quantity == 20

    @pytest.mark.asyncio
    async def test_modify_order_with_invalid_quantity_raises_error(
        self, broker: ZerodhaBroker
    ) -> None:
        """Test that modifying with invalid quantity raises error."""
        with pytest.raises(ValueError, match="quantity must be positive"):
            await broker.modify_order(order_id="ORD123456", quantity=0)

    @pytest.mark.asyncio
    async def test_modify_order_without_order_id_raises_error(self, broker: ZerodhaBroker) -> None:
        """Test that modifying without order_id raises error."""
        with pytest.raises(ValueError, match="order_id is required"):
            await broker.modify_order(order_id="", price=Decimal("2500.00"))  # type: ignore[arg-type]


class TestZerodhaBrokerGetQuote:
    """Test get_quote method."""

    @pytest.mark.asyncio
    async def test_get_quote(self, broker: ZerodhaBroker) -> None:
        """Test getting quote for a symbol."""
        quote = await broker.get_quote(symbol="RELIANCE", exchange=Exchange.NSE)
        assert quote["last_price"] == 2500.0
        assert quote["instrument_token"] == "256265"

    @pytest.mark.asyncio
    async def test_get_quote_without_symbol_raises_error(self, broker: ZerodhaBroker) -> None:
        """Test that getting quote without symbol raises error."""
        with pytest.raises(ValueError, match="symbol is required"):
            await broker.get_quote(symbol="", exchange=Exchange.NSE)  # type: ignore[arg-type]


class TestZerodhaBrokerTypeConversions:
    """Test type conversion methods."""

    def test_parse_exchange(self) -> None:
        """Test exchange enum to string conversion."""
        assert ZerodhaBroker._parse_exchange(Exchange.NSE) == "NSE"
        assert ZerodhaBroker._parse_exchange(Exchange.NFO) == "NFO"

    def test_parse_order_type(self) -> None:
        """Test order type enum to string conversion."""
        assert ZerodhaBroker._parse_order_type(OrderType.MARKET) == "MARKET"
        assert ZerodhaBroker._parse_order_type(OrderType.STOP_LOSS) == "SL"
        assert ZerodhaBroker._parse_order_type(OrderType.STOP_LOSS_MARKET) == "SL-M"

    def test_parse_transaction_type(self) -> None:
        """Test transaction type enum to string conversion."""
        assert ZerodhaBroker._parse_transaction_type(TransactionType.BUY) == "BUY"
        assert ZerodhaBroker._parse_transaction_type(TransactionType.SELL) == "SELL"

    def test_parse_product_type(self) -> None:
        """Test product type enum to string conversion."""
        assert ZerodhaBroker._parse_product_type(ProductType.INTRADAY) == "MIS"
        assert ZerodhaBroker._parse_product_type(ProductType.DELIVERY) == "CNC"
        assert ZerodhaBroker._parse_product_type(ProductType.NRML) == "NRML"

    def test_parse_order_status(self) -> None:
        """Test string to order status enum conversion."""
        assert ZerodhaBroker._parse_order_status("COMPLETE") == OrderStatus.COMPLETE
        assert ZerodhaBroker._parse_order_status("OPEN") == OrderStatus.OPEN
        assert ZerodhaBroker._parse_order_status("CANCELLED") == OrderStatus.CANCELLED
        assert ZerodhaBroker._parse_order_status("UNKNOWN") == OrderStatus.PENDING

    def test_parse_exchange_from_str(self) -> None:
        """Test string to exchange enum conversion."""
        assert ZerodhaBroker._parse_exchange_from_str("NSE") == Exchange.NSE
        assert ZerodhaBroker._parse_exchange_from_str("NFO") == Exchange.NFO

    def test_parse_order_type_from_str(self) -> None:
        """Test string to order type enum conversion."""
        assert ZerodhaBroker._parse_order_type_from_str("MARKET") == OrderType.MARKET
        assert ZerodhaBroker._parse_order_type_from_str("SL") == OrderType.STOP_LOSS

    def test_parse_transaction_type_from_str(self) -> None:
        """Test string to transaction type enum conversion."""
        assert ZerodhaBroker._parse_transaction_type_from_str("BUY") == TransactionType.BUY
        assert ZerodhaBroker._parse_transaction_type_from_str("SELL") == TransactionType.SELL

    def test_parse_product_type_from_str(self) -> None:
        """Test string to product type enum conversion."""
        assert ZerodhaBroker._parse_product_type_from_str("MIS") == ProductType.INTRADAY
        assert ZerodhaBroker._parse_product_type_from_str("CNC") == ProductType.DELIVERY


class TestZerodhaBrokerErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_place_order_api_failure(self, broker: ZerodhaBroker) -> None:
        """Test handling of API failure when placing order."""
        broker._client.place_order.return_value = {}
        with pytest.raises(ConfigError, match="Non-retryable error: Failed to place order"):
            await broker.place_order(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                quantity=10,
            )

    @pytest.mark.asyncio
    async def test_cancel_order_api_failure(self, broker: ZerodhaBroker) -> None:
        """Test handling of API failure when canceling order."""
        broker._client.cancel_order.return_value = {}
        with pytest.raises(ConfigError, match="Non-retryable error: Failed to cancel order"):
            await broker.cancel_order(order_id="ORD123456")

    @pytest.mark.asyncio
    async def test_get_quote_empty_response(self, broker: ZerodhaBroker) -> None:
        """Test handling of empty quote response."""
        broker._client.quote.return_value = {}
        with pytest.raises(ConfigError, match="Non-retryable error: No quote data for RELIANCE"):
            await broker.get_quote(symbol="RELIANCE", exchange=Exchange.NSE)
