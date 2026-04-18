import random
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import PaperExecutor

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_paper_executor_end_to_end_buy_and_sell() -> None:
    executor = PaperExecutor(slippage_bps=Decimal("10"))
    buy_request = OrderRequest(
        Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("2"), price=Decimal("100")
    )
    sell_request = OrderRequest(
        Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("1"), price=Decimal("100")
    )
    buy_result = executor.execute_order(buy_request)
    sell_result = executor.execute_order(sell_request)
    assert buy_result.order_id == "PAPER-000001"
    assert sell_result.order_id == "PAPER-000002"
    assert buy_result.status == OrderStatus.FILLED
    assert buy_result.average_price == Decimal("100.10")
    assert sell_result.average_price == Decimal("99.90")
    assert executor.cancel_all() == 2


def test_paper_executor_thread_safe_counter() -> None:
    """Test that counter is thread-safe using itertools.count()."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))
    num_threads = 10
    orders_per_thread = 100
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))

    def execute_orders() -> list[str]:
        return [executor.execute_order(request).order_id for _ in range(orders_per_thread)]

    with ThreadPoolExecutor(max_workers=num_threads) as executor_pool:
        results = list(executor_pool.map(lambda _: execute_orders(), range(num_threads)))

    # Flatten results
    all_order_ids = [order_id for thread_results in results for order_id in thread_results]

    # Check that all order IDs are unique
    assert len(all_order_ids) == len(set(all_order_ids)), "Duplicate order IDs found"

    # Check that all order IDs are in correct format and sequence
    expected_ids = {f"PAPER-{i:06d}" for i in range(1, num_threads * orders_per_thread + 1)}
    actual_ids = set(all_order_ids)
    assert actual_ids == expected_ids, f"Expected {expected_ids}, got {actual_ids}"

    # Verify all orders are in open_orders set
    assert len(executor._open_orders) == num_threads * orders_per_thread


def test_paper_executor_order_lifecycle() -> None:
    """Test proper order lifecycle: add, keep, close individually, cancel_all."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))

    # Execute 3 orders
    result1 = executor.execute_order(request)
    result2 = executor.execute_order(request)
    result3 = executor.execute_order(request)

    # Verify all orders are in open_orders
    assert len(executor._open_orders) == 3
    assert result1.order_id in executor._open_orders
    assert result2.order_id in executor._open_orders
    assert result3.order_id in executor._open_orders

    # Close one order individually
    assert executor.close_order(result1.order_id) is True
    assert len(executor._open_orders) == 2
    assert result1.order_id not in executor._open_orders
    assert result2.order_id in executor._open_orders
    assert result3.order_id in executor._open_orders

    # Try to close already closed order
    assert executor.close_order(result1.order_id) is False
    assert len(executor._open_orders) == 2

    # Try to close non-existent order
    assert executor.close_order("PAPER-999999") is False
    assert len(executor._open_orders) == 2

    # Cancel remaining orders
    cancelled = executor.cancel_all()
    assert cancelled == 2
    assert len(executor._open_orders) == 0


def test_paper_executor_close_order_edge_cases() -> None:
    """Test close_order edge cases."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))

    # Close order from empty set
    assert executor.close_order("PAPER-000001") is False
    assert len(executor._open_orders) == 0

    # Execute order
    result = executor.execute_order(request)
    assert result.order_id in executor._open_orders

    # Close with exact order ID
    assert executor.close_order(result.order_id) is True
    assert len(executor._open_orders) == 0

    # Try to close same order again
    assert executor.close_order(result.order_id) is False
    assert len(executor._open_orders) == 0


def test_paper_executor_slippage_calculation() -> None:
    """Test slippage is applied correctly for buy and sell orders."""
    executor = PaperExecutor(slippage_bps=Decimal("10"))
    buy_request = OrderRequest(
        Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("1000")
    )
    sell_request = OrderRequest(
        Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("1"), price=Decimal("1000")
    )

    buy_result = executor.execute_order(buy_request)
    sell_result = executor.execute_order(sell_request)

    # Buy: price + slippage = 1000 + 1.0 = 1001.0
    assert buy_result.average_price == Decimal("1001.0")
    # Sell: price - slippage = 1000 - 1.0 = 999.0
    assert sell_result.average_price == Decimal("999.0")


def test_paper_executor_default_price() -> None:
    """Test that default price of 100 is used when no price provided."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))
    request = OrderRequest(
        Exchange.NSE,
        "NIFTY",
        OrderSide.BUY,
        Decimal("1"),  # No price
    )
    result = executor.execute_order(request)
    # Default price 100 + 5 bps slippage (0.05) = 100.05
    assert result.average_price == Decimal("100.05")


def test_paper_executor_invalid_slippage() -> None:
    """Test that negative slippage raises ConfigError."""
    from iatb.core.exceptions import ConfigError

    with pytest.raises(ConfigError, match="slippage_bps cannot be negative"):
        PaperExecutor(slippage_bps=Decimal("-5"))


def test_paper_executor_concurrent_lifecycle_operations() -> None:
    """Test concurrent order execution and closing operations."""
    executor = PaperExecutor(slippage_bps=Decimal("5"))
    num_threads = 5
    orders_per_thread = 20
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))

    def execute_and_close() -> int:
        """Execute orders and close half of them."""
        order_ids = []
        for _ in range(orders_per_thread):
            result = executor.execute_order(request)
            order_ids.append(result.order_id)

        # Close half the orders
        closed_count = 0
        for i, order_id in enumerate(order_ids):
            if i % 2 == 0:  # Close every other order
                if executor.close_order(order_id):
                    closed_count += 1

        return closed_count

    with ThreadPoolExecutor(max_workers=num_threads) as executor_pool:
        closed_counts = list(executor_pool.map(lambda _: execute_and_close(), range(num_threads)))

    total_closed = sum(closed_counts)
    total_orders = num_threads * orders_per_thread
    remaining_orders = total_orders - total_closed

    # Verify counts
    assert len(executor._open_orders) == remaining_orders
    assert total_closed > 0, "Some orders should have been closed"

    # Cancel remaining orders
    cancelled = executor.cancel_all()
    assert cancelled == remaining_orders
    assert len(executor._open_orders) == 0
