"""
Tests for core enum definitions.
"""


import random

import numpy as np
import torch
from iatb.core.enums import (
    Exchange,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestExchange:
    """Test Exchange enum."""

    def test_exchange_values(self) -> None:
        """Test all exchange enum values."""
        assert Exchange.NSE == "NSE"
        assert Exchange.BSE == "BSE"
        assert Exchange.MCX == "MCX"
        assert Exchange.CDS == "CDS"
        assert Exchange.BINANCE == "BINANCE"
        assert Exchange.COINDCX == "COINDCX"

    def test_exchange_is_strenum(self) -> None:
        """Test that Exchange is a StrEnum."""
        assert isinstance(Exchange.NSE, str)
        assert Exchange.NSE.value == "NSE"


class TestMarketType:
    """Test MarketType enum."""

    def test_market_type_values(self) -> None:
        """Test all market type enum values."""
        assert MarketType.SPOT == "SPOT"
        assert MarketType.FUTURES == "FUTURES"
        assert MarketType.OPTIONS == "OPTIONS"
        assert MarketType.CURRENCY_FO == "CURRENCY_FO"

    def test_market_type_is_strenum(self) -> None:
        """Test that MarketType is a StrEnum."""
        assert isinstance(MarketType.SPOT, str)
        assert MarketType.SPOT.value == "SPOT"


class TestOrderSide:
    """Test OrderSide enum."""

    def test_order_side_values(self) -> None:
        """Test all order side enum values."""
        assert OrderSide.BUY == "BUY"
        assert OrderSide.SELL == "SELL"

    def test_order_side_is_strenum(self) -> None:
        """Test that OrderSide is a StrEnum."""
        assert isinstance(OrderSide.BUY, str)
        assert OrderSide.BUY.value == "BUY"


class TestOrderType:
    """Test OrderType enum."""

    def test_order_type_values(self) -> None:
        """Test all order type enum values."""
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.STOP_LOSS == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET == "STOP_LOSS_MARKET"

    def test_order_type_is_strenum(self) -> None:
        """Test that OrderType is a StrEnum."""
        assert isinstance(OrderType.MARKET, str)
        assert OrderType.MARKET.value == "MARKET"


class TestOrderStatus:
    """Test OrderStatus enum."""

    def test_order_status_values(self) -> None:
        """Test all order status enum values."""
        assert OrderStatus.PENDING == "PENDING"
        assert OrderStatus.OPEN == "OPEN"
        assert OrderStatus.PARTIALLY_FILLED == "PARTIALLY_FILLED"
        assert OrderStatus.FILLED == "FILLED"
        assert OrderStatus.CANCELLED == "CANCELLED"
        assert OrderStatus.REJECTED == "REJECTED"
        assert OrderStatus.EXPIRED == "EXPIRED"

    def test_order_status_is_strenum(self) -> None:
        """Test that OrderStatus is a StrEnum."""
        assert isinstance(OrderStatus.PENDING, str)
        assert OrderStatus.PENDING.value == "PENDING"
