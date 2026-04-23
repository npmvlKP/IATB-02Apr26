"""
Broker integration module for trading platform connections.

This module provides a unified interface for broker operations,
supporting multiple broker implementations through a common protocol.
"""

from iatb.broker.base import (
    BrokerInterface,
    Exchange,
    Margin,
    Order,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    TransactionType,
)
from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.broker.zerodha_broker import ZerodhaBroker

__all__ = [
    "BrokerInterface",
    "Exchange",
    "Margin",
    "Order",
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "TransactionType",
    "ZerodhaBroker",
    "ZerodhaTokenManager",
]
