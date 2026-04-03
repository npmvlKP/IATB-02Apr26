"""
Position sizing models for risk-aware order quantity selection.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class PositionSizingInput:
    equity: Decimal
    entry_price: Decimal
    stop_price: Decimal
    risk_fraction: Decimal
    realized_volatility: Decimal


def fixed_fractional_size(data: PositionSizingInput) -> Decimal:
    _validate_inputs(data)
    risk_amount = data.equity * data.risk_fraction
    stop_distance = abs(data.entry_price - data.stop_price)
    if stop_distance == Decimal("0"):
        msg = "stop distance cannot be zero"
        raise ConfigError(msg)
    quantity = risk_amount / stop_distance
    return max(Decimal("0"), quantity)


def kelly_fraction(
    win_rate: Decimal,
    win_loss_ratio: Decimal,
    max_fraction: Decimal = Decimal("0.5"),
) -> Decimal:
    if win_rate < Decimal("0") or win_rate > Decimal("1"):
        msg = "win_rate must be between 0 and 1"
        raise ConfigError(msg)
    if win_loss_ratio <= Decimal("0"):
        msg = "win_loss_ratio must be positive"
        raise ConfigError(msg)
    if max_fraction <= Decimal("0"):
        msg = "max_fraction must be positive"
        raise ConfigError(msg)
    loss_rate = Decimal("1") - win_rate
    raw_kelly = win_rate - (loss_rate / win_loss_ratio)
    bounded = min(max_fraction, max(Decimal("0"), raw_kelly))
    return bounded


def volatility_adjusted_size(
    equity: Decimal,
    target_risk_fraction: Decimal,
    realized_volatility: Decimal,
    base_volatility: Decimal = Decimal("0.02"),
) -> Decimal:
    if equity <= Decimal("0"):
        msg = "equity must be positive"
        raise ConfigError(msg)
    if target_risk_fraction <= Decimal("0"):
        msg = "target_risk_fraction must be positive"
        raise ConfigError(msg)
    if realized_volatility <= Decimal("0"):
        msg = "realized_volatility must be positive"
        raise ConfigError(msg)
    adjusted_fraction = target_risk_fraction * (base_volatility / realized_volatility)
    capped_fraction = min(Decimal("0.5"), max(Decimal("0.01"), adjusted_fraction))
    return equity * capped_fraction


def _validate_inputs(data: PositionSizingInput) -> None:
    if data.equity <= Decimal("0"):
        msg = "equity must be positive"
        raise ConfigError(msg)
    if data.entry_price <= Decimal("0") or data.stop_price <= Decimal("0"):
        msg = "entry_price and stop_price must be positive"
        raise ConfigError(msg)
    if data.risk_fraction <= Decimal("0") or data.risk_fraction > Decimal("0.5"):
        msg = "risk_fraction must be in (0, 0.5]"
        raise ConfigError(msg)
    if data.realized_volatility <= Decimal("0"):
        msg = "realized_volatility must be positive"
        raise ConfigError(msg)
