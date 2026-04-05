"""
Rank instruments by composite score with threshold and correlation filter.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError

_DEFAULT_MIN_SCORE = Decimal("0.20")
_DEFAULT_TOP_N = 5
_DEFAULT_CORRELATION_LIMIT = Decimal("0.80")


@dataclass(frozen=True)
class RankedInstrument:
    symbol: str
    exchange: Exchange
    composite_score: Decimal
    rank: int
    metadata: dict[str, str]


@dataclass(frozen=True)
class RankingConfig:
    min_score: Decimal = _DEFAULT_MIN_SCORE
    top_n: int = _DEFAULT_TOP_N
    correlation_limit: Decimal = _DEFAULT_CORRELATION_LIMIT

    def __post_init__(self) -> None:
        if self.min_score < Decimal("0") or self.min_score > Decimal("1"):
            msg = "min_score must be in [0, 1]"
            raise ConfigError(msg)
        if self.top_n <= 0:
            msg = "top_n must be positive"
            raise ConfigError(msg)
        if self.correlation_limit < Decimal("0") or self.correlation_limit > Decimal("1"):
            msg = "correlation_limit must be in [0, 1]"
            raise ConfigError(msg)


@dataclass(frozen=True)
class SelectionResult:
    selected: list[RankedInstrument]
    filtered_count: int
    total_candidates: int


def rank_and_select(
    candidates: list[tuple[str, Exchange, Decimal, dict[str, str]]],
    config: RankingConfig | None = None,
    correlations: dict[tuple[str, str], Decimal] | None = None,
) -> SelectionResult:
    """Rank candidates by score, apply threshold and top-N, filter correlated."""
    if not candidates:
        return SelectionResult(selected=[], filtered_count=0, total_candidates=0)
    cfg = config or RankingConfig()
    above_threshold = _apply_threshold(candidates, cfg.min_score)
    sorted_candidates = sorted(above_threshold, key=lambda c: c[2], reverse=True)
    top_n = sorted_candidates[: cfg.top_n]
    filtered = _correlation_filter(top_n, correlations, cfg.correlation_limit)
    ranked = _assign_ranks(filtered)
    return SelectionResult(
        selected=ranked,
        filtered_count=len(candidates) - len(ranked),
        total_candidates=len(candidates),
    )


def _apply_threshold(
    candidates: list[tuple[str, Exchange, Decimal, dict[str, str]]],
    min_score: Decimal,
) -> list[tuple[str, Exchange, Decimal, dict[str, str]]]:
    return [c for c in candidates if c[2] >= min_score]


def _correlation_filter(
    candidates: list[tuple[str, Exchange, Decimal, dict[str, str]]],
    correlations: dict[tuple[str, str], Decimal] | None,
    limit: Decimal,
) -> list[tuple[str, Exchange, Decimal, dict[str, str]]]:
    if not correlations or len(candidates) < 2:
        return candidates
    selected: list[tuple[str, Exchange, Decimal, dict[str, str]]] = []
    for candidate in candidates:
        if _is_too_correlated(candidate[0], selected, correlations, limit):
            continue
        selected.append(candidate)
    return selected


def _is_too_correlated(
    symbol: str,
    selected: list[tuple[str, Exchange, Decimal, dict[str, str]]],
    correlations: dict[tuple[str, str], Decimal],
    limit: Decimal,
) -> bool:
    for existing in selected:
        pair = _ordered_pair(symbol, existing[0])
        correlation = correlations.get(pair, Decimal("0"))
        if abs(correlation) > limit:
            return True
    return False


def _ordered_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _assign_ranks(
    candidates: list[tuple[str, Exchange, Decimal, dict[str, str]]],
) -> list[RankedInstrument]:
    return [
        RankedInstrument(
            symbol=c[0],
            exchange=c[1],
            composite_score=c[2],
            rank=idx + 1,
            metadata=c[3],
        )
        for idx, c in enumerate(candidates)
    ]
