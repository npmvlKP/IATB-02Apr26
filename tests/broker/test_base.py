"""
Tests for broker base interface and data classes.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.broker import (
    Exchange,
    Margin,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    TransactionType,
)


class TestOrder:
    """Test Order dataclass."""

    def test_order_creation(self) -> None:
        """Test creating an order with all fields."""
        order = Order(
            order_id="ORD123",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=OrderStatus.PENDING,
            product_type=ProductType.INTRADAY,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            average_price=None,
        )
        assert order.order_id == "ORD123"
        assert order.symbol == "RELIANCE"
        assert order.exchange == Exchange.NSE
        assert order.transaction_type == TransactionType.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 10
        assert order.price is None
        assert order.trigger_price is None
        assert order.status == OrderStatus.PENDING
        assert order.product_type == ProductType.INTRADAY
        assert order.filled_quantity == 0
        assert order.average_price is None

    def test_order_with_limit_price(self) -> None:
        """Test creating a limit order."""
        order = Order(
            order_id="ORD456",
            symbol="INFY",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.SELL,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("1500.50"),
            trigger_price=None,
            status=OrderStatus.OPEN,
            product_type=ProductType.DELIVERY,
            timestamp=datetime.now(UTC),
            filled_quantity=50,
            average_price=Decimal("1500.00"),
        )
        assert order.price == Decimal("1500.50")
        assert order.average_price == Decimal("1500.00")
        assert order.filled_quantity == 50


class TestPosition:
    """Test Position dataclass."""

    def test_position_creation(self) -> None:
        """Test creating a position."""
        position = Position(
            symbol="TCS",
            exchange=Exchange.NSE,
            product_type=ProductType.INTRADAY,
            quantity=10,
            average_price=Decimal("3500.00"),
            last_price=Decimal("3520.00"),
            pnl=Decimal("200.00"),
            day_change=Decimal("200.00"),
        )
        assert position.symbol == "TCS"
        assert position.exchange == Exchange.NSE
        assert position.product_type == ProductType.INTRADAY
        assert position.quantity == 10
        assert position.average_price == Decimal("3500.00")
        assert position.last_price == Decimal("3520.00")
        assert position.pnl == Decimal("200.00")
        assert position.day_change == Decimal("200.00")


class TestMargin:
    """Test Margin dataclass."""

    def test_margin_creation(self) -> None:
        """Test creating margin details."""
        margin = Margin(
            available_cash=Decimal("100000.00"),
            used_margin=Decimal("20000.00"),
            available_margin=Decimal("80000.00"),
            opening_balance=Decimal("100000.00"),
        )
        assert margin.available_cash == Decimal("100000.00")
        assert margin.used_margin == Decimal("20000.00")
        assert margin.available_margin == Decimal("80000.00")
        assert margin.opening_balance == Decimal("100000.00")


class TestEnums:
    """Test enum values."""

    def test_exchange_enum(self) -> None:
        """Test Exchange enum values."""
        assert Exchange.NSE.value == "NSE"
        assert Exchange.BSE.value == "BSE"
        assert Exchange.NFO.value == "NFO"
        assert Exchange.BFO.value == "BFO"
        assert Exchange.MCX.value == "MCX"

    def test_order_type_enum(self) -> None:
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP_LOSS.value == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET.value == "STOP_LOSS_MARKET"

    def test_order_status_enum(self) -> None:
        """Test OrderStatus enum values."""
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.OPEN.value == "OPEN"
        assert OrderStatus.COMPLETE.value == "COMPLETE"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"

    def test_transaction_type_enum(self) -> None:
        """Test TransactionType enum values."""
        assert TransactionType.BUY.value == "BUY"
        assert TransactionType.SELL.value == "SELL"

    def test_product_type_enum(self) -> None:
        """Test ProductType enum values."""
        assert ProductType.INTRADAY.value == "MIS"
        assert ProductType.DELIVERY.value == "CNC"
        assert ProductType.NRML.value == "NRML"
        assert ProductType.BO.value == "BO"
        assert ProductType.CO.value == "CO"


class TestOrderImmutability:
    """Test that Order dataclass is immutable (frozen)."""

    def test_order_is_frozen(self) -> None:
        """Test that Order cannot be modified after creation."""
        order = Order(
            order_id="ORD123",
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            transaction_type=TransactionType.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            price=None,
            trigger_price=None,
            status=OrderStatus.PENDING,
            product_type=ProductType.INTRADAY,
            timestamp=datetime.now(UTC),
            filled_quantity=0,
            average_price=None,
        )
        with pytest.raises(FrozenInstanceError):
            order.quantity = 20  # type: ignore[misc]


class TestPositionImmutability:
    """Test that Position dataclass is immutable (frozen)."""

    def test_position_is_frozen(self) -> None:
        """Test that Position cannot be modified after creation."""
        position = Position(
            symbol="TCS",
            exchange=Exchange.NSE,
            product_type=ProductType.INTRADAY,
            quantity=10,
            average_price=Decimal("3500.00"),
            last_price=Decimal("3520.00"),
            pnl=Decimal("200.00"),
            day_change=Decimal("200.00"),
        )
        with pytest.raises(FrozenInstanceError):
            position.quantity = 20  # type: ignore[misc]


class TestMarginImmutability:
    """Test that Margin dataclass is immutable (frozen)."""

    def test_margin_is_frozen(self) -> None:
        """Test that Margin cannot be modified after creation."""
        margin = Margin(
            available_cash=Decimal("100000.00"),
            used_margin=Decimal("20000.00"),
            available_margin=Decimal("80000.00"),
            opening_balance=Decimal("100000.00"),
        )
        with pytest.raises(FrozenInstanceError):
            margin.available_cash = Decimal("150000.00")  # type: ignore[misc]
