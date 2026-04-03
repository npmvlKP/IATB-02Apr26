"""
Execution transaction cost estimators.
"""

from decimal import Decimal

from iatb.backtesting.indian_costs import MarketSegment, calculate_indian_costs
from iatb.core.exceptions import ConfigError


def estimate_single_side_cost(notional: Decimal, segment: MarketSegment) -> Decimal:
    if notional <= Decimal("0"):
        msg = "notional must be positive"
        raise ConfigError(msg)
    return calculate_indian_costs(notional, segment).total


def estimate_round_trip_cost(notional: Decimal, segment: MarketSegment) -> Decimal:
    single_side = estimate_single_side_cost(notional, segment)
    return single_side * Decimal("2")
