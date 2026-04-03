"""
Enumeration types for IATB.

Provides strongly-typed enums for exchange, market types,
order properties, and status.
"""

from enum import StrEnum


class Exchange(StrEnum):
    """Supported trading exchanges."""

    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    CDS = "CDS"
    BINANCE = "BINANCE"
    COINDCX = "COINDCX"


class MarketType(StrEnum):
    """Types of markets available for trading."""

    SPOT = "SPOT"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CURRENCY_FO = "CURRENCY_FO"


class OrderSide(StrEnum):
    """Side of an order: buy or sell."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Types of order execution."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderStatus(StrEnum):
    """Status of an order in its lifecycle."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
