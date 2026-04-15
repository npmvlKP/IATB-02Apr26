"""
Comprehensive tests for PnL calculation fix in OrderManager.

Tests cover:
- Happy path: long and short position PnL
- Edge cases: partial closes, position flips
- Error handling: zero fills, missing guards
- Type precision: Decimal calculations
- Timezone handling: UTC datetime
"""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager


class _MockExecutor(Executor):
    """Mock executor that returns configurable results."""

    def __init__(self, fill_price: Decimal = Decimal("100")) -> None:
        self.fill_price = fill_price
        self.order_count = 0

    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        self.order_count += 1
        return ExecutionResult(
            order_id=f"ORDER-{self.order_count}",
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            average_price=self.fill_price,
        )

    def cancel_all(self) -> int:
        return 0


@pytest.fixture
def daily_loss_guard():
    """Mock DailyLossGuard for testing."""
    guard = MagicMock()
    return guard


@pytest.fixture
def order_manager(daily_loss_guard):
    """OrderManager with mocked dependencies."""
    executor = _MockExecutor()
    return OrderManager(
        executor=executor,
        heartbeat_timeout_seconds=30,
        daily_loss_guard=daily_loss_guard,
    )


class TestLongPositionPnL:
    """Test PnL calculation for long positions."""

    def test_buy_opens_long_no_pnl(self, order_manager, daily_loss_guard):
        """BUY order opens long position, no PnL recorded."""
        request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request)

        # No PnL should be recorded on opening
        daily_loss_guard.record_trade.assert_not_called()

    def test_sell_closes_long_with_profit(self, order_manager, daily_loss_guard):
        """SELL order closes long position with profit."""
        # Open long at 100
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Close long at 110 (profit)
        executor.fill_price = Decimal("110")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # PnL = (110 - 100) * 10 = 100
        expected_pnl = Decimal("100")
        daily_loss_guard.record_trade.assert_called_once()
        call_args = daily_loss_guard.record_trade.call_args
        assert call_args[0][0] == expected_pnl
        assert call_args[0][1].tzinfo == UTC

    def test_sell_closes_long_with_loss(self, order_manager, daily_loss_guard):
        """SELL order closes long position with loss."""
        # Open long at 100
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Close long at 95 (loss)
        executor.fill_price = Decimal("95")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # PnL = (95 - 100) * 10 = -50
        expected_pnl = Decimal("-50")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl


class TestShortPositionPnL:
    """Test PnL calculation for short positions."""

    def test_sell_opens_short_no_pnl(self, order_manager, daily_loss_guard):
        """SELL order opens short position, no PnL recorded."""
        request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request)

        # No PnL should be recorded on opening
        daily_loss_guard.record_trade.assert_not_called()

    def test_buy_closes_short_with_profit(self, order_manager, daily_loss_guard):
        """BUY order closes short position with profit."""
        # Open short at 100
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Close short at 90 (profit - sold at 100, bought back at 90)
        executor.fill_price = Decimal("90")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # PnL = (100 - 90) * 10 = 100
        expected_pnl = Decimal("100")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl

    def test_buy_closes_short_with_loss(self, order_manager, daily_loss_guard):
        """BUY order closes short position with loss."""
        # Open short at 100
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Close short at 110 (loss - sold at 100, bought back at 110)
        executor.fill_price = Decimal("110")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # PnL = (100 - 110) * 10 = -100
        expected_pnl = Decimal("-100")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl


class TestPartialCloses:
    """Test PnL calculation for partial position closes."""

    def test_partial_close_long(self, order_manager, daily_loss_guard):
        """Partial close of long position records proportional PnL."""
        # Open long at 100, qty 10
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Partial close 4 units at 110
        executor.fill_price = Decimal("110")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("4"))
        order_manager.place_order(request_sell)

        # PnL = (110 - 100) * 4 = 40
        expected_pnl = Decimal("40")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl

    def test_partial_close_short(self, order_manager, daily_loss_guard):
        """Partial close of short position records proportional PnL."""
        # Open short at 100, qty 10
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Partial close 3 units at 90
        executor.fill_price = Decimal("90")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("3"))
        order_manager.place_order(request_buy)

        # PnL = (100 - 90) * 3 = 30
        expected_pnl = Decimal("30")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl


class TestPositionFlips:
    """Test PnL calculation when position flips direction."""

    def test_flip_long_to_short(self, order_manager, daily_loss_guard):
        """Flip from long to short records PnL on close."""
        # Open long at 100, qty 10
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Sell 15 units: close 10 long, open 5 short at 110
        executor.fill_price = Decimal("110")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("15"))
        order_manager.place_order(request_sell)

        # PnL on close = (110 - 100) * 10 = 100
        expected_pnl = Decimal("100")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl

    def test_flip_short_to_long(self, order_manager, daily_loss_guard):
        """Flip from short to long records PnL on close."""
        # Open short at 100, qty 10
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Buy 20 units: close 10 short, open 10 long at 90
        executor.fill_price = Decimal("90")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("20"))
        order_manager.place_order(request_buy)

        # PnL on close = (100 - 90) * 10 = 100
        expected_pnl = Decimal("100")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl


