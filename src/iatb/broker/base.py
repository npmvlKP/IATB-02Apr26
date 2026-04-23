"""
Broker interface abstraction for multi-broker support.

Defines the protocol that all broker implementations must follow,
enabling the trading system to work with multiple brokers through
a unified interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol


class OrderType(Enum):
    """Order execution types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderStatus(Enum):
    """Order status values."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    TRIGGER_PENDING = "TRIGGER_PENDING"
    VALIDATION_PENDING = "VALIDATION_PENDING"


class TransactionType(Enum):
    """Transaction direction."""

    BUY = "BUY"
    SELL = "SELL"


class ProductType(Enum):
    """Product types."""

    INTRADAY = "MIS"
    DELIVERY = "CNC"
    NRML = "NRML"  # Normal (F&O)
    BO = "BO"  # Bracket Order
    CO = "CO"  # Cover Order


class Exchange(Enum):
    """Exchange identifiers."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"


@dataclass(frozen=True)
class Order:
    """Order representation."""

    order_id: str
    symbol: str
    exchange: Exchange
    transaction_type: TransactionType
    order_type: OrderType
    quantity: int
    price: Decimal | None
    trigger_price: Decimal | None
    status: OrderStatus
    product_type: ProductType
    timestamp: datetime
    filled_quantity: int
    average_price: Decimal | None


@dataclass(frozen=True)
class Position:
    """Position representation."""

    symbol: str
    exchange: Exchange
    product_type: ProductType
    quantity: int
    average_price: Decimal
    last_price: Decimal
    pnl: Decimal
    day_change: Decimal


@dataclass(frozen=True)
class Margin:
    """Margin details."""

    available_cash: Decimal
    used_margin: Decimal
    available_margin: Decimal
    opening_balance: Decimal


class BrokerInterface(Protocol):
    """Protocol defining the broker interface.

    All broker implementations must conform to this interface to ensure
    consistent behavior across different broker backends.
    """

    async def place_order(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        transaction_type: TransactionType,
        order_type: OrderType,
        quantity: int,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
    ) -> Order:
        """Place a new order.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "INFY").
            exchange: Exchange where symbol is traded.
            transaction_type: BUY or SELL.
            order_type: Type of order (MARKET, LIMIT, etc.).
            quantity: Number of shares/contracts.
            price: Limit price (required for LIMIT orders).
            trigger_price: Trigger price (required for STOP_LOSS orders).
            product_type: Product type (INTRADAY, DELIVERY, etc.).

        Returns:
            Order object with order details.

        Raises:
            ValueError: If parameters are invalid.
            RuntimeError: If order placement fails.
        """
        ...

    async def cancel_order(self, *, order_id: str) -> Order:
        """Cancel an existing order.

        Args:
            order_id: Order ID to cancel.

        Returns:
            Updated order object with CANCELLED status.

        Raises:
            ValueError: If order_id is invalid.
            RuntimeError: If cancellation fails (e.g., order already executed).
        """
        ...

    async def get_positions(self) -> list[Position]:
        """Get current positions.

        Returns:
            List of current positions.

        Raises:
            RuntimeError: If fetching positions fails.
        """
        ...

    async def get_orders(self) -> list[Order]:
        """Get all orders.

        Returns:
            List of all orders.

        Raises:
            RuntimeError: If fetching orders fails.
        """
        ...

    async def get_margins(self) -> Margin:
        """Get margin details.

        Returns:
            Margin details object.

        Raises:
            RuntimeError: If fetching margins fails.
        """
        ...

    async def get_order_history(
        self, *, order_id: str, from_date: date | None = None, to_date: date | None = None
    ) -> list[Mapping[str, Any]]:
        """Get order history for a specific order.

        Args:
            order_id: Order ID to fetch history for.
            from_date: Optional start date for filtering.
            to_date: Optional end date for filtering.

        Returns:
            List of order history entries.

        Raises:
            ValueError: If order_id is invalid.
            RuntimeError: If fetching history fails.
        """
        ...

    async def get_holdings(self) -> list[Mapping[str, Any]]:
        """Get holdings for delivery-based positions.

        Returns:
            List of holdings.

        Raises:
            RuntimeError: If fetching holdings fails.
        """
        ...

    async def modify_order(
        self,
        *,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        trigger_price: Decimal | None = None,
        disclosed_quantity: int | None = None,
    ) -> Order:
        """Modify an existing order.

        Args:
            order_id: Order ID to modify.
            quantity: New quantity (optional).
            price: New price (optional).
            order_type: New order type (optional).
            trigger_price: New trigger price (optional).
            disclosed_quantity: New disclosed quantity (optional).

        Returns:
            Updated order object.

        Raises:
            ValueError: If parameters are invalid or order cannot be modified.
            RuntimeError: If modification fails.
        """
        ...

    async def get_quote(self, *, symbol: str, exchange: Exchange) -> Mapping[str, Any]:
        """Get current quote for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange where symbol is traded.

        Returns:
            Quote data as dictionary.

        Raises:
            ValueError: If symbol is invalid.
            RuntimeError: If fetching quote fails.
        """
        ...
