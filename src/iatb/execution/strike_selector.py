"""
Strike price selection strategies for options trading.

Provides a protocol and multiple implementations for automatic
strike selection based on ATM proximity, OTM distance, moneyness,
and liquidity filtering.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.data.instrument import Instrument, InstrumentType


@runtime_checkable
class StrikeSelector(Protocol):
    """Protocol for strike price selection from an option chain."""

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        """Select the optimal strike from the given option chain."""
        ...


class ATMSelector:
    """Select the strike nearest to the underlying price (at-the-money)."""

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        _validate_chain(chain, underlying_price)
        return min(
            chain,
            key=lambda inst: abs(_strike_of(inst) - underlying_price),
        )


class OTMByStrikesSelector:
    """Select the Nth OTM strike from ATM."""

    def __init__(self, n_strikes: int = 2) -> None:
        if n_strikes < 0:
            msg = "n_strikes cannot be negative"
            raise ConfigError(msg)
        self._n = n_strikes

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        _validate_chain(chain, underlying_price)
        if self._n == 0:
            return ATMSelector().select(chain, underlying_price, side)
        sorted_chain = sorted(chain, key=lambda inst: _strike_of(inst))
        atm_index = _atm_index(sorted_chain, underlying_price)
        if _is_call_chain(chain):
            target_index = min(atm_index + self._n, len(sorted_chain) - 1)
        else:
            target_index = max(atm_index - self._n, 0)
        return sorted_chain[target_index]


class DeltaSelector:
    """Select strike by target delta (requires Greeks — future phase)."""

    def __init__(self, target_delta: Decimal = Decimal("0.30")) -> None:
        self._target = target_delta

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        msg = (
            "DeltaSelector requires a Greeks provider which is not yet implemented. "
            "Use ATMSelector or OTMByStrikesSelector instead."
        )
        raise ConfigError(msg)


class MoneynessPctSelector:
    """Select strike at a percentage offset from underlying price."""

    def __init__(self, pct: Decimal = Decimal("0.05")) -> None:
        if pct <= Decimal("0") or pct >= Decimal("1"):
            msg = "pct must be between 0 and 1"
            raise ConfigError(msg)
        self._pct = pct

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        _validate_chain(chain, underlying_price)
        if _is_call_chain(chain):
            target_strike = underlying_price * (Decimal("1") + self._pct)
        else:
            target_strike = underlying_price * (Decimal("1") - self._pct)
        return min(
            chain,
            key=lambda inst: abs(_strike_of(inst) - target_strike),
        )


class LiquidityFilteredSelector:
    """Wraps another selector, pre-filtering chain by minimum lot volume."""

    def __init__(self, inner: StrikeSelector, min_lot_volume: int = 100) -> None:
        if min_lot_volume < 0:
            msg = "min_lot_volume cannot be negative"
            raise ConfigError(msg)
        self._inner = inner
        self._min_volume = min_lot_volume

    def select(
        self, chain: list[Instrument], underlying_price: Decimal, side: OrderSide
    ) -> Instrument:
        _validate_chain(chain, underlying_price)
        filtered = [inst for inst in chain if inst.lot_size >= Decimal(str(self._min_volume))]
        if not filtered:
            filtered = chain
        return self._inner.select(filtered, underlying_price, side)


def _validate_chain(chain: list[Instrument], underlying_price: Decimal) -> None:
    if not chain:
        msg = "Option chain is empty"
        raise ConfigError(msg)
    if underlying_price <= Decimal("0"):
        msg = "underlying_price must be positive"
        raise ConfigError(msg)


def _strike_of(inst: Instrument) -> Decimal:
    if inst.strike is None:
        msg = f"Instrument {inst.trading_symbol} has no strike price"
        raise ConfigError(msg)
    return inst.strike


def _atm_index(sorted_chain: list[Instrument], underlying_price: Decimal) -> int:
    best_index = 0
    best_distance = abs(_strike_of(sorted_chain[0]) - underlying_price)
    for i, inst in enumerate(sorted_chain):
        distance = abs(_strike_of(inst) - underlying_price)
        if distance < best_distance:
            best_distance = distance
            best_index = i
    return best_index


def _is_call_chain(chain: list[Instrument]) -> bool:
    return any(inst.instrument_type == InstrumentType.OPTION_CE for inst in chain)
