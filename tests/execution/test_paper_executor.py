from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.execution.base import OrderRequest
from iatb.execution.paper_executor import PaperExecutor


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
    assert executor.cancel_all() == 0
