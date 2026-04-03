from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.openalgo_executor import OpenAlgoExecutor


def test_openalgo_executor_live_gate_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))
    executor = OpenAlgoExecutor(
        place_order=lambda payload: {
            "order_id": "OA-1",
            "status": "FILLED",
            "filled_quantity": payload["quantity"],
            "average_price": payload["price"],
        },
        cancel_all_orders=lambda: 3,
    )
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    with pytest.raises(ConfigError, match="LIVE_TRADING_ENABLED=true"):
        executor.execute_order(request)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    result = executor.execute_order(request)
    assert result.order_id == "OA-1"
    assert result.status == OrderStatus.FILLED
    assert executor.cancel_all() == 3


def test_openalgo_executor_rejects_missing_order_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    executor = OpenAlgoExecutor(
        place_order=lambda payload: {"status": "FILLED"}, cancel_all_orders=lambda: 0
    )
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    with pytest.raises(ConfigError, match="missing order_id"):
        executor.execute_order(request)
