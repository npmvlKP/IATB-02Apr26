"""
Execution protocol and shared request/response types.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class OrderRequest:
    exchange: Exchange
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            msg = "symbol cannot be empty"
            raise ConfigError(msg)
        if self.quantity <= Decimal("0"):
            msg = "quantity must be positive"
            raise ConfigError(msg)
        if self.price is not None and self.price <= Decimal("0"):
            msg = "price must be positive when provided"
            raise ConfigError(msg)


@dataclass(frozen=True)
class ExecutionResult:
    order_id: str
    status: OrderStatus
    filled_quantity: Decimal
    average_price: Decimal
    message: str = ""

    def __post_init__(self) -> None:
        if not self.order_id.strip():
            msg = "order_id cannot be empty"
            raise ConfigError(msg)
        if self.filled_quantity < Decimal("0"):
            msg = "filled_quantity cannot be negative"
            raise ConfigError(msg)
        if self.average_price < Decimal("0"):
            msg = "average_price cannot be negative"
            raise ConfigError(msg)


@runtime_checkable
class Executor(Protocol):
    def execute_order(self, request: OrderRequest) -> ExecutionResult:
        ...

    def cancel_all(self) -> int:
        ...

    def close_order(self, order_id: str) -> bool:
        ...
