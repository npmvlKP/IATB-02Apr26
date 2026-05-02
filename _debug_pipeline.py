from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.risk.risk_pipeline import RiskPipeline


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
mock_state = MagicMock()
mock_guard.state = mock_state
mock_guard.record_trade.return_value = mock_state

executor = _MockExecutor(fill_price=Decimal("100"))

pipeline = RiskPipeline(
    kill_switch=None,
    order_throttle=None,
    pre_trade_config=None,
    paper_executor=executor,
    daily_loss_guard=mock_guard,
    trade_audit_logger=None,
)

# Step 1: Buy NIFTY at 100
req_buy = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("10"))
result1 = pipeline.process_order(req_buy, datetime.now(UTC))
print(f"Buy result: allowed={result1.allowed}")
print(f"Guard called after buy: {mock_guard.record_trade.called}")
print(f"Position state after buy: {pipeline._position_state}")

# Step 2: Sell NIFTY at 110
executor.fill_price = Decimal("110")
req_sell = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.SELL, Decimal("10"))
result2 = pipeline.process_order(req_sell, datetime.now(UTC))
print(f"Sell result: allowed={result2.allowed}")
print(f"Guard called after sell: {mock_guard.record_trade.called}")
print(f"Guard call_count: {mock_guard.record_trade.call_count}")
if mock_guard.record_trade.called:
    print(f"Guard call_args: {mock_guard.record_trade.call_args}")
print(f"Position state after sell: {pipeline._position_state}")
