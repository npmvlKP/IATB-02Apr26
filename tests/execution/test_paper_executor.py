import random
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, MarketType, OrderSide, OrderStatus
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import (
    PaperExecutor,
    _resolve_base_slippage,
    _volume_adjustment_factor,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


# ---------------------------------------------------------------------------
# Existing tests (backward compatible)
# ---------------------------------------------------------------------------


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
        order_ids: list[str] = []
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


# ---------------------------------------------------------------------------
# New slippage model tests
# ---------------------------------------------------------------------------


def test_resolve_base_slippage_nse_spot() -> None:
    assert _resolve_base_slippage(Exchange.NSE, MarketType.SPOT) == Decimal("3")


def test_resolve_base_slippage_nse_futures() -> None:
    assert _resolve_base_slippage(Exchange.NSE, MarketType.FUTURES) == Decimal("2")


def test_resolve_base_slippage_nse_options() -> None:
    assert _resolve_base_slippage(Exchange.NSE, MarketType.OPTIONS) == Decimal("2")


def test_resolve_base_slippage_bse() -> None:
    assert _resolve_base_slippage(Exchange.BSE, MarketType.SPOT) == Decimal("5")


def test_resolve_base_slippage_mcx() -> None:
    assert _resolve_base_slippage(Exchange.MCX, MarketType.SPOT) == Decimal("8")
    assert _resolve_base_slippage(Exchange.MCX, MarketType.FUTURES) == Decimal("8")
    assert _resolve_base_slippage(Exchange.MCX, MarketType.OPTIONS) == Decimal("8")


def test_resolve_base_slippage_fallback() -> None:
    # Any unmapped combination defaults to 5 bps
    assert _resolve_base_slippage(Exchange.BINANCE, MarketType.SPOT) == Decimal("5")
    assert _resolve_base_slippage(Exchange.CDS, MarketType.FUTURES) == Decimal("5")


# Volume adjustment tests


def test_volume_adjustment_factor_small_quantity() -> None:
    factor = _volume_adjustment_factor(Decimal("1"))
    assert Decimal("0.9") < factor <= Decimal("1.0")


def test_volume_adjustment_factor_large_quantity() -> None:
    factor = _volume_adjustment_factor(Decimal("100000"))
    # Should be reduced but floored at 0.5
    assert Decimal("0.5") <= factor < Decimal("1.0")


def test_volume_adjustment_factor_monotonic() -> None:
    """Ensure that higher quantity never increases slippage factor."""
    prev = Decimal("1.0")
    for qty in [1, 10, 100, 1000, 10000, 100000]:
        factor = _volume_adjustment_factor(Decimal(str(qty)))
        assert factor <= prev, f"factor increased at quantity={qty}"
        prev = factor


def test_volume_adjustment_factor_floor() -> None:
    """Very large quantities should asymptotically approach (but not exceed) 0.5."""
    factor = _volume_adjustment_factor(Decimal("9999999999"))
    assert Decimal("0.5") <= factor < Decimal("0.52")


# Exchange-specific slippage e2e tests (no slippage_bps override)


def test_exchange_specific_slippage_nse_spot() -> None:
    executor = PaperExecutor()  # no override
    request = OrderRequest(
        Exchange.NSE, "RELIANCE", OrderSide.BUY, Decimal("10"), price=Decimal("1000")
    )
    result = executor.execute_order(request)
    # base 3 bps, volume adjustment ~0.9057
    # effective ~2.717 bps
    # slippage = 1000 * 2.71705 / 10000 = 0.271705
    # price ≈ 1000.271705
    expected = Decimal("1000.271704855134133785418023")
    assert result.average_price == expected


def test_exchange_specific_slippage_nse_futures() -> None:
    executor = PaperExecutor()
    request = OrderRequest(
        Exchange.NSE,
        "NIFTY25JUNFUT",
        OrderSide.BUY,
        Decimal("50"),
        price=Decimal("20000"),
        market_type=MarketType.FUTURES,
    )
    result = executor.execute_order(request)
    # base 2 bps * ~0.854148 factor = ~1.708 bps
    # slippage = 20000 * 1.708296 / 10000 = 3.41659
    expected = Decimal("20003.41659280263496680169746")
    assert result.average_price == expected


def test_exchange_specific_slippage_bse() -> None:
    executor = PaperExecutor()
    request = OrderRequest(Exchange.BSE, "TCS", OrderSide.BUY, Decimal("5"), price=Decimal("500"))
    result = executor.execute_order(request)
    # base 5 bps * ~0.927803 = ~4.639 bps
    # slippage = 500 * 4.639015 / 10000 = 0.231951
    expected = Decimal("500.2319507253074606453236064")
    assert result.average_price == expected


def test_exchange_specific_slippage_mcx() -> None:
    executor = PaperExecutor()
    request = OrderRequest(Exchange.MCX, "GOLD", OrderSide.BUY, Decimal("2"), price=Decimal("3000"))
    result = executor.execute_order(request)
    # base 8 bps * ~0.954461 = ~7.636 bps
    # slippage = 3000 * 7.635685 / 10000 = 2.290706
    expected = Decimal("3002.290705568496560347363350")
    assert result.average_price == expected


def test_exchange_specific_slippage_sell_side() -> None:
    executor = PaperExecutor()
    request = OrderRequest(Exchange.NSE, "INFY", OrderSide.SELL, Decimal("1"), price=Decimal("100"))
    result = executor.execute_order(request)
    # base 3 bps * ~0.970777 = ~2.912 bps
    # slippage = 100 * 2.91233 / 10000 = 0.0291233
    # sell => 100 - 0.0291233 = 99.970877
    expected = Decimal("99.97087669872563431211794223")
    assert result.average_price == expected


# Volume adjustment e2e tests


def test_volume_adjustment_lowers_slippage() -> None:
    """Higher volume should result in lower effective slippage."""
    executor = PaperExecutor()
    # Low quantity
    req_low = OrderRequest(Exchange.NSE, "A", OrderSide.BUY, Decimal("1"), price=Decimal("100"))
    # High quantity
    req_high = OrderRequest(
        Exchange.NSE, "A", OrderSide.BUY, Decimal("100000"), price=Decimal("100")
    )

    result_low = executor.execute_order(req_low)
    result_high = executor.execute_order(req_high)

    slip_low = result_low.average_price - Decimal("100")
    slip_high = result_high.average_price - Decimal("100")

    assert slip_high < slip_low, "Higher volume should have lower slippage per unit"


# Override still takes priority


def test_override_bps_takes_priority() -> None:
    """When slippage_bps is explicitly provided, it should override exchange-specific."""
    executor = PaperExecutor(slippage_bps=Decimal("50"))
    request = OrderRequest(Exchange.NSE, "X", OrderSide.BUY, Decimal("1"), price=Decimal("100"))
    result = executor.execute_order(request)
    # 50 bps = 0.5%
    # slippage = 100 * 0.005 = 0.50
    assert result.average_price == Decimal("100.50")


# Edge case: zero / negative quantity should not crash


def test_quantity_zero_slippage_computation() -> None:
    """Zero quantity should use max factor (1.0 -> no adjustment)."""
    # We avoid actual qty=0 because OrderRequest validates qty>0,
    # but the internal _volume_adjustment_factor must be robust.
    factor = _volume_adjustment_factor(Decimal("0.0001"))
    assert Decimal("0.9") < factor <= Decimal("1.0")
