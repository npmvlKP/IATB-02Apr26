"""
Sector-relative strength normalization.

Adjusts instrument strength score relative to its sector average
so outperformers rank higher even in weak absolute environments.
"""

from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.selection._util import clamp_01


def sector_relative_score(
    instrument_score: Decimal,
    sector_scores: list[Decimal],
) -> Decimal:
    """Compute instrument score minus sector mean, centered at 0.5."""
    if not sector_scores:
        msg = "sector_scores cannot be empty"
        raise ConfigError(msg)
    sector_mean = sum(sector_scores, Decimal("0")) / Decimal(len(sector_scores))
    relative = instrument_score - sector_mean + Decimal("0.5")
    return clamp_01(relative)


def apply_sector_adjustment(
    scores_by_symbol: dict[str, Decimal],
    sector_map: dict[str, str],
) -> dict[str, Decimal]:
    """Adjust all instrument scores by their sector average."""
    sector_groups: dict[str, list[Decimal]] = {}
    for symbol, score in scores_by_symbol.items():
        sector = sector_map.get(symbol, "UNKNOWN")
        sector_groups.setdefault(sector, []).append(score)
    result: dict[str, Decimal] = {}
    for symbol, score in scores_by_symbol.items():
        sector = sector_map.get(symbol, "UNKNOWN")
        peers = sector_groups.get(sector, [score])
        result[symbol] = sector_relative_score(score, peers)
    return result
