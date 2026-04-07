from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, OrderRequest


def test_order_request_and_execution_result_validation() -> None:
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("1"), Decimal("100"))
    assert request.symbol == "NIFTY"
    assert result.order_id == "OID-1"
    with pytest.raises(ConfigError, match="quantity must be positive"):
        OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("0"))
    with pytest.raises(ConfigError, match="cannot be empty"):
        ExecutionResult("", OrderStatus.FILLED, Decimal("1"), Decimal("100"))
