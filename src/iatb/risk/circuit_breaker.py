"""
Market-wide circuit breaker evaluation.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class CircuitBreakerState:
    level: int
    halt_required: bool
    reason: str


def evaluate_circuit_breaker(index_move_pct: Decimal) -> CircuitBreakerState:
    if index_move_pct < Decimal("0"):
        msg = "index_move_pct must be non-negative"
        raise ConfigError(msg)
    if index_move_pct >= Decimal("20"):
        return CircuitBreakerState(level=3, halt_required=True, reason="Level-3 halt (20%)")
    if index_move_pct >= Decimal("15"):
        return CircuitBreakerState(level=2, halt_required=True, reason="Level-2 halt (15%)")
    if index_move_pct >= Decimal("10"):
        return CircuitBreakerState(level=1, halt_required=True, reason="Level-1 halt (10%)")
    return CircuitBreakerState(level=0, halt_required=False, reason="No halt")
