"""
Instrument scanner for auto-selecting tradable Stocks/Options/Futures.

Uses jugaad-data + pandas-ta (proven blueprint components) to scan NSE/CDS/MCX
and rank top gainers/losers by % change with multi-factor filtering.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer


class InstrumentCategory(StrEnum):
    """Category of tradable instrument."""

    STOCK = "STOCK"
    OPTION = "OPTION"
    FUTURE = "FUTURE"


class SortDirection(StrEnum):
    """Sort direction for ranking."""

    GAINERS = "GAINERS"
    LOSERS = "LOSERS"


@dataclass(frozen=True)
class ScannerConfig:
    """Configuration for instrument scanner."""

    min_volume_ratio: Decimal = Decimal("2.0")
    very_strong_threshold: Decimal = Decimal("0.75")
    min_exit_probability: Decimal = Decimal("0.5")
    top_n: int = 10
    exchanges: tuple[Exchange, ...] = (Exchange.NSE, Exchange.CDS, Exchange.MCX)
    categories: tuple[InstrumentCategory, ...] = (
        InstrumentCategory.STOCK,
        InstrumentCategory.OPTION,
        InstrumentCategory.FUTURE,
    )

    def __post_init__(self) -> None:
        if self.min_volume_ratio < Decimal("0"):
            msg = "min_volume_ratio cannot be negative"
            raise ConfigError(msg)
        if self.very_strong_threshold <= Decimal("0") or self.very_strong_threshold > Decimal("1"):
            msg = "very_strong_threshold must be in (0, 1]"
            raise ConfigError(msg)
        if self.min_exit_probability < Decimal("0") or self.min_exit_probability > Decimal("1"):
            msg = "min_exit_probability must be in [0, 1]"
            raise ConfigError(msg)
        if self.top_n <= 0:
            msg = "top_n must be positive"
            raise ConfigError(msg)
        if not self.exchanges:
            msg = "exchanges cannot be empty"
            raise ConfigError(msg)
        if not self.categories:
            msg = "categories cannot be empty"
            raise ConfigError(msg)


@dataclass(frozen=True)
class MarketData:
    """Market data for a single instrument."""

    symbol: str
    exchange: Exchange
    category: InstrumentCategory
    close_price: Decimal
    prev_close_price: Decimal
    volume: Decimal
    avg_volume: Decimal
    timestamp_utc: datetime
    high_price: Decimal
    low_price: Decimal
    adx: Decimal
    atr_pct: Decimal
    breadth_ratio: Decimal

    @property
    def pct_change(self) -> Decimal:
        """Calculate percentage change from previous close."""
        if self.prev_close_price == Decimal("0"):
            return Decimal("0")
        return ((self.close_price - self.prev_close_price) / self.prev_close_price) * Decimal("100")

    @property
    def volume_ratio(self) -> Decimal:
        """Calculate volume ratio vs average."""
        if self.avg_volume == Decimal("0"):
            return Decimal("0")
        return self.volume / self.avg_volume


@dataclass(frozen=True)
class ScannerCandidate:
    """A candidate instrument that passed all scanner filters."""

    symbol: str
    exchange: Exchange
    category: InstrumentCategory
    pct_change: Decimal
    composite_score: Decimal
    sentiment_score: Decimal
    volume_ratio: Decimal
    exit_probability: Decimal
    is_tradable: bool
    regime: MarketRegime
    rank: int
    timestamp_utc: datetime
    metadata: dict[str, str]


@dataclass(frozen=True)
class ScannerResult:
    """Result of a scanner run."""

    gainers: list[ScannerCandidate]
    losers: list[ScannerCandidate]
    total_scanned: int
    filtered_count: int
    scan_timestamp_utc: datetime


@dataclass(frozen=True)
class _CandidateScores:
    """Internal scoring container for a candidate."""

    market_data: MarketData
    sentiment_score: Decimal
    is_very_strong: bool
    strength_score: Decimal
    is_strength_tradable: bool
    exit_probability: Decimal


class InstrumentScanner:
    """
    Multi-factor instrument scanner using jugaad-data + pandas-ta.

    Filters instruments by:
    - VERY_STRONG sentiment (|score| >= 0.75)
    - strength_scorer.is_tradable() == True
    - volume_ratio >= 2.0
    - RL positive exit probability

    Emits only if ALL factors pass.
    """

    def __init__(
        self,
        config: ScannerConfig | None = None,
        strength_scorer: StrengthScorer | None = None,
        sentiment_analyzer: Callable[[str], tuple[Decimal, bool]] | None = None,
        rl_predictor: Callable[[list[Decimal]], Decimal] | None = None,
        data_provider: Callable[[Exchange, InstrumentCategory], list[MarketData]] | None = None,
    ) -> None:
        self._config = config or ScannerConfig()
        self._strength_scorer = strength_scorer or StrengthScorer()
        self._sentiment_analyzer = sentiment_analyzer
        self._rl_predictor = rl_predictor
        self._data_provider = data_provider

    def scan(
        self,
        direction: SortDirection = SortDirection.GAINERS,
        custom_data: list[MarketData] | None = None,
    ) -> ScannerResult:
        """
        Scan instruments and return ranked candidates.

        Args:
            direction: Sort by gainers or losers
            custom_data: Optional pre-fetched market data (for testing)

        Returns:
            ScannerResult with ranked gainers/losers
        """
        scan_timestamp = datetime.now(UTC)
        all_candidates = custom_data or self._fetch_all_market_data()
        scored = self._score_candidates(all_candidates)
        filtered = self._apply_filters(scored)
        gainers, losers = self._rank_and_split(filtered)
        return ScannerResult(
            gainers=gainers[: self._config.top_n],
            losers=losers[: self._config.top_n],
            total_scanned=len(all_candidates),
            filtered_count=len(all_candidates) - len(filtered),
            scan_timestamp_utc=scan_timestamp,
        )

    def _fetch_all_market_data(self) -> list[MarketData]:
        """Fetch market data for all configured exchanges and categories."""
        if self._data_provider is None:
            return []
        all_data: list[MarketData] = []
        for exchange in self._config.exchanges:
            for category in self._config.categories:
                data = self._data_provider(exchange, category)
                all_data.extend(data)
        return all_data

    def _score_candidates(self, candidates: list[MarketData]) -> list[_CandidateScores]:
        """Score each candidate with sentiment, strength, and RL."""
        scored: list[_CandidateScores] = []
        for data in candidates:
            sentiment_score, is_very_strong = self._get_sentiment(data)
            strength_score, is_tradable = self._get_strength(data)
            exit_prob = self._get_exit_probability(data)
            scored.append(
                _CandidateScores(
                    market_data=data,
                    sentiment_score=sentiment_score,
                    is_very_strong=is_very_strong,
                    strength_score=strength_score,
                    is_strength_tradable=is_tradable,
                    exit_probability=exit_prob,
                )
            )
        return scored

    def _apply_filters(self, scored: list[_CandidateScores]) -> list[_CandidateScores]:
        """Apply all filters: sentiment, strength, volume, RL."""
        filtered: list[_CandidateScores] = []
        for candidate in scored:
            if not candidate.is_very_strong:
                continue
            if not candidate.is_strength_tradable:
                continue
            if candidate.market_data.volume_ratio < self._config.min_volume_ratio:
                continue
            if candidate.exit_probability < self._config.min_exit_probability:
                continue
            filtered.append(candidate)
        return filtered

    def _rank_and_split(
        self, filtered: list[_CandidateScores]
    ) -> tuple[list[ScannerCandidate], list[ScannerCandidate]]:
        """Rank by % change and split into gainers/losers."""
        gainers_data = [c for c in filtered if c.market_data.pct_change > Decimal("0")]
        losers_data = [c for c in filtered if c.market_data.pct_change < Decimal("0")]
        gainers_sorted = sorted(gainers_data, key=lambda c: c.market_data.pct_change, reverse=True)
        losers_sorted = sorted(losers_data, key=lambda c: c.market_data.pct_change)
        gainers = self._to_scanner_candidates(gainers_sorted)
        losers = self._to_scanner_candidates(losers_sorted)
        return gainers, losers

    def _to_scanner_candidates(self, scored: list[_CandidateScores]) -> list[ScannerCandidate]:
        """Convert scored candidates to ScannerCandidate with ranks."""
        candidates: list[ScannerCandidate] = []
        for idx, s in enumerate(scored):
            composite = self._compute_composite_score(s)
            candidates.append(
                ScannerCandidate(
                    symbol=s.market_data.symbol,
                    exchange=s.market_data.exchange,
                    category=s.market_data.category,
                    pct_change=s.market_data.pct_change,
                    composite_score=composite,
                    sentiment_score=s.sentiment_score,
                    volume_ratio=s.market_data.volume_ratio,
                    exit_probability=s.exit_probability,
                    is_tradable=s.is_strength_tradable,
                    regime=MarketRegime.SIDEWAYS,  # Default; can be enhanced
                    rank=idx + 1,
                    timestamp_utc=s.market_data.timestamp_utc,
                    metadata={
                        "adx": str(s.market_data.adx),
                        "atr_pct": str(s.market_data.atr_pct),
                        "strength_score": str(s.strength_score),
                    },
                )
            )
        return candidates

    def _get_sentiment(self, data: MarketData) -> tuple[Decimal, bool]:
        """Get sentiment score and VERY_STRONG flag."""
        if self._sentiment_analyzer is None:
            return Decimal("0"), False
        score, is_strong = self._sentiment_analyzer(data.symbol)
        return score, is_strong

    def _get_strength(self, data: MarketData) -> tuple[Decimal, bool]:
        """Get strength score and tradability flag."""
        inputs = StrengthInputs(
            breadth_ratio=data.breadth_ratio,
            regime=MarketRegime.SIDEWAYS,
            adx=data.adx,
            volume_ratio=data.volume_ratio,
            volatility_atr_pct=data.atr_pct,
        )
        try:
            score = self._strength_scorer.score(data.exchange, inputs)
            is_tradable = self._strength_scorer.is_tradable(data.exchange, inputs)
            return score, is_tradable
        except ConfigError:
            return Decimal("0"), False

    def _get_exit_probability(self, data: MarketData) -> Decimal:
        """Get RL-based exit probability."""
        if self._rl_predictor is None:
            return Decimal("0")
        observation = self._build_observation(data)
        return self._rl_predictor(observation)

    def _build_observation(self, data: MarketData) -> list[Decimal]:
        """Build observation vector for RL predictor."""
        return [
            data.pct_change / Decimal("100"),
            data.volume_ratio,
            data.adx / Decimal("100"),
            data.atr_pct,
            data.breadth_ratio,
        ]

    def _compute_composite_score(self, scored: _CandidateScores) -> Decimal:
        """Compute weighted composite score from all factors."""
        weights = {
            "sentiment": Decimal("0.30"),
            "strength": Decimal("0.30"),
            "volume": Decimal("0.20"),
            "rl": Decimal("0.20"),
        }
        volume_score = min(Decimal("1"), scored.market_data.volume_ratio / Decimal("5"))
        composite = (
            abs(scored.sentiment_score) * weights["sentiment"]
            + scored.strength_score * weights["strength"]
            + volume_score * weights["volume"]
            + scored.exit_probability * weights["rl"]
        )
        return min(Decimal("1"), max(Decimal("0"), composite))


def create_mock_data_provider(
    data: Sequence[MarketData],
) -> Callable[[Exchange, InstrumentCategory], list[MarketData]]:
    """Create a mock data provider for testing."""

    def provider(exchange: Exchange, category: InstrumentCategory) -> list[MarketData]:
        return [d for d in data if d.exchange == exchange and d.category == category]

    return provider


def create_mock_sentiment_analyzer(
    scores: dict[str, tuple[Decimal, bool]],
) -> Callable[[str], tuple[Decimal, bool]]:
    """Create a mock sentiment analyzer for testing."""

    def analyzer(symbol: str) -> tuple[Decimal, bool]:
        return scores.get(symbol, (Decimal("0"), False))

    return analyzer


def create_mock_rl_predictor(
    probability: Decimal = Decimal("0.6"),
) -> Callable[[list[Decimal]], Decimal]:
    """Create a mock RL predictor for testing."""

    def predictor(_observation: list[Decimal]) -> Decimal:
        return probability

    return predictor
