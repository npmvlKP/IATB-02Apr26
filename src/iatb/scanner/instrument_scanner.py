"""
Instrument scanner for auto-selecting tradable Stocks/Options/Futures.

Uses DataProvider abstraction + indicator module to scan NSE/CDS/MCX
and rank top gainers/losers by % change with multi-factor filtering.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_timestamp
from iatb.data.base import DataProvider
from iatb.data.market_data_cache import MarketDataCache
from iatb.market_strength.indicators import IndicatorSnapshot, PandasTaIndicators
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer

_LOGGER = logging.getLogger(__name__)


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
    lookback_days: int = 30

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
    data_source: str = "unknown"

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
    close_price: Decimal
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


def _to_decimal(value: object, field_name: str) -> Decimal:
    """Convert value to Decimal with validation."""
    if value is None:
        msg = f"{field_name} cannot be None"
        raise ConfigError(msg)
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        msg = f"{field_name} is not decimal-compatible: {value!r}"
        raise ConfigError(msg) from exc
    if not decimal_value.is_finite():
        msg = f"{field_name} must be finite"
        raise ConfigError(msg)
    return decimal_value


def _last_decimal(values: object, field_name: str) -> Decimal:
    """Extract last value from sequence and convert to Decimal."""
    if isinstance(values, Sequence) and not isinstance(values, str):
        if not values:
            msg = f"{field_name} returned empty sequence"
            raise ConfigError(msg)
        return _to_decimal(values[-1], field_name)
    msg = f"{field_name} returned unsupported output type: {type(values).__name__}"
    raise ConfigError(msg)


class InstrumentScanner:
    """
    Multi-factor instrument scanner using DataProvider abstraction.

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
        data_provider: DataProvider | None = None,
        strength_scorer: StrengthScorer | None = None,
        sentiment_analyzer: Callable[[str], tuple[Decimal, bool]] | None = None,
        rl_predictor: Callable[[list[Decimal]], Decimal] | None = None,
        symbols: Sequence[str] | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._config = config or ScannerConfig()
        self._data_provider = data_provider

        self._strength_scorer = strength_scorer or StrengthScorer()
        self._sentiment_analyzer = sentiment_analyzer
        self._rl_predictor = rl_predictor
        self._symbols = symbols or []
        self._cache = MarketDataCache(default_ttl_seconds=cache_ttl_seconds)
        self._indicators: PandasTaIndicators | None = None

    def scan(
        self,
        direction: SortDirection = SortDirection.GAINERS,
        custom_data: Iterable[MarketData] | None = None,
    ) -> ScannerResult:
        """
        Scan instruments using DataProvider abstraction.

        Args:
            direction: Sort by gainers or losers
            custom_data: Optional custom market data for testing (bypasses provider fetch)

        Returns:
            ScannerResult with ranked gainers/losers

        Raises:
            ConfigError: If DataProvider is not configured and custom_data not provided.
        """
        scan_timestamp = datetime.now(UTC)
        if custom_data is not None:
            all_candidates = list(custom_data)
        else:
            if self._data_provider is None:
                msg = (
                    "DataProvider not configured; provide custom_data or "
                    "initialize with data_provider"
                )
                raise ConfigError(msg)
            all_candidates = self._fetch_market_data()
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

    def _fetch_market_data(self) -> list[MarketData]:
        """Fetch market data using parallel async fetching with cache."""
        if not self._symbols:
            return []

        # Run parallel fetch using asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(self._fetch_symbols_parallel())
        finally:
            loop.close()

        return [r for r in results if r is not None]

    async def _fetch_symbols_parallel(self) -> list[MarketData | None]:
        """
        Fetch all symbols in parallel using asyncio.gather().

        Note: While batch OHLCV APIs would be ideal, this approach achieves
        similar performance benefits by fetching all symbols concurrently.
        """
        tasks = [self._fetch_single_symbol_async(symbol) for symbol in self._symbols]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _fetch_single_symbol_async(self, symbol: str) -> MarketData | None:
        """Async wrapper for fetching single symbol with cache check."""
        try:
            # Check cache first
            cache_key = f"{symbol}_{datetime.now(UTC).date()}"
            cached_data = cast(MarketData | None, self._cache.get(symbol, cache_key, cache_key))
            if cached_data is not None:
                return cached_data

            # Cache miss - fetch fresh data
            market_data = await self._fetch_single_symbol(symbol)

            if market_data is not None:
                self._cache.put(symbol, cache_key, cache_key, market_data)

            return market_data
        except Exception as exc:  # nosec - B112: scanner continues on individual failures  # noqa: S112
            _LOGGER.warning("Failed to fetch symbol %s: %s", symbol, exc)
            return None

    async def _fetch_single_symbol(self, symbol: str) -> MarketData | None:
        """Fetch and process data for a single symbol using DataProvider."""
        if self._data_provider is None:
            msg = "DataProvider not configured"
            raise ConfigError(msg)

        # Determine exchange from symbol or config
        exchange = self._determine_exchange(symbol)
        category = self._determine_category(symbol)

        # Fetch OHLCV data
        since_timestamp = create_timestamp(
            datetime.now(UTC) - timedelta(days=self._config.lookback_days)
        )
        bars = await self._data_provider.get_ohlcv(
            symbol=symbol,
            exchange=exchange,
            timeframe="1d",
            since=since_timestamp,
            limit=self._config.lookback_days,
        )

        if not bars:
            return None

        # Extract price/volume data
        closes: list[Decimal] = []
        highs: list[Decimal] = []
        lows: list[Decimal] = []
        volumes: list[Decimal] = []
        timestamps: list[datetime] = []

        for bar in bars:
            closes.append(Decimal(str(bar.close)))
            highs.append(Decimal(str(bar.high)))
            lows.append(Decimal(str(bar.low)))
            volumes.append(Decimal(str(bar.volume)))
            timestamps.append(bar.timestamp)

        if len(closes) < 2:
            return None

        # Calculate indicators using indicator module
        indicators = self._calculate_indicators(closes, highs, lows)

        # Get latest and previous data
        latest_close = closes[-1]
        prev_close = closes[-2]
        latest_high = highs[-1]
        latest_low = lows[-1]
        latest_volume = volumes[-1]
        latest_timestamp = timestamps[-1]

        # Calculate average volume
        avg_volume = sum(volumes) / Decimal(str(len(volumes)))

        # Calculate breadth ratio from price action (simplified)
        breadth_ratio = self._calculate_breadth_ratio(closes, volumes)

        # Calculate ATR percentage
        atr_pct = indicators.atr / latest_close if latest_close > Decimal("0") else Decimal("0")

        return MarketData(
            symbol=symbol,
            exchange=exchange,
            category=category,
            close_price=latest_close,
            prev_close_price=prev_close,
            volume=latest_volume,
            avg_volume=avg_volume,
            timestamp_utc=latest_timestamp,
            high_price=latest_high,
            low_price=latest_low,
            adx=indicators.adx,
            atr_pct=atr_pct,
            breadth_ratio=breadth_ratio,
            data_source=bars[0].source if bars else "unknown",
        )

    def _calculate_indicators(
        self, closes: list[Decimal], highs: list[Decimal], lows: list[Decimal]
    ) -> IndicatorSnapshot:
        """Calculate technical indicators using indicator module."""
        if len(closes) < 14:
            return self._default_indicators()

        try:
            if self._indicators is None:
                self._indicators = PandasTaIndicators()
            return self._indicators.snapshot(close=closes, high=highs, low=lows)
        except Exception as exc:  # nosec - B112: fallback to defaults on calculation error  # noqa: S112
            _LOGGER.debug("Indicator calculation failed, using defaults: %s", exc)
            return self._default_indicators()

    def _calculate_breadth_ratio(self, closes: list[Decimal], volumes: list[Decimal]) -> Decimal:
        """Calculate breadth ratio from price and volume data."""
        if len(closes) < 2:
            return Decimal("1.0")

        # Simple breadth: ratio of positive to negative price changes over lookback period
        positive_changes = Decimal("0")
        negative_changes = Decimal("0")

        for i in range(1, min(len(closes), 21)):  # Use last 20 days
            change = closes[i] - closes[i - 1]
            if change > Decimal("0"):
                positive_changes += change
            else:
                negative_changes += abs(change)

        if negative_changes == Decimal("0"):
            return Decimal("2.0")  # Cap at reasonable maximum

        ratio = positive_changes / negative_changes
        return min(Decimal("2.0"), max(Decimal("0.5"), ratio))

    def _default_indicators(self) -> IndicatorSnapshot:
        """Return default indicator values when calculation fails."""
        return IndicatorSnapshot(
            rsi=Decimal("50"),
            adx=Decimal("20"),
            atr=Decimal("0"),
            macd_histogram=Decimal("0"),
            bollinger_upper=Decimal("0"),
            bollinger_middle=Decimal("0"),
            bollinger_lower=Decimal("0"),
        )

    def _determine_exchange(self, symbol: str) -> Exchange:
        """Determine exchange from symbol name or config."""
        symbol_upper = symbol.upper()

        # Check for exchange prefixes or suffixes
        if any(prefix in symbol_upper for prefix in ("NIFTY", "BANKNIFTY")):
            return Exchange.NSE
        if "MCX" in symbol_upper:
            return Exchange.MCX
        if "NIFTY" in symbol_upper or any(x in symbol_upper for x in ("CE", "PE", "FUT")):
            return Exchange.NSE

        # Default to first configured exchange
        return self._config.exchanges[0] if self._config.exchanges else Exchange.NSE

    @staticmethod
    def _determine_category(symbol: str) -> InstrumentCategory:
        """Determine instrument category from symbol name."""
        symbol_upper = symbol.upper()
        if "FUT" in symbol_upper or "FUTURE" in symbol_upper:
            return InstrumentCategory.FUTURE
        if "CE" in symbol_upper or "PE" in symbol_upper or len(symbol_upper) > 10:
            return InstrumentCategory.OPTION
        return InstrumentCategory.STOCK

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
                    regime=MarketRegime.SIDEWAYS,
                    rank=idx + 1,
                    timestamp_utc=s.market_data.timestamp_utc,
                    close_price=s.market_data.close_price,
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
        is_very_strong = abs(score) >= self._config.very_strong_threshold
        return score, is_very_strong

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


# Mock helpers for testing
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
