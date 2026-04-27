"""
Market-wide circuit breaker evaluation with kill switch auto-wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.exceptions import ConfigError

if TYPE_CHECKING:
    from datetime import datetime

    from iatb.risk.kill_switch import KillSwitch

_LOGGER = logging.getLogger(__name__)


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


def evaluate_and_engage_kill_switch(
    index_move_pct: Decimal,
    kill_switch: KillSwitch,
    now_utc: datetime,
) -> CircuitBreakerState:
    """Evaluate circuit breaker and auto-engage kill switch on halt.

    When the circuit breaker triggers a halt, this automatically
    engages the kill switch to cancel all open orders and block
    new order submissions.

    Args:
        index_move_pct: Absolute percentage move of the index.
        kill_switch: KillSwitch instance to engage on halt.
        now_utc: Current UTC datetime.

    Returns:
        CircuitBreakerState with evaluation result.
    """
    state = evaluate_circuit_breaker(index_move_pct)
    if state.halt_required and not kill_switch.is_engaged:
        kill_switch.engage(
            f"circuit breaker: {state.reason}",
            now_utc,
        )
        _LOGGER.critical(
            "Circuit breaker triggered kill switch: %s",
            state.reason,
        )
    return state
