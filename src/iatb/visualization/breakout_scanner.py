"""
Breakout and breakdown ranking helpers for dashboard scanners.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class BreakoutCandidate:
    symbol: str
    breakout_probability: Decimal
    distance_to_breakout_pct: Decimal
    direction: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            msg = "symbol cannot be empty"
            raise ConfigError(msg)
        if self.breakout_probability < Decimal("0") or self.breakout_probability > Decimal("1"):
            msg = "breakout_probability must be between 0 and 1"
            raise ConfigError(msg)
        if self.distance_to_breakout_pct < Decimal("0"):
            msg = "distance_to_breakout_pct cannot be negative"
            raise ConfigError(msg)
        normalized = self.direction.strip().lower()
        if normalized not in {"breakout", "breakdown"}:
            msg = "direction must be either 'breakout' or 'breakdown'"
            raise ConfigError(msg)
        object.__setattr__(self, "direction", normalized)


def rank_breakout_candidates(
    candidates: list[BreakoutCandidate],
    top_n: int = 10,
    direction: str = "breakout",
) -> list[BreakoutCandidate]:
    if top_n <= 0:
        msg = "top_n must be positive"
        raise ConfigError(msg)
    normalized = direction.strip().lower()
    if normalized not in {"breakout", "breakdown"}:
        msg = "direction must be either 'breakout' or 'breakdown'"
        raise ConfigError(msg)
    filtered = [item for item in candidates if item.direction == normalized]
    ordered = sorted(
        filtered,
        key=lambda item: (item.breakout_probability, -item.distance_to_breakout_pct),
        reverse=True,
    )
    return ordered[:top_n]
