from decimal import Decimal
from unittest.mock import MagicMock

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.order_manager import OrderManager


class _MockExecutor(Executor):
    def __init__(self, fill_price=Decimal("100")):
        self.fill_price = fill_price
        self.order_count = 0

    def execute_order(self, request):
        self.order_count += 1
        return ExecutionResult(
            f"ORDER-{self.order_count}", OrderStatus.FILLED, request.quantity, self.fill_price
        )

    def cancel_all(self):
        return 0

    def close_order(self, order_id):
        return False


mock_guard = MagicMock()
executor = _MockExecutor(fill_price=Decimal("100"))
om = OrderManager(executor=executor, daily_loss_guard=mock_guard)

req_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
result1 = om.place_order(req_buy)
print(f"Buy result: {result1.order_id} {result1.status}")
print(f"Guard called after buy: {mock_guard.record_trade.called}")

executor.fill_price = Decimal("110")
req_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
result2 = om.place_order(req_sell)
print(f"Sell result: {result2.order_id} {result2.status}")
print(f"Guard called after sell: {mock_guard.record_trade.called}")
print(f"Guard call_count: {mock_guard.record_trade.call_count}")
if mock_guard.record_trade.called:
    print(f"Guard call_args: {mock_guard.record_trade.call_args}")
print(f"Pipeline position state: {om._risk_pipeline._position_state}")
