"""
IATB Core Module

Provides fundamental types, events, and infrastructure for the
algorithmic trading system.
"""

from iatb.core.clock import Clock, ClockDriftDetector, TradingSessions
from iatb.core.config import Config
from iatb.core.engine import Engine
from iatb.core.enums import (
    Exchange,
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from iatb.core.event_bus import EventBus
from iatb.core.event_persistence import EventPersistence
from iatb.core.events import (
    MarketTickEvent,
    OrderUpdateEvent,
    PnLUpdateEvent,
    RegimeChangeEvent,
    ScanUpdateEvent,
    SignalEvent,
)
from iatb.core.exceptions import (
    ClockError,
    ConfigError,
    EngineError,
    EventBusError,
    ExchangeHaltError,
    ExecutionError,
    IATBError,
    ValidationError,
)
from iatb.core.exchange_calendar import ExchangeCalendar, SessionWindow
from iatb.core.health import HealthServer
from iatb.core.pipeline_checkpoint import PipelineCheckpoint
from iatb.core.pipeline_health import PipelineHealthMonitor
from iatb.core.scaling import ClusterManager
from iatb.core.secrets_rotation import SecretsRotationManager
from iatb.core.sse_broadcaster import SSEBroadcaster
from iatb.core.strategy_runner import StrategyRunner
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
    "PnLUpdateEvent",
    "RegimeChangeEvent",
    "ScanUpdateEvent",
    "SignalEvent",
    # Infrastructure
    "Config",
    "Clock",
    "ClockDriftDetector",
    "ClusterManager",
    "Engine",
    "EventBus",
    "EventPersistence",
    "ExchangeCalendar",
    "PipelineCheckpoint",
    "PipelineHealthMonitor",
    "SecretsRotationManager",
    "SessionWindow",
    "SSEBroadcaster",
    "StrategyRunner",
    "TradingSessions",
    # Exceptions
    "IATBError",
    "ValidationError",
    "ConfigError",
    "EventBusError",
    "ClockError",
    "EngineError",
    "ExecutionError",
    "ExchangeHaltError",
    # Deprecated
    "HealthServer",
]
