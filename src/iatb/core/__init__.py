"""
IATB Core Module

Provides fundamental types, events, and infrastructure for the
algorithmic trading system.
"""

from iatb.core.clock import Clock
from iatb.core.config import Config
from iatb.core.enums import (
    Exchange,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from iatb.core.event_bus import EventBus
from iatb.core.events import (
    MarketTickEvent,
    OrderUpdateEvent,
    RegimeChangeEvent,
    SignalEvent,
)
from iatb.core.exceptions import (
    ClockError,
    ConfigError,
    EventBusError,
    IATBError,
    ValidationError,
)
from iatb.core.exchange_calendar import ExchangeCalendar, SessionWindow
from iatb.core.types import Price, Quantity, Timestamp

__all__ = [
    # Types
    "Price",
    "Quantity",
    "Timestamp",
    # Enums
    "Exchange",
    "MarketType",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    # Events
    "MarketTickEvent",
    "OrderUpdateEvent",
    "RegimeChangeEvent",
    "SignalEvent",
    # Infrastructure
    "EventBus",
    "Clock",
    "ExchangeCalendar",
    "SessionWindow",
    "Config",
    # Exceptions
    "IATBError",
    "ValidationError",
    "ConfigError",
    "EventBusError",
    "ClockError",
]
