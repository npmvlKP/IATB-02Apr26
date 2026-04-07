"""
Adaptive trailing stop strategies with volatility and regime awareness.

Provides a protocol and multiple implementations for production-grade
trailing stop management that adapts to ATR, market regime, and time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime


@dataclass(frozen=True)
class PositionState:
    """Snapshot of an open position for trailing stop computation."""

    entry_price: Decimal
    current_price: Decimal
    highest_since_entry: Decimal
    lowest_since_entry: Decimal
    side: OrderSide
    current_atr: Decimal
    current_regime: MarketRegime
    bars_held: int

    def __post_init__(self) -> None:
        if self.entry_price <= Decimal("0"):
            msg = "entry_price must be positive"
            raise ConfigError(msg)
        if self.current_price <= Decimal("0"):
            msg = "current_price must be positive"
            raise ConfigError(msg)
        if self.current_atr <= Decimal("0"):
            msg = "current_atr must be positive"
            raise ConfigError(msg)
        if self.bars_held < 0:
            msg = "bars_held cannot be negative"
            raise ConfigError(msg)


@runtime_checkable
class TrailingStopStrategy(Protocol):
    """Protocol for trailing stop computation strategies."""

    def compute_stop(self, state: PositionState) -> Decimal:
        """Compute the trailing stop price for the current position state."""
        ...


class ATRTrailingStop:
    """ATR-scaled trailing stop with ratchet-only movement."""

    def __init__(self, atr_multiplier: Decimal = Decimal("3.0")) -> None:
        if atr_multiplier <= Decimal("0"):
            msg = "atr_multiplier must be positive"
            raise ConfigError(msg)
        self._multiplier = atr_multiplier
        self._previous_stop: Decimal | None = None

    def compute_stop(self, state: PositionState) -> Decimal:
        distance = state.current_atr * self._multiplier
        if state.side == OrderSide.BUY:
            candidate = state.highest_since_entry - distance
            candidate = max(Decimal("0"), candidate)
            if self._previous_stop is not None:
                candidate = max(self._previous_stop, candidate)
        else:
            candidate = state.lowest_since_entry + distance
            if self._previous_stop is not None:
                candidate = min(self._previous_stop, candidate)
        self._previous_stop = candidate
        return candidate

    def reset(self) -> None:
        """Reset ratchet state for a new position."""
        self._previous_stop = None


class RegimeAdaptiveTrailingStop:
    """Trailing stop with regime-dependent ATR multiplier."""

    _REGIME_MULTIPLIERS: dict[MarketRegime, Decimal] = {
        MarketRegime.BULL: Decimal("2.5"),
        MarketRegime.BEAR: Decimal("1.5"),
        MarketRegime.SIDEWAYS: Decimal("3.0"),
    }

    def __init__(self, base_multiplier: Decimal = Decimal("2.5")) -> None:
        if base_multiplier <= Decimal("0"):
            msg = "base_multiplier must be positive"
            raise ConfigError(msg)
        self._base = base_multiplier
        self._previous_stop: Decimal | None = None

    def compute_stop(self, state: PositionState) -> Decimal:
        regime_factor = self._REGIME_MULTIPLIERS.get(state.current_regime, self._base)
        distance = state.current_atr * regime_factor
        if state.side == OrderSide.BUY:
            candidate = max(Decimal("0"), state.highest_since_entry - distance)
            if self._previous_stop is not None:
                candidate = max(self._previous_stop, candidate)
        else:
            candidate = state.lowest_since_entry + distance
            if self._previous_stop is not None:
                candidate = min(self._previous_stop, candidate)
        self._previous_stop = candidate
        return candidate

    def reset(self) -> None:
        self._previous_stop = None


class ChandelierExit:
    """Classic Wilder chandelier exit based on ATR from extreme."""

    def __init__(self, atr_multiplier: Decimal = Decimal("3.0")) -> None:
        if atr_multiplier <= Decimal("0"):
            msg = "atr_multiplier must be positive"
            raise ConfigError(msg)
        self._multiplier = atr_multiplier

    def compute_stop(self, state: PositionState) -> Decimal:
        distance = state.current_atr * self._multiplier
        if state.side == OrderSide.BUY:
            return max(Decimal("0"), state.highest_since_entry - distance)
        return state.lowest_since_entry + distance


class TimeDecayTrailingStop:
    """Trailing stop that tightens exponentially as position ages."""

    def __init__(
        self,
        initial_multiplier: Decimal = Decimal("3.0"),
        decay_rate: Decimal = Decimal("0.02"),
        min_multiplier: Decimal = Decimal("1.0"),
    ) -> None:
        if initial_multiplier <= Decimal("0"):
            msg = "initial_multiplier must be positive"
            raise ConfigError(msg)
        if decay_rate <= Decimal("0"):
            msg = "decay_rate must be positive"
            raise ConfigError(msg)
        if min_multiplier <= Decimal("0") or min_multiplier > initial_multiplier:
            msg = "min_multiplier must be in (0, initial_multiplier]"
            raise ConfigError(msg)
        self._initial = initial_multiplier
        self._decay = decay_rate
        self._min = min_multiplier
        self._previous_stop: Decimal | None = None

    def compute_stop(self, state: PositionState) -> Decimal:
        # API boundary: math.exp requires float; result immediately converted to Decimal.
        decay_factor = Decimal(str(math.exp(-float(self._decay) * state.bars_held)))
        multiplier = max(self._min, self._initial * decay_factor)
        distance = state.current_atr * multiplier
        if state.side == OrderSide.BUY:
            candidate = max(Decimal("0"), state.highest_since_entry - distance)
            if self._previous_stop is not None:
                candidate = max(self._previous_stop, candidate)
        else:
            candidate = state.lowest_since_entry + distance
            if self._previous_stop is not None:
                candidate = min(self._previous_stop, candidate)
        self._previous_stop = candidate
        return candidate

    def reset(self) -> None:
        self._previous_stop = None


class FixedFractionTrailingStop:
    """Adapter wrapping the existing trailing_stop_price() for protocol conformance."""

    def __init__(self, trail_fraction: Decimal = Decimal("0.01")) -> None:
        if trail_fraction <= Decimal("0") or trail_fraction >= Decimal("1"):
            msg = "trail_fraction must be between 0 and 1"
            raise ConfigError(msg)
        self._fraction = trail_fraction
        self._previous_stop: Decimal | None = None

    def compute_stop(self, state: PositionState) -> Decimal:
        distance = state.current_price * self._fraction
        if state.side == OrderSide.BUY:
            candidate = state.current_price - distance
            if self._previous_stop is not None:
                candidate = max(self._previous_stop, candidate)
        else:
            candidate = state.current_price + distance
            if self._previous_stop is not None:
                candidate = min(self._previous_stop, candidate)
        self._previous_stop = candidate
        return candidate

    def reset(self) -> None:
        self._previous_stop = None
