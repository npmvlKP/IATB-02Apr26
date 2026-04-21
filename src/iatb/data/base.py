"""
Normalized contracts for market data providers.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from iatb.core.enums import Exchange
from iatb.core.types import (
    Price,
    Quantity,
    Timestamp,
    create_price,
    create_quantity,
    create_timestamp,
)


def _utc_now_timestamp() -> Timestamp:
    """Create a strict UTC timestamp for data-model defaults."""
    return create_timestamp(datetime.now(UTC))


@dataclass(frozen=True)
class OHLCVBar:
    """Normalized OHLCV bar with Decimal-only financial fields."""

    event_id: UUID = field(default_factory=uuid4)
    timestamp: Timestamp = field(default_factory=_utc_now_timestamp)
    exchange: Exchange = Exchange.NSE
    symbol: str = "UNKNOWN"
    timeframe: str = "1d"
    open: Price = field(default_factory=lambda: create_price("0"))
    high: Price = field(default_factory=lambda: create_price("0"))
    low: Price = field(default_factory=lambda: create_price("0"))
    close: Price = field(default_factory=lambda: create_price("0"))
    volume: Quantity = field(default_factory=lambda: create_quantity("0"))
    source: str = "unknown"

    def __post_init__(self) -> None:
        """Enforce strict UTC timestamps at model construction."""
        object.__setattr__(self, "timestamp", create_timestamp(self.timestamp))


@dataclass(frozen=True)
class TickerSnapshot:
    """Normalized top-of-book ticker snapshot."""

    event_id: UUID = field(default_factory=uuid4)
    timestamp: Timestamp = field(default_factory=_utc_now_timestamp)
    exchange: Exchange = Exchange.NSE
    symbol: str = "UNKNOWN"
    bid: Price = field(default_factory=lambda: create_price("0"))
    ask: Price = field(default_factory=lambda: create_price("0"))
    last: Price = field(default_factory=lambda: create_price("0"))
    volume_24h: Quantity = field(default_factory=lambda: create_quantity("0"))
    source: str = "unknown"

    def __post_init__(self) -> None:
        """Enforce strict UTC timestamps at model construction."""
        object.__setattr__(self, "timestamp", create_timestamp(self.timestamp))


@runtime_checkable
class DataProvider(Protocol):
    """Contract for any market data provider implementation."""

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch normalized OHLCV bars for a symbol."""
        ...

    async def get_ticker(
        self,
        *,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        """Fetch a normalized ticker snapshot for a symbol."""
        ...

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        """Fetch normalized OHLCV bars for multiple symbols.

        This is an optional method for providers that support batch requests.
        If not implemented, the scanner will fall back to parallel individual requests.
        """
        ...
