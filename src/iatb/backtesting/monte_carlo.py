"""
Monte Carlo permutation robustness testing.
"""

from dataclasses import dataclass
from decimal import Decimal
from random import Random

from iatb.core.exceptions import ConfigError

_SQRT_252 = Decimal("15.8745078664")


@dataclass(frozen=True)
class MonteCarloResult:
    base_sharpe: Decimal
    percentile_5_sharpe: Decimal
    robust: bool
    permutations: int


class MonteCarloAnalyzer:
    """Permutation-based robustness analyzer (default 10K simulations)."""

    def __init__(self, permutations: int = 10000, seed: int = 42) -> None:
        if permutations <= 0:
            msg = "permutations must be positive"
            raise ConfigError(msg)
        self._permutations = permutations
        self._rng = Random(seed)  # noqa: S311  # nosec B311

    def run(self, returns: list[Decimal]) -> MonteCarloResult:
        if len(returns) < 2:
            msg = "returns must contain at least two points"
            raise ConfigError(msg)
        base_sharpe = _sharpe_like(returns)
        sampled = [_sharpe_like(self._permute(returns)) for _ in range(self._permutations)]
        sampled.sort()
        percentile_5 = sampled[max(0, (len(sampled) * 5 // 100) - 1)]
        return MonteCarloResult(
            base_sharpe=base_sharpe,
            percentile_5_sharpe=percentile_5,
            robust=base_sharpe >= percentile_5,
            permutations=self._permutations,
        )

    def _permute(self, returns: list[Decimal]) -> list[Decimal]:
        shuffled = list(returns)
        self._rng.shuffle(shuffled)
        return shuffled


def _sharpe_like(returns: list[Decimal]) -> Decimal:
    mean_return = sum(returns, Decimal("0")) / Decimal(len(returns))
    abs_dev = [abs(value - mean_return) for value in returns]
    dispersion = sum(abs_dev, Decimal("0")) / Decimal(len(abs_dev))
    if dispersion == Decimal("0"):
        return Decimal("0")
    return (mean_return / dispersion) * _SQRT_252
