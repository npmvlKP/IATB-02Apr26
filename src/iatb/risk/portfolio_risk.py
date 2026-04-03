"""
Portfolio-level risk statistics.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    var_95: Decimal
    cvar_95: Decimal
    max_drawdown: Decimal
    drawdown_breached: bool


def compute_var(returns: list[Decimal], confidence: Decimal = Decimal("0.95")) -> Decimal:
    _validate_returns(returns, confidence)
    ordered = sorted(returns)
    index = int((Decimal("1") - confidence) * Decimal(len(ordered) - 1))
    return abs(ordered[index])


def compute_cvar(returns: list[Decimal], confidence: Decimal = Decimal("0.95")) -> Decimal:
    var = compute_var(returns, confidence)
    tail = [value for value in returns if value <= -var]
    if not tail:
        return var
    return abs(sum(tail, Decimal("0")) / Decimal(len(tail)))


def compute_max_drawdown(equity_curve: list[Decimal]) -> Decimal:
    if len(equity_curve) < 2:
        msg = "equity_curve must contain at least two points"
        raise ConfigError(msg)
    peak = equity_curve[0]
    max_dd = Decimal("0")
    for value in equity_curve:
        peak = max(peak, value)
        drawdown = (peak - value) / max(peak, Decimal("1"))
        max_dd = max(max_dd, drawdown)
    return max_dd


def build_risk_snapshot(
    returns: list[Decimal],
    equity_curve: list[Decimal],
    max_allowed_drawdown: Decimal = Decimal("0.1"),
) -> PortfolioRiskSnapshot:
    var_95 = compute_var(returns)
    cvar_95 = compute_cvar(returns)
    max_drawdown = compute_max_drawdown(equity_curve)
    return PortfolioRiskSnapshot(var_95, cvar_95, max_drawdown, max_drawdown > max_allowed_drawdown)


def _validate_returns(returns: list[Decimal], confidence: Decimal) -> None:
    if len(returns) < 2:
        msg = "returns must contain at least two points"
        raise ConfigError(msg)
    if confidence <= Decimal("0") or confidence >= Decimal("1"):
        msg = "confidence must be between 0 and 1"
        raise ConfigError(msg)
