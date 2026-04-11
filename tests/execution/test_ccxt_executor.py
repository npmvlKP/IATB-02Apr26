import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.ccxt_executor import CCXTExecutor

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_ccxt_executor_live_gate_and_status_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = CCXTExecutor(
        create_order=lambda payload: {
            "id": "CX-1",
            "status": "closed",
            "filled": payload["amount"],
            "average": payload.get("price", "100"),
        },
        cancel_all_orders=lambda: 2,
    )
    request = OrderRequest(
        Exchange.BINANCE,
        "BTCUSDT",
        OrderSide.BUY,
        Decimal("1"),
        price=Decimal("100"),
        metadata={"algo_id": "ALG-101"},
    )
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("BROKER_OAUTH_2FA_VERIFIED", raising=False)
    with pytest.raises(ConfigError, match="LIVE_TRADING_ENABLED=true"):
        executor.execute_order(request)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    result = executor.execute_order(request)
    assert result.order_id == "CX-1"
    assert result.status == OrderStatus.FILLED
    assert executor.cancel_all() == 2


def test_ccxt_executor_rejects_missing_order_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    executor = CCXTExecutor(
        create_order=lambda payload: {"status": "open"}, cancel_all_orders=lambda: 0
    )
    request = OrderRequest(
        Exchange.BINANCE, "BTCUSDT", OrderSide.BUY, Decimal("1"), metadata={"algo_id": "ALG-101"}
    )
    with pytest.raises(ConfigError, match="missing id"):
        executor.execute_order(request)


def test_ccxt_executor_rejects_without_oauth_2fa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.delenv("BROKER_OAUTH_2FA_VERIFIED", raising=False)
    executor = CCXTExecutor(
        create_order=lambda payload: {"id": "CX-1", "status": "open"}, cancel_all_orders=lambda: 0
    )
    request = OrderRequest(
        Exchange.BINANCE, "BTCUSDT", OrderSide.BUY, Decimal("1"), metadata={"algo_id": "ALG-101"}
    )
    with pytest.raises(ConfigError, match="BROKER_OAUTH_2FA_VERIFIED=true"):
        executor.execute_order(request)


def test_ccxt_executor_rejects_missing_algo_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("BROKER_OAUTH_2FA_VERIFIED", "true")
    executor = CCXTExecutor(
        create_order=lambda payload: {"id": "CX-1", "status": "open"}, cancel_all_orders=lambda: 0
    )
    request = OrderRequest(Exchange.BINANCE, "BTCUSDT", OrderSide.BUY, Decimal("1"))
    with pytest.raises(ConfigError, match="algo_id metadata is required"):
        executor.execute_order(request)
