"""
Tests for LiveExecutor with comprehensive coverage.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from iatb.broker.base import (
    BrokerInterface,
    Order,
    ProductType,
    TransactionType,
)
from iatb.broker.base import (
    Exchange as BrokerExchange,
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


@pytest.fixture
def mock_broker() -> MagicMock:
    """Create mock broker interface."""
    broker = MagicMock(spec=BrokerInterface)
    broker.place_order = AsyncMock()
    broker.cancel_order = AsyncMock()
    broker.get_orders = AsyncMock(return_value=[])
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_margins = AsyncMock()
    broker.get_order_history = AsyncMock()
    broker.get_holdings = AsyncMock()
    broker.modify_order = AsyncMock()
    broker.get_quote = AsyncMock()
    return broker


@pytest.fixture
def live_executor(mock_broker: MagicMock) -> LiveExecutor:
    """Create live executor with mock broker."""
    return LiveExecutor(broker=mock_broker)


def test_live_executor_initialization_success(mock_broker: MagicMock) -> None:
    """Test successful initialization with valid parameters."""
    executor = LiveExecutor(
        broker=mock_broker,
        confirmation_timeout_seconds=10,
        confirmation_poll_interval_seconds=0.5,
        slippage_tolerance_bps=Decimal("15"),
    )

    assert executor._broker is mock_broker
    assert executor._confirmation_timeout_seconds == 10
    assert executor._confirmation_poll_interval == 0.5
    assert executor._slippage_tolerance_bps == Decimal("15")
    assert len(executor._open_orders) == 0


def test_live_executor_initialization_defaults(mock_broker: MagicMock) -> None:
    """Test initialization with default values."""
    executor = LiveExecutor(broker=mock_broker)

    assert executor._confirmation_timeout_seconds == 30
    assert executor._confirmation_poll_interval == 0.5
    assert executor._slippage_tolerance_bps == Decimal("20")


def test_live_executor_initialization_no_broker() -> None:
    """Test that initialization fails without broker."""
    with pytest.raises(ValueError, match="broker is required"):
        LiveExecutor(broker=None)  # type: ignore[arg-type]


def test_live_executor_initialization_invalid_timeout(mock_broker: MagicMock) -> None:
    """Test that invalid timeout raises error."""
    with pytest.raises(ValueError, match="confirmation_timeout_seconds must be positive"):
        LiveExecutor(broker=mock_broker, confirmation_timeout_seconds=0)


def test_live_executor_initialization_invalid_poll_interval(mock_broker: MagicMock) -> None:
    """Test that invalid poll interval raises error."""
    with pytest.raises(ValueError, match="confirmation_poll_interval_seconds must be positive"):
        LiveExecutor(broker=mock_broker, confirmation_poll_interval_seconds=-1.0)


def test_live_executor_initialization_negative_slippage(mock_broker: MagicMock) -> None:
    """Test that negative slippage tolerance raises error."""
    with pytest.raises(ValueError, match="slippage_tolerance_bps cannot be negative"):
        LiveExecutor(broker=mock_broker, slippage_tolerance_bps=Decimal("-5"))


def test_execute_order_happy_path_buy(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test successful buy order execution."""
    # Setup mock broker response
    broker_order = Order(
        order_id="LIVE-000001",
        symbol="RELIANCE",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=10,
        average_price=Decimal("2500.50"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    # Execute order
    request = OrderRequest(
        Exchange.NSE,
        "RELIANCE",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.MARKET,
        price=Decimal("2500"),
    )

    result = live_executor.execute_order(request)

    # Verify result
    assert result.order_id == "LIVE-000001"
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("10")
    assert result.average_price == Decimal("2500.50")
    assert "broker order" in result.message

    # Verify broker was called
    mock_broker.place_order.assert_called_once()
    mock_broker.get_orders.assert_called()


def test_execute_order_happy_path_sell(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test successful sell order execution."""
    broker_order = Order(
        order_id="LIVE-000002",
        symbol="INFY",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.SELL,
        order_type=BrokerOrderType.LIMIT,
        quantity=50,
        price=Decimal("1500"),
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=50,
        average_price=Decimal("1499.75"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "INFY",
        OrderSide.SELL,
        Decimal("50"),
        OrderType.LIMIT,
        price=Decimal("1500"),
    )

    result = live_executor.execute_order(request)

    assert result.order_id == "LIVE-000002"
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("50")
    assert result.average_price == Decimal("1499.75")


def test_execute_order_partial_fill(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test handling of partial fills."""
    broker_order = Order(
        order_id="LIVE-000003",
        symbol="TCS",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=100,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.OPEN,  # Still open, but partially filled
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=60,  # Partial fill
        average_price=Decimal("3500.25"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "TCS",
        OrderSide.BUY,
        Decimal("100"),
        OrderType.MARKET,
        price=Decimal("3500"),
    )

    result = live_executor.execute_order(request)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == Decimal("60")
    assert result.average_price == Decimal("3500.25")


def test_execute_order_rejected(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test handling of rejected orders."""
    broker_order = Order(
        order_id="LIVE-000004",
        symbol="WIPRO",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=100,
        price=Decimal("400"),
        trigger_price=None,
        status=BrokerOrderStatus.REJECTED,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=0,
        average_price=None,
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "WIPRO",
        OrderSide.BUY,
        Decimal("100"),
        OrderType.LIMIT,
        price=Decimal("400"),
    )

    with pytest.raises(ExecutionError, match="Order LIVE-000004 was rejected"):
        live_executor.execute_order(request)


def test_execute_order_timeout(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test order confirmation timeout."""
    pending_order = Order(
        order_id="LIVE-000005",
        symbol="HDFC",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.OPEN,  # Stays open
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=0,
        average_price=None,
    )

    mock_broker.place_order.return_value = pending_order
    mock_broker.get_orders.return_value = [pending_order]

    request = OrderRequest(
        Exchange.NSE,
        "HDFC",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.MARKET,
    )

    # Use short timeout for test
    executor = LiveExecutor(
        broker=mock_broker,
        confirmation_timeout_seconds=1,
        confirmation_poll_interval_seconds=0.1,
    )

    with pytest.raises(ExecutionError, match="Order confirmation timeout"):
        executor.execute_order(request)


def test_slippage_within_tolerance_buy(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test slippage within tolerance for buy order."""
    # Expected: 100, Filled: 100.15 (0.15% slippage, within 0.20% tolerance)
    broker_order = Order(
        order_id="LIVE-000006",
        symbol="TATASTEEL",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=100,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=100,
        average_price=Decimal("100.15"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "TATASTEEL",
        OrderSide.BUY,
        Decimal("100"),
        OrderType.MARKET,
        price=Decimal("100"),
    )

    result = live_executor.execute_order(request)
    assert result.status == OrderStatus.FILLED


def test_slippage_within_tolerance_sell(
    live_executor: LiveExecutor, mock_broker: MagicMock
) -> None:
    """Test slippage within tolerance for sell order."""
    # Expected: 200, Filled: 199.80 (0.10% slippage, within 0.20% tolerance)
    broker_order = Order(
        order_id="LIVE-000007",
        symbol="MARUTI",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.SELL,
        order_type=BrokerOrderType.MARKET,
        quantity=50,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=50,
        average_price=Decimal("199.80"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "MARUTI",
        OrderSide.SELL,
        Decimal("50"),
        OrderType.MARKET,
        price=Decimal("200"),
    )

    result = live_executor.execute_order(request)
    assert result.status == OrderStatus.FILLED


def test_slippage_exceeds_tolerance(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test slippage exceeding tolerance raises error."""
    # Expected: 100, Filled: 100.50 (0.50% slippage, exceeds 0.20% tolerance)
    broker_order = Order(
        order_id="LIVE-000008",
        symbol="SBIN",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=100,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=100,
        average_price=Decimal("100.50"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "SBIN",
        OrderSide.BUY,
        Decimal("100"),
        OrderType.MARKET,
        price=Decimal("100"),
    )

    with pytest.raises(ExecutionError, match="Slippage exceeded tolerance"):
        live_executor.execute_order(request)


def test_slippage_check_skipped_without_expected_price(
    live_executor: LiveExecutor,
    mock_broker: MagicMock,
) -> None:
    """Test that slippage check is skipped when no expected price."""
    broker_order = Order(
        order_id="LIVE-000009",
        symbol="ICICIBANK",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=100,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=100,
        average_price=Decimal("500.75"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "ICICIBANK",
        OrderSide.BUY,
        Decimal("100"),
        OrderType.MARKET,
        # No expected price - slippage check skipped
    )

    result = live_executor.execute_order(request)
    assert result.status == OrderStatus.FILLED


def test_map_exchange() -> None:
    """Test exchange mapping from core to broker."""
    mock_broker = MagicMock(spec=BrokerInterface)
    mock_broker.place_order = AsyncMock()
    mock_broker.get_orders = AsyncMock(return_value=[])

    executor = LiveExecutor(broker=mock_broker)

    # Test NSE
    assert executor._map_exchange(Exchange.NSE) == BrokerExchange.NSE
    # Test BSE
    assert executor._map_exchange(Exchange.BSE) == BrokerExchange.BSE
    # Test MCX
    assert executor._map_exchange(Exchange.MCX) == BrokerExchange.MCX
    # Test fallback for CDS
    assert executor._map_exchange(Exchange.CDS) == BrokerExchange.MCX


def test_map_side() -> None:
    """Test side mapping from core to broker."""
    mock_broker = MagicMock(spec=BrokerInterface)
    mock_broker.place_order = AsyncMock()
    mock_broker.get_orders = AsyncMock(return_value=[])

    executor = LiveExecutor(broker=mock_broker)

    assert executor._map_side(OrderSide.BUY) == TransactionType.BUY
    assert executor._map_side(OrderSide.SELL) == TransactionType.SELL


def test_map_order_type() -> None:
    """Test order type mapping from core to broker."""
    mock_broker = MagicMock(spec=BrokerInterface)
    mock_broker.place_order = AsyncMock()
    mock_broker.get_orders = AsyncMock(return_value=[])

    executor = LiveExecutor(broker=mock_broker)

    assert executor._map_order_type(OrderType.MARKET) == BrokerOrderType.MARKET
    assert executor._map_order_type(OrderType.LIMIT) == BrokerOrderType.LIMIT
    assert executor._map_order_type(OrderType.STOP_LOSS) == BrokerOrderType.STOP_LOSS
    assert executor._map_order_type(OrderType.STOP_LOSS_MARKET) == BrokerOrderType.STOP_LOSS_MARKET


def test_map_broker_status() -> None:
    """Test status mapping from broker to core."""
    assert LiveExecutor._map_broker_status(BrokerOrderStatus.COMPLETE) == OrderStatus.FILLED
    assert LiveExecutor._map_broker_status(BrokerOrderStatus.REJECTED) == OrderStatus.REJECTED
    assert LiveExecutor._map_broker_status(BrokerOrderStatus.CANCELLED) == OrderStatus.CANCELLED
    assert LiveExecutor._map_broker_status(BrokerOrderStatus.PENDING) == OrderStatus.PENDING
    assert LiveExecutor._map_broker_status(BrokerOrderStatus.OPEN) == OrderStatus.OPEN


def test_cancel_all_empty(live_executor: LiveExecutor) -> None:
    """Test cancel_all with no open orders."""
    count = live_executor.cancel_all()
    assert count == 0


def test_cancel_all_success(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test successful cancellation of all orders."""
    # Add some orders to open_orders
    live_executor._open_orders.add("LIVE-000001")
    live_executor._open_orders.add("LIVE-000002")
    live_executor._open_orders.add("LIVE-000003")

    mock_broker.cancel_order = AsyncMock(return_value=None)

    count = live_executor.cancel_all()

    assert count == 3
    assert len(live_executor._open_orders) == 0
    assert mock_broker.cancel_order.call_count == 3


def test_cancel_all_partial_failure(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test cancel_all with some failures."""
    live_executor._open_orders.add("LIVE-000001")
    live_executor._open_orders.add("LIVE-000002")

    # First succeeds, second fails
    async def side_effect(order_id: str) -> None:
        if order_id == "LIVE-000002":
            raise RuntimeError("Network error")

    mock_broker.cancel_order = AsyncMock(side_effect=side_effect)

    count = live_executor.cancel_all()

    # Should still clear open_orders set
    assert count == 1  # Only first succeeded
    assert len(live_executor._open_orders) == 0


def test_close_order_success(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test successful order closure."""
    live_executor._open_orders.add("LIVE-000001")
    mock_broker.cancel_order = AsyncMock(return_value=None)

    result = live_executor.close_order("LIVE-000001")

    assert result is True
    assert "LIVE-000001" not in live_executor._open_orders
    mock_broker.cancel_order.assert_called_once_with(order_id="LIVE-000001")


def test_close_order_not_found(live_executor: LiveExecutor) -> None:
    """Test closing non-existent order."""
    result = live_executor.close_order("LIVE-999999")
    assert result is False


def test_close_order_already_closed(live_executor: LiveExecutor) -> None:
    """Test closing an already closed order."""
    live_executor._open_orders.add("LIVE-000001")
    live_executor._open_orders.discard("LIVE-000001")

    result = live_executor.close_order("LIVE-000001")
    assert result is False


def test_close_order_failure(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test closing order with broker failure."""
    live_executor._open_orders.add("LIVE-000001")
    mock_broker.cancel_order = AsyncMock(side_effect=RuntimeError("Network error"))

    result = live_executor.close_order("LIVE-000001")

    # Order should remain in open_orders on failure
    assert result is False
    assert "LIVE-000001" in live_executor._open_orders


def test_convert_broker_order_to_result_complete() -> None:
    """Test conversion of complete broker order to result."""
    broker_order = Order(
        order_id="LIVE-000001",
        symbol="RELIANCE",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=10,
        average_price=Decimal("2500.50"),
    )

    mock_broker = MagicMock(spec=BrokerInterface)
    mock_broker.place_order = AsyncMock()
    mock_broker.get_orders = AsyncMock(return_value=[])

    executor = LiveExecutor(broker=mock_broker)
    result = executor._convert_broker_order_to_result(broker_order)

    assert result.order_id == "LIVE-000001"
    assert result.status == OrderStatus.FILLED
    assert result.filled_quantity == Decimal("10")
    assert result.average_price == Decimal("2500.50")


def test_convert_broker_order_to_result_partial() -> None:
    """Test conversion of partially filled broker order to result."""
    broker_order = Order(
        order_id="LIVE-000002",
        symbol="INFY",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=100,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=60,
        average_price=Decimal("1500.25"),
    )

    mock_broker = MagicMock(spec=BrokerInterface)
    mock_broker.place_order = AsyncMock()
    mock_broker.get_orders = AsyncMock(return_value=[])

    executor = LiveExecutor(broker=mock_broker)
    result = executor._convert_broker_order_to_result(broker_order)

    assert result.status == OrderStatus.PARTIALLY_FILLED
    assert result.filled_quantity == Decimal("60")


def test_decimal_precision_handling(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test that Decimal precision is maintained throughout execution."""
    # High precision price
    expected_price = Decimal("1234.5678")
    filled_price = Decimal("1234.5890")

    broker_order = Order(
        order_id="LIVE-000001",
        symbol="RELIANCE",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.LIMIT,
        quantity=10,
        price=expected_price,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=10,
        average_price=filled_price,
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "RELIANCE",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.LIMIT,
        price=expected_price,
    )

    result = live_executor.execute_order(request)

    # Verify precision is maintained
    assert isinstance(result.filled_quantity, Decimal)
    assert isinstance(result.average_price, Decimal)
    assert result.filled_quantity == Decimal("10")
    assert result.average_price == filled_price


def test_utc_datetime_in_broker_order(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test that broker order uses UTC-aware datetime."""
    utc_time = datetime.now(UTC)

    broker_order = Order(
        order_id="LIVE-000001",
        symbol="RELIANCE",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=utc_time,  # UTC-aware
        filled_quantity=10,
        average_price=Decimal("2500.50"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "RELIANCE",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.MARKET,
    )

    result = live_executor.execute_order(request)
    assert result.status == OrderStatus.FILLED


def test_no_float_usage(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test that no float types are used in financial calculations."""
    broker_order = Order(
        order_id="LIVE-000001",
        symbol="RELIANCE",
        exchange=BrokerExchange.NSE,
        transaction_type=TransactionType.BUY,
        order_type=BrokerOrderType.MARKET,
        quantity=10,
        price=None,
        trigger_price=None,
        status=BrokerOrderStatus.COMPLETE,
        product_type=ProductType.INTRADAY,
        timestamp=datetime.now(UTC),
        filled_quantity=10,
        average_price=Decimal("2500.50"),
    )

    mock_broker.place_order.return_value = broker_order
    mock_broker.get_orders.return_value = [broker_order]

    request = OrderRequest(
        Exchange.NSE,
        "RELIANCE",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.MARKET,
        price=Decimal("2500"),
    )

    result = live_executor.execute_order(request)

    # All financial values should be Decimal
    assert isinstance(result.filled_quantity, Decimal)
    assert isinstance(result.average_price, Decimal)
    assert not isinstance(result.filled_quantity, float)
    assert not isinstance(result.average_price, float)


def test_execute_order_broker_exception(
    live_executor: LiveExecutor, mock_broker: MagicMock
) -> None:
    """Test handling of broker exceptions during order execution."""
    mock_broker.place_order.side_effect = RuntimeError("API error")

    request = OrderRequest(
        Exchange.NSE,
        "RELIANCE",
        OrderSide.BUY,
        Decimal("10"),
        OrderType.MARKET,
    )

    with pytest.raises(ExecutionError, match="Order execution failed"):
        live_executor.execute_order(request)


def test_multiple_sequential_orders(live_executor: LiveExecutor, mock_broker: MagicMock) -> None:
    """Test multiple sequential order executions."""
    order_id_counter = 0
    placed_orders: list[Order] = []

    async def create_order(*args: Any, **kwargs: Any) -> Order:
        nonlocal order_id_counter
        order_id_counter += 1
        order = Order(
            order_id=f"LIVE-{order_id_counter:06d}",
            symbol=kwargs.get("symbol", "TEST"),
            exchange=kwargs.get("exchange", BrokerExchange.NSE),
            transaction_type=kwargs.get("transaction_type", TransactionType.BUY),
            order_type=kwargs.get("order_type", BrokerOrderType.MARKET),
            quantity=kwargs.get("quantity", 10),
            price=None,
            trigger_price=None,
            status=BrokerOrderStatus.COMPLETE,
            product_type=ProductType.INTRADAY,
            timestamp=datetime.now(UTC),
            filled_quantity=kwargs.get("quantity", 10),
            average_price=Decimal("100"),
        )
        placed_orders.append(order)
        return order

    async def get_orders_list(*args: Any, **kwargs: Any) -> list[Order]:
        return list(placed_orders)

    mock_broker.place_order.side_effect = create_order
    mock_broker.get_orders.side_effect = get_orders_list

    # Execute multiple orders
    results = []
    for i in range(5):
        request = OrderRequest(
            Exchange.NSE,
            f"STOCK{i}",
            OrderSide.BUY,
            Decimal("10"),
            OrderType.MARKET,
        )
        result = live_executor.execute_order(request)
        results.append(result)

    assert len(results) == 5
    assert all(r.status == OrderStatus.FILLED for r in results)
    assert len(live_executor._open_orders) == 5