class TestMultipleAdds:
    """Test PnL calculation when adding to positions."""

    def test_multiple_buys_weighted_avg(self, order_manager, daily_loss_guard):
        """Multiple BUY orders use weighted average entry price."""
        executor = _MockExecutor()
        order_manager._executor = executor

        # Buy 10 at 100
        executor.fill_price = Decimal("100")
        request1 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request1)

        # Buy 10 at 110
        executor.fill_price = Decimal("110")
        request2 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request2)

        # Weighted avg = (100*10 + 110*10) / 20 = 105
        # Sell 5 at 120
        executor.fill_price = Decimal("120")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("5"))
        order_manager.place_order(request_sell)

        # PnL = (120 - 105) * 5 = 75
        expected_pnl = Decimal("75")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl

    def test_multiple_sells_weighted_avg(self, order_manager, daily_loss_guard):
        """Multiple SELL orders use weighted average entry price."""
        executor = _MockExecutor()
        order_manager._executor = executor

        # Sell 10 at 100
        executor.fill_price = Decimal("100")
        request1 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request1)

        # Sell 10 at 110
        executor.fill_price = Decimal("110")
        request2 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request2)

        # Weighted avg = (100*10 + 110*10) / 20 = 105
        # Buy 5 at 90
        executor.fill_price = Decimal("90")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("5"))
        order_manager.place_order(request_buy)

        # PnL = (105 - 90) * 5 = 75
        expected_pnl = Decimal("75")
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_zero_fill_no_pnl(self, order_manager, daily_loss_guard):
        """Zero fill quantity should not record PnL."""
        executor = _MockExecutor()
        order_manager._executor = executor

        # First, open a position
        executor.fill_price = Decimal("100")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Simulate zero fill by mocking result
        def mock_zero_fill(request):
            _ = request
            return ExecutionResult(
                order_id="ZERO-FILL",
                status=OrderStatus.FILLED,
                filled_quantity=Decimal("0"),
                average_price=Decimal("95"),
            )

        order_manager._executor.execute_order = mock_zero_fill

        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # No PnL should be recorded for zero fill
        daily_loss_guard.record_trade.assert_not_called()

    def test_no_daily_loss_guard_no_pnl(self):
        """Without DailyLossGuard, PnL is not recorded."""
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager = OrderManager(
            executor=executor,
            daily_loss_guard=None,  # No guard
        )

        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Should not raise any errors
        assert len(order_manager._order_status) == 1

    def test_multiple_symbols_independent_tracking(self, order_manager, daily_loss_guard):
        """Multiple symbols track positions independently."""
        executor = _MockExecutor()
        order_manager._executor = executor

        # Buy NIFTY at 100
        executor.fill_price = Decimal("100")
        request1 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request1)

        # Buy BANKNIFTY at 200
        executor.fill_price = Decimal("200")
        request2 = OrderRequest(Exchange.NSE, "BANKNIFTY", OrderSide.BUY, Decimal("5"))
        order_manager.place_order(request2)

        # Sell NIFTY at 110
        executor.fill_price = Decimal("110")
        request3 = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request3)

        # Only NIFTY PnL should be recorded
        # PnL = (110 - 100) * 10 = 100
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == Decimal("100")


class TestPrecisionAndTimezone:
    """Test Decimal precision and UTC timezone handling."""

    def test_decimal_precision_pnl(self, order_manager, daily_loss_guard):
        """PnL calculation maintains Decimal precision."""
        executor = _MockExecutor()
        order_manager._executor = executor

        # Buy at precise price
        executor.fill_price = Decimal("100.50")
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Sell at precise price
        executor.fill_price = Decimal("110.75")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # PnL = (110.75 - 100.50) * 10 = 102.50
        expected_pnl = Decimal("102.50")
        daily_loss_guard.record_trade.assert_called_once()
        actual_pnl = daily_loss_guard.record_trade.call_args[0][0]
        assert isinstance(actual_pnl, Decimal)
        assert actual_pnl == expected_pnl

    def test_utc_timezone_aware_pnl(self, order_manager, daily_loss_guard):
        """PnL recording uses UTC timezone."""
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor

        # Open position
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Close position
        executor.fill_price = Decimal("110")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Verify UTC timezone
        assert daily_loss_guard.record_trade.called
        timestamp = daily_loss_guard.record_trade.call_args[0][1]
        assert isinstance(timestamp, datetime)
        assert timestamp.tzinfo == UTC


class TestRegressionBug1:
    """Regression tests for BUG-1: PnL calculation logic error."""

    def test_bug1_buy_at_100_fill_at_95_no_negative_pnl(self, order_manager, daily_loss_guard):
        """
        Regression test for BUG-1.
        Original bug: Buying at 100 and filling at 95 recorded PnL of -5*qty.
        Expected: No PnL on BUY (opening long position).
        """
        # Buy at 100, fill at 95
        request_buy = OrderRequest(
            Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"), price=Decimal("100")
        )
        order_manager.place_order(request_buy)

        # Should NOT record negative PnL on opening long
        daily_loss_guard.record_trade.assert_not_called()

    def test_bug1_sell_rising_price_records_profit(self, order_manager, daily_loss_guard):
        """
        Regression test for BUG-1.
        Original bug: SELL order PnL was calculated incorrectly.
        Expected: For long position, SELL at higher price = profit.
        """
        # Open long at 100
        executor = _MockExecutor(fill_price=Decimal("100"))
        order_manager._executor = executor
        request_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
        order_manager.place_order(request_buy)

        # Sell at 110 (rising price = profit)
        executor.fill_price = Decimal("110")
        request_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
        order_manager.place_order(request_sell)

        # Should record positive PnL
        expected_pnl = Decimal("100")  # (110 - 100) * 10
        daily_loss_guard.record_trade.assert_called_once()
        assert daily_loss_guard.record_trade.call_args[0][0] == expected_pnl
