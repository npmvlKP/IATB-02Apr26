"""
Pairwise return correlation from Decimal close-price sequences.
"""

from collections.abc import Sequence
from decimal import Decimal

from iatb.core.exceptions import ConfigError


def compute_pairwise_correlations(
    price_series: dict[str, Sequence[Decimal]],
) -> dict[tuple[str, str], Decimal]:
    """Compute correlation for every unique pair of instruments.

    Returns dict keyed by alphabetically-ordered (symbol_a, symbol_b) tuples.
    """
    symbols = sorted(price_series.keys())
    if len(symbols) < 2:
        return {}
    returns_map = {sym: _returns(price_series[sym]) for sym in symbols}
    result: dict[tuple[str, str], Decimal] = {}
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            sym_a, sym_b = symbols[i], symbols[j]
            corr = _pearson(returns_map[sym_a], returns_map[sym_b])
            result[(sym_a, sym_b)] = corr
    return result


def _returns(prices: Sequence[Decimal]) -> list[Decimal]:
    if len(prices) < 2:
        msg = "price series must have at least 2 points"
        raise ConfigError(msg)
    result: list[Decimal] = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1]
        if prev == Decimal("0"):
            result.append(Decimal("0"))
        else:
            result.append((prices[idx] - prev) / prev)
    return result


def _pearson(xs: list[Decimal], ys: list[Decimal]) -> Decimal:
    """Pearson correlation clamped to [-1, 1].

    Uses population variance (N denominator) intentionally:
    cov/N divided by sqrt(var_x/N * var_y/N) cancels N,
    producing the same result as the sample (N-1) formula.
    """
    n = min(len(xs), len(ys))
    if n < 2:
        return Decimal("0")
    xs_trimmed = xs[-n:]
    ys_trimmed = ys[-n:]
    mean_x = _mean(xs_trimmed)
    mean_y = _mean(ys_trimmed)
    cov = _mean([(x - mean_x) * (y - mean_y) for x, y in zip(xs_trimmed, ys_trimmed, strict=True)])
    var_x = _mean([(x - mean_x) ** 2 for x in xs_trimmed])
    var_y = _mean([(y - mean_y) ** 2 for y in ys_trimmed])
    if var_x == Decimal("0") or var_y == Decimal("0"):
        return Decimal("0")
    # sqrt at API boundary via Decimal.sqrt()
    denom = var_x.sqrt() * var_y.sqrt()
    if denom == Decimal("0"):
        return Decimal("0")
    raw = cov / denom
    return max(Decimal("-1"), min(Decimal("1"), raw))


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))
