"""
Instrument model and provider protocol for exchange-provided metadata.

Provides typed instrument definitions with validation for F&O trading
across NSE, BSE, MCX, and crypto exchanges.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from iatb.core.enums import Exchange
from iatb.core.exceptions import ValidationError


class InstrumentType(StrEnum):
    """Classification of tradable instrument types."""

    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION_CE = "OPTION_CE"
    OPTION_PE = "OPTION_PE"
    INDEX = "INDEX"


_OPTION_TYPES: frozenset[InstrumentType] = frozenset(
    {InstrumentType.OPTION_CE, InstrumentType.OPTION_PE}
)

_DERIVATIVE_TYPES: frozenset[InstrumentType] = frozenset(
    {InstrumentType.FUTURE, InstrumentType.OPTION_CE, InstrumentType.OPTION_PE}
)

_KITE_TYPE_MAP: dict[str, InstrumentType] = {
    "EQ": InstrumentType.EQUITY,
    "FUT": InstrumentType.FUTURE,
    "CE": InstrumentType.OPTION_CE,
    "PE": InstrumentType.OPTION_PE,
}


def map_kite_instrument_type(raw_type: str) -> InstrumentType:
    """Map Kite API instrument_type string to InstrumentType enum."""
    normalized = raw_type.strip().upper()
    if normalized not in _KITE_TYPE_MAP:
        msg = f"Unknown Kite instrument_type: {raw_type!r}"
        raise ValidationError(msg)
    return _KITE_TYPE_MAP[normalized]


@dataclass(frozen=True)
class Instrument:
    """Exchange-provided instrument with validated metadata."""

    instrument_token: int
    exchange_token: int
    trading_symbol: str
    name: str
    exchange: Exchange
    segment: str
    instrument_type: InstrumentType
    lot_size: Decimal
    tick_size: Decimal
    strike: Decimal | None = None
    expiry: date | None = None

    def __post_init__(self) -> None:
        _validate_instrument(self)

    @property
    def is_option(self) -> bool:
        return self.instrument_type in _OPTION_TYPES

    @property
    def is_derivative(self) -> bool:
        return self.instrument_type in _DERIVATIVE_TYPES

    @property
    def underlying_name(self) -> str:
        """Extract underlying name from trading symbol."""
        return self.name.strip() if self.name.strip() else self.trading_symbol


def _validate_instrument(inst: Instrument) -> None:
    if not inst.trading_symbol.strip():
        msg = "trading_symbol cannot be empty"
        raise ValidationError(msg)
    if inst.lot_size <= Decimal("0"):
        msg = f"lot_size must be positive, got: {inst.lot_size}"
        raise ValidationError(msg)
    if inst.tick_size <= Decimal("0"):
        msg = f"tick_size must be positive, got: {inst.tick_size}"
        raise ValidationError(msg)
    if inst.instrument_type in _OPTION_TYPES and inst.strike is None:
        msg = f"strike is required for {inst.instrument_type.value}"
        raise ValidationError(msg)
    if inst.instrument_type in _DERIVATIVE_TYPES and inst.expiry is None:
        msg = f"expiry is required for {inst.instrument_type.value}"
        raise ValidationError(msg)
    if inst.strike is not None and inst.strike < Decimal("0"):
        msg = f"strike cannot be negative: {inst.strike}"
        raise ValidationError(msg)


@runtime_checkable
class InstrumentProvider(Protocol):
    """Protocol for broker-agnostic instrument data fetching."""

    async def fetch_instruments(self, exchange: Exchange) -> list[Instrument]:
        """Fetch all tradable instruments for the given exchange."""
        ...
