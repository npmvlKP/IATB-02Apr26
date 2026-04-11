import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, OrderRequest

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_order_request_and_execution_result_validation() -> None:
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"))
    result = ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("1"), Decimal("100"))
    assert request.symbol == "NIFTY"
    assert result.order_id == "OID-1"
    with pytest.raises(ConfigError, match="quantity must be positive"):
        OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("0"))
    with pytest.raises(ConfigError, match="cannot be empty"):
        ExecutionResult("", OrderStatus.FILLED, Decimal("1"), Decimal("100"))


def test_order_request_empty_symbol_raises_error() -> None:
    """Test that empty symbol raises ConfigError."""
    with pytest.raises(ConfigError, match="symbol cannot be empty"):
        OrderRequest(Exchange.NSE, "", OrderSide.BUY, Decimal("1"))


def test_order_request_whitespace_symbol_raises_error() -> None:
    """Test that whitespace-only symbol raises ConfigError."""
    with pytest.raises(ConfigError, match="symbol cannot be empty"):
        OrderRequest(Exchange.NSE, "   ", OrderSide.BUY, Decimal("1"))


def test_order_request_negative_price_raises_error() -> None:
    """Test that negative price raises ConfigError."""
    with pytest.raises(ConfigError, match="price must be positive when provided"):
        OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("-100"))


def test_order_request_zero_price_raises_error() -> None:
    """Test that zero price raises ConfigError."""
    with pytest.raises(ConfigError, match="price must be positive when provided"):
        OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("0"))


def test_execution_result_negative_filled_quantity_raises_error() -> None:
    """Test that negative filled_quantity raises ConfigError."""
    with pytest.raises(ConfigError, match="filled_quantity cannot be negative"):
        ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("-1"), Decimal("100"))


def test_execution_result_negative_average_price_raises_error() -> None:
    """Test that negative average_price raises ConfigError."""
    with pytest.raises(ConfigError, match="average_price cannot be negative"):
        ExecutionResult("OID-1", OrderStatus.FILLED, Decimal("1"), Decimal("-100"))


def test_order_request_with_valid_price() -> None:
    """Test that valid price is accepted."""
    request = OrderRequest(Exchange.NSE, "NIFTY", OrderSide.BUY, Decimal("1"), price=Decimal("100"))
    assert request.price == Decimal("100")


def test_execution_result_with_zero_filled_quantity() -> None:
    """Test that zero filled_quantity is accepted."""
    result = ExecutionResult("OID-1", OrderStatus.REJECTED, Decimal("0"), Decimal("0"))
    assert result.filled_quantity == Decimal("0")
