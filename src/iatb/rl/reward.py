"""
Reward functions for RL training objectives.
"""

from decimal import Decimal

_SQRT_252 = Decimal("15.8745078664")


def pnl_reward(pnl: Decimal, costs: Decimal = Decimal("0")) -> Decimal:
    return pnl - costs


def sharpe_reward(returns: list[Decimal], costs: Decimal = Decimal("0")) -> Decimal:
    if not returns:
        return -costs
    mean_return = _mean(returns)
    dispersion = _mean([abs(value - mean_return) for value in returns])
    if dispersion == Decimal("0"):
        return -costs
    return (mean_return / dispersion) * _SQRT_252 - costs


def sortino_reward(returns: list[Decimal], costs: Decimal = Decimal("0")) -> Decimal:
    if not returns:
        return -costs
    mean_return = _mean(returns)
    downside = [abs(value) for value in returns if value < Decimal("0")]
    downside_risk = _mean(downside) if downside else Decimal("0")
    if downside_risk == Decimal("0"):
        return mean_return * _SQRT_252 - costs
    return (mean_return / downside_risk) * _SQRT_252 - costs


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))
