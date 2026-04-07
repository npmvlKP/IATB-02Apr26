"""
Instrument type resolver with cascade fallback and index awareness.

Resolves an underlying symbol to the best available instrument type
(Options → Futures → Equity) based on strategy preference and exchange data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import InstrumentResolutionError
from iatb.data.instrument import Instrument, InstrumentType
from iatb.data.instrument_master import InstrumentMaster

logger = logging.getLogger(__name__)

_KNOWN_INDICES: frozenset[str] = frozenset(
    {
        "NIFTY",
        "BANKNIFTY",
        "FINNIFTY",
        "MIDCPNIFTY",
        "SENSEX",
        "BANKEX",
        "NIFTY BANK",
        "NIFTY 50",
    }
)

_OPTION_TYPES: frozenset[InstrumentType] = frozenset(
    {
        InstrumentType.OPTION_CE,
        InstrumentType.OPTION_PE,
    }
)


@dataclass(frozen=True)
class ResolvedInstrument:
    """Result of instrument resolution with audit trail."""

    instrument: Instrument
    underlying: str
    resolution_path: str


class InstrumentResolver:
    """Resolves underlyings to tradable instruments via preference cascade."""

    def __init__(self, instrument_master: InstrumentMaster) -> None:
        self._master = instrument_master

    def resolve(
        self,
        underlying: str,
        exchange: Exchange,
        preferred: list[InstrumentType],
        *,
        expiry_target_days: int = 30,
        underlying_price: Decimal | None = None,
        side: OrderSide = OrderSide.BUY,
    ) -> ResolvedInstrument:
        """Resolve underlying to best available instrument via cascade."""
        available = self._master.get_available_types(underlying, exchange)
        if not available:
            msg = f"No instruments found for {underlying} on {exchange.value}"
            raise InstrumentResolutionError(msg)
        effective_preferred = self._filter_for_indices(underlying, preferred)
        for pref_type in effective_preferred:
            if pref_type not in available:
                continue
            instrument = self._resolve_type(
                underlying,
                exchange,
                pref_type,
                expiry_target_days,
                underlying_price,
                side,
            )
            if instrument is not None:
                path = f"{pref_type.value}(preferred) -> resolved"
                logger.info("Resolved %s -> %s via %s", underlying, instrument.trading_symbol, path)
                return ResolvedInstrument(
                    instrument=instrument,
                    underlying=underlying,
                    resolution_path=path,
                )
        pref_vals = [p.value for p in effective_preferred]
        avail_vals = [a.value for a in available]
        msg = (
            f"No preferred type for {underlying} on {exchange.value}. "
            f"Preferred: {pref_vals}, Available: {avail_vals}"
        )
        raise InstrumentResolutionError(msg)

    def _resolve_type(
        self,
        underlying: str,
        exchange: Exchange,
        inst_type: InstrumentType,
        expiry_target_days: int,
        underlying_price: Decimal | None,
        side: OrderSide,
    ) -> Instrument | None:
        if inst_type == InstrumentType.EQUITY:
            return self._resolve_equity(underlying, exchange)
        if inst_type == InstrumentType.FUTURE:
            return self._resolve_future(underlying, exchange, expiry_target_days)
        if inst_type in _OPTION_TYPES:
            return self._resolve_option(
                underlying,
                exchange,
                inst_type,
                expiry_target_days,
                underlying_price,
                side,
            )
        return None

    def _resolve_equity(self, underlying: str, exchange: Exchange) -> Instrument | None:
        try:
            return self._master.get_instrument(underlying, exchange, InstrumentType.EQUITY)
        except Exception:
            return None

    def _resolve_future(
        self, underlying: str, exchange: Exchange, target_days: int
    ) -> Instrument | None:
        try:
            expiry = self._master.get_nearest_expiry(underlying, exchange, InstrumentType.FUTURE)
            min_expiry = datetime.now(UTC).date() + timedelta(days=max(0, target_days - 15))
            if expiry < min_expiry:
                return None
            return self._master.get_instrument(underlying, exchange, InstrumentType.FUTURE)
        except Exception:
            return None

    def _resolve_option(
        self,
        underlying: str,
        exchange: Exchange,
        inst_type: InstrumentType,
        target_days: int,
        underlying_price: Decimal | None,
        side: OrderSide,
    ) -> Instrument | None:
        try:
            expiry = self._master.get_nearest_expiry(underlying, exchange, inst_type)
            chain = self._master.get_option_chain(underlying, exchange, expiry)
            typed_chain = [c for c in chain if c.instrument_type == inst_type]
            if not typed_chain:
                return None
            if underlying_price is not None:
                return _select_atm(typed_chain, underlying_price)
            return typed_chain[len(typed_chain) // 2]
        except Exception:
            return None

    @staticmethod
    def _filter_for_indices(
        underlying: str, preferred: list[InstrumentType]
    ) -> list[InstrumentType]:
        if underlying.upper() in _KNOWN_INDICES:
            return [p for p in preferred if p != InstrumentType.EQUITY]
        return list(preferred)


def _select_atm(chain: list[Instrument], underlying_price: Decimal) -> Instrument:
    """Select ATM strike from a typed option chain."""
    return min(
        chain,
        key=lambda inst: abs((inst.strike or Decimal("0")) - underlying_price),
    )
