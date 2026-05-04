"""
Instrument scanner for auto-selecting tradable Stocks/Options/Futures.

Uses DataProvider abstraction + indicator module to scan NSE/CDS/MCX
and rank top gainers/losers by % change with multi-factor filtering.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_timestamp
from iatb.data.base import DataProvider
from iatb.data.market_data_cache import MarketDataCache
from iatb.data.rate_limiter import (
    AsyncRateLimiter,
    CircuitBreaker,
    RetryConfig,
    retry_with_backoff,
)
from iatb.market_strength.indicators import IndicatorSnapshot, PandasTaIndicators
from iatb.market_strength.regime_detector import MarketRegime, RegimeDetector
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.selection._util import DirectionalIntent
from iatb.selection.drl_signal import BacktestConclusion, DRLSignalOutput, compute_drl_signal
from iatb.selection.instrument_scorer import InstrumentScorer, InstrumentSignals
from iatb.selection.ranking import RankingConfig
from iatb.selection.sentiment_signal import (
    SentimentSignalInput,
    SentimentSignalOutput,
    compute_sentiment_signal,
)
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import (
    ProfileShape,
    VolumeProfileSignalOutput,
)
from iatb.sentiment.aggregator import SentimentAggregator

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
    - DRL exit probability

    Emits only if ALL factors pass.
    Uses regime-aware composite scoring from InstrumentScorer.
    """

    def __init__(  # noqa: G10
        self,
        config: ScannerConfig | None = None,
        data_provider: DataProvider | None = None,
        strength_scorer: StrengthScorer | None = None,
        sentiment_aggregator: SentimentAggregator | None = None,
        regime_detector: RegimeDetector | None = None,
        instrument_scorer: InstrumentScorer | None = None,
        correlations: dict[tuple[str, str], Decimal] | None = None,
        ranking_config: RankingConfig | None = None,
        symbols: Sequence[str] | None = None,
        cache_ttl_seconds: int = 60,
        rate_limiter: AsyncRateLimiter | None = None,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        # Test compatibility parameters (legacy naming)
        sentiment_analyzer: Callable[[str], tuple[Decimal, bool]] | None = None,
        rl_predictor: Callable[[list[Decimal]], Decimal] | None = None,
    ) -> None:
        self._config = config or ScannerConfig()
        self._data_provider = data_provider

        self._strength_scorer = strength_scorer or StrengthScorer()
        self._sentiment_aggregator = sentiment_aggregator
        # Legacy test compatibility: prefer sentiment_analyzer if provided
        self._sentiment_analyzer = sentiment_analyzer
        self._regime_detector = regime_detector or RegimeDetector()
        self._instrument_scorer = instrument_scorer or InstrumentScorer()
        self._correlations = correlations or {}
        self._ranking_config = ranking_config or RankingConfig()
        self._symbols = symbols or []
        self._cache = MarketDataCache(default_ttl_seconds=cache_ttl_seconds)
        self._indicators: PandasTaIndicators | None = None
        self._current_regime: MarketRegime = MarketRegime.SIDEWAYS
        # RL predictor for exit probability (test override)
        self._rl_predictor = rl_predictor

        self._initialize_components(rate_limiter, retry_config, circuit_breaker)

    def _initialize_components(
        self,
        rate_limiter: AsyncRateLimiter | None,
        retry_config: RetryConfig | None,
        circuit_breaker: CircuitBreaker | None,
    ) -> None:
        """Initialize async components: rate limiter, retry config, circuit breaker."""
        # Rate limiter for controlling concurrent API requests
        # Default: 10 req/sec with burst capacity of 20 for parallel fetching
        self._rate_limiter = rate_limiter or AsyncRateLimiter(
            requests_per_second=10.0,
            burst_capacity=20,
        )

        # Retry configuration for API resilience
        # Default: 3 retries with exponential backoff (1s, 2s, 4s)
        self._retry_config = retry_config or RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            jitter_seconds=0.5,
        )

        # Circuit breaker to prevent cascading failures
        # Opens after 5 consecutive failures, resets after 60 seconds
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5, reset_timeout=60.0, name="instrument_scanner"
        )

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

        self._current_regime = self._detect_regime(all_candidates)
        scored = self._score_candidates_with_pipeline(all_candidates)
        filtered = self._apply_filters(scored)
        gainers, losers = self._rank_and_split_with_correlation(filtered)
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

        # Check if there's already a running event loop
        try:
            asyncio.get_running_loop()
            # We're in an async context, need to run in thread to avoid blocking
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self._fetch_symbols_parallel())
                results = future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            results = asyncio.run(self._fetch_symbols_parallel())

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

        exchange = self._determine_exchange(symbol)
        category = self._determine_category(symbol)

        bars = await self._fetch_ohlcv_bars(symbol, exchange)
        if not bars:
            return None

        price_data = self._extract_price_data(bars)
        if len(price_data.closes) < 2:
            return None

        indicators = self._calculate_indicators(
            price_data.closes, price_data.highs, price_data.lows
        )
        return self._build_market_data(
            symbol, exchange, category, price_data, indicators, bars[0].source
        )

    async def _fetch_ohlcv_bars_raw(
        self,
        symbol: str,
        exchange: Exchange,
        since_timestamp: Timestamp | None,
    ) -> list[Any]:
        """
        Raw OHLCV fetch without retry/backoff (for retry wrapper).
        """
        if self._data_provider is None:
            msg = "DataProvider not configured"
            raise ConfigError(msg)

        # get_ohlcv() is async, no need for asyncio.to_thread wrapper
        bars = await self._data_provider.get_ohlcv(
            symbol=symbol,
            exchange=exchange,
            timeframe="1d",
            since=since_timestamp,
            limit=self._config.lookback_days,
        )
        return bars

    async def _fetch_ohlcv_bars(self, symbol: str, exchange: Exchange) -> list[Any]:
        """
        Fetch OHLCV bars from data provider with rate limiting and retry/backoff.

        Uses exponential backoff (1s, 2s, 4s) with jitter and circuit breaker
        to handle transient failures and prevent cascading failures.
        """
        if self._data_provider is None:
            msg = "DataProvider not configured"
            raise ConfigError(msg)

        async with self._rate_limiter:
            since_timestamp = create_timestamp(
                datetime.now(UTC) - timedelta(days=self._config.lookback_days)
            )
            # Use retry wrapper with exponential backoff and circuit breaker
            bars: list[Any] = await retry_with_backoff(
                self._fetch_ohlcv_bars_raw,
                config=self._retry_config,
                circuit_breaker=self._circuit_breaker,
                symbol=symbol,
                exchange=exchange,
                since_timestamp=since_timestamp,
            )
            return bars

    @dataclass
    class _PriceData:
        """Container for extracted price data."""

        closes: list[Decimal]
        highs: list[Decimal]
        lows: list[Decimal]
        volumes: list[Decimal]
        timestamps: list[datetime]

    def _extract_price_data(self, bars: list[Any]) -> _PriceData:
        """Extract price and volume data from OHLCV bars."""
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

        return self._PriceData(closes, highs, lows, volumes, timestamps)

    def _build_market_data(
        self,
        symbol: str,
        exchange: Exchange,
        category: InstrumentCategory,
        price_data: _PriceData,
        indicators: IndicatorSnapshot,
        data_source: str,
    ) -> MarketData:
        """Build MarketData object from price data and indicators."""
        latest_close = price_data.closes[-1]
        prev_close = price_data.closes[-2]
        avg_volume = sum(price_data.volumes) / Decimal(str(len(price_data.volumes)))
        breadth_ratio = self._calculate_breadth_ratio(price_data.closes, price_data.volumes)
        atr_pct = indicators.atr / latest_close if latest_close > Decimal("0") else Decimal("0")

        return MarketData(
            symbol=symbol,
            exchange=exchange,
            category=category,
            close_price=latest_close,
            prev_close_price=prev_close,
            volume=price_data.volumes[-1],
            avg_volume=avg_volume,
            timestamp_utc=price_data.timestamps[-1],
            high_price=price_data.highs[-1],
            low_price=price_data.lows[-1],
            adx=indicators.adx,
            atr_pct=atr_pct,
            breadth_ratio=breadth_ratio,
            data_source=data_source,
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

    def _detect_regime(self, candidates: list[MarketData]) -> MarketRegime:
        """Detect market regime from candidate data using RegimeDetector."""
        if len(candidates) < 3:
            return MarketRegime.SIDEWAYS
        try:
            features = self._build_regime_features(candidates)
            result = self._regime_detector.detect(features)
            _LOGGER.info(
                "Regime detected: %s (confidence: %s)", result.regime.value, result.confidence
            )
            return result.regime
        except ConfigError as exc:
            _LOGGER.warning("Regime detection failed, defaulting to SIDEWAYS: %s", exc)
            return MarketRegime.SIDEWAYS
        except Exception as exc:  # nosec - B112: fallback to default on error  # noqa: S112
            _LOGGER.warning("Regime detection error, defaulting to SIDEWAYS: %s", exc)
            return MarketRegime.SIDEWAYS

    def _build_regime_features(self, candidates: list[MarketData]) -> list[list[Decimal]]:
        """Build feature matrix for regime detection from candidates."""
        features: list[list[Decimal]] = []
        for data in candidates:
            feature_row = [
                data.pct_change / Decimal("100"),
                data.adx / Decimal("100"),
                data.breadth_ratio,
                data.volume_ratio,
            ]
            features.append(feature_row)
        return features

    def _score_candidates_with_pipeline(
        self, candidates: list[MarketData]
    ) -> list[_CandidateScores]:
        """Score candidates using the wired selection pipeline."""
        scored: list[_CandidateScores] = []
        current_utc = datetime.now(UTC)

        for data in candidates:
            sentiment_score, is_very_strong = self._get_sentiment_pipeline(data, current_utc)
            strength_score, is_tradable = self._get_strength(data)
            exit_prob = self._get_exit_probability_pipeline(data, current_utc)
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

    def _get_sentiment_pipeline(
        self, data: MarketData, current_utc: datetime
    ) -> tuple[Decimal, bool]:
        """Get sentiment score using analyzer or aggregator."""
        # Legacy test override: direct analyzer callable
        if self._sentiment_analyzer is not None:
            try:
                score, is_very_strong = self._sentiment_analyzer(data.symbol)
                return score, is_very_strong
            except Exception:
                return Decimal("0"), False
        if self._sentiment_aggregator is None:
            return Decimal("0"), False
        try:
            inputs = SentimentSignalInput(
                text=f"{data.symbol} market analysis",
                volume_ratio=data.volume_ratio,
                instrument_symbol=data.symbol,
                exchange=data.exchange,
                timestamp_utc=data.timestamp_utc,
            )
            intent = (
                DirectionalIntent.LONG
                if data.pct_change > Decimal("0")
                else DirectionalIntent.SHORT
            )
            signal = compute_sentiment_signal(
                self._sentiment_aggregator, inputs, current_utc, intent
            )
            is_very_strong = abs(signal.score) >= self._config.very_strong_threshold
            return signal.score, is_very_strong
        except Exception as exc:  # nosec - B112: fallback to defaults on error  # noqa: S112
            _LOGGER.debug("Sentiment pipeline failed for %s: %s", data.symbol, exc)
            return Decimal("0"), False

    def _get_strength(self, data: MarketData) -> tuple[Decimal, bool]:
        """Get strength score and tradability flag."""
        inputs = StrengthInputs(
            breadth_ratio=data.breadth_ratio,
            regime=self._current_regime,
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

    def _get_exit_probability_pipeline(self, data: MarketData, current_utc: datetime) -> Decimal:
        """Get DRL exit probability using rl_predictor or compute_drl_signal."""
        # Legacy test override: rl_predictor callable
        if self._rl_predictor is not None:
            try:
                # RL predictor expects a list of Decimal features; provide empty list as dummy
                return self._rl_predictor([])
            except Exception:
                return Decimal("0")
        try:
            conclusion = BacktestConclusion(
                instrument_symbol=data.symbol,
                out_of_sample_sharpe=data.pct_change / Decimal("100"),
                max_drawdown_pct=data.atr_pct * Decimal("10"),
                win_rate=Decimal("0.5"),
                total_trades=10,
                monte_carlo_robust=True,
                walk_forward_overfit_detected=False,
                mean_overfit_ratio=Decimal("1.0"),
                timestamp_utc=data.timestamp_utc,
            )
            drl_output = compute_drl_signal(conclusion, current_utc)
            return drl_output.score
        except Exception as exc:  # nosec - B112: fallback to zero on error  # noqa: S112
            _LOGGER.debug("DRL signal failed for %s: %s", data.symbol, exc)
            return Decimal("0")

    def _apply_filters(self, scored: list[_CandidateScores]) -> list[_CandidateScores]:
        """Apply all filters: sentiment, strength, volume, DRL."""
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

    def _rank_and_split_with_correlation(  # noqa: G10
        self, filtered: list[_CandidateScores]
    ) -> tuple[list[ScannerCandidate], list[ScannerCandidate]]:
        """Rank by composite score and split into gainers/losers with correlation filtering."""
        if not filtered:
            return [], []

        instrument_signals = self._build_instrument_signals(filtered)

        # Use InstrumentScorer to compute regime-aware composite scores
        selection_result = self._instrument_scorer.score_and_select(
            instrument_signals, self._current_regime, self._correlations
        )

        # Build symbol to composite score mapping
        symbol_to_composite = {
            s.symbol: s.composite.composite_score
            for s in self._instrument_scorer.score_instruments(
                instrument_signals, self._current_regime
            )
        }

        # Split into gainers and losers and convert to candidates
        gainers_data = [c for c in filtered if c.market_data.pct_change > Decimal("0")]
        losers_data = [c for c in filtered if c.market_data.pct_change < Decimal("0")]

        gainers = self._to_scanner_candidates_with_scores(
            gainers_data, selection_result.selected, symbol_to_composite
        )
        losers = self._to_scanner_candidates_with_scores(
            losers_data, selection_result.selected, symbol_to_composite
        )

        gainers_sorted = sorted(gainers, key=lambda c: c.composite_score, reverse=True)
        losers_sorted = sorted(losers, key=lambda c: c.composite_score)
        return gainers_sorted, losers_sorted

    def _build_instrument_signals(
        self, filtered: list[_CandidateScores]
    ) -> list[InstrumentSignals]:
        """Build InstrumentSignals from candidate data."""
        signals: list[InstrumentSignals] = []
        for c in filtered:
            signals.append(self._build_instrument_signal(c))
        return signals

    def _build_instrument_signal(self, c: _CandidateScores) -> InstrumentSignals:
        """Build a single InstrumentSignals object."""
        directional_bias = "BULLISH" if c.market_data.pct_change > Decimal("0") else "BEARISH"

        sentiment_output = self._build_sentiment_output(c, directional_bias)
        strength_output = self._build_strength_output(c)
        volume_output = self._build_volume_output(c)
        drl_output = self._build_drl_output(c)
        strength_inputs = self._build_strength_inputs(c)

        return InstrumentSignals(
            symbol=c.market_data.symbol,
            exchange=c.market_data.exchange,
            sentiment=sentiment_output,
            strength=strength_output,
            volume_profile=volume_output,
            drl=drl_output,
            strength_inputs=strength_inputs,
        )

    def _build_sentiment_output(
        self, c: _CandidateScores, directional_bias: str
    ) -> SentimentSignalOutput:
        """Build sentiment signal output."""
        return SentimentSignalOutput(
            score=c.sentiment_score,
            confidence=Decimal("0.8") if c.is_very_strong else Decimal("0.5"),
            directional_bias=directional_bias,
            metadata={"symbol": c.market_data.symbol},
        )

    def _build_strength_output(self, c: _CandidateScores) -> StrengthSignalOutput:
        """Build strength signal output."""
        return StrengthSignalOutput(
            score=c.strength_score,
            confidence=Decimal("0.8") if c.is_strength_tradable else Decimal("0.5"),
            regime=self._current_regime,
            tradable=c.is_strength_tradable,
            metadata={"symbol": c.market_data.symbol},
        )

    def _build_volume_output(self, c: _CandidateScores) -> VolumeProfileSignalOutput:
        """Build volume profile signal output."""
        volume_score = min(Decimal("1"), c.market_data.volume_ratio / Decimal("5"))
        return VolumeProfileSignalOutput(
            score=volume_score,
            confidence=Decimal("0.7"),
            shape=ProfileShape.D_BALANCED,
            poc_distance_pct=Decimal("0"),
            va_width_pct=Decimal("10"),
            metadata={"symbol": c.market_data.symbol},
        )

    def _build_drl_output(self, c: _CandidateScores) -> DRLSignalOutput:
        """Build DRL output."""
        return DRLSignalOutput(
            score=c.exit_probability,
            confidence=Decimal("0.7"),
            robust=True,
            metadata={"symbol": c.market_data.symbol},
        )

    def _build_strength_inputs(self, c: _CandidateScores) -> StrengthInputs:
        """Build strength inputs."""
        return StrengthInputs(
            breadth_ratio=c.market_data.breadth_ratio,
            regime=self._current_regime,
            adx=c.market_data.adx,
            volume_ratio=c.market_data.volume_ratio,
            volatility_atr_pct=c.market_data.atr_pct,
        )

    def _build_metadata(self, scored: _CandidateScores) -> dict[str, str]:
        """Build metadata dictionary for a scored candidate."""
        return {
            "adx": str(scored.market_data.adx),
            "atr_pct": str(scored.market_data.atr_pct),
            "strength_score": str(scored.strength_score),
            "regime": self._current_regime.value,
        }

    def _to_scanner_candidates_with_scores(
        self,
        scored: list[_CandidateScores],
        ranked: list[Any],
        symbol_to_composite: dict[str, Any],
    ) -> list[ScannerCandidate]:
        """Convert scored candidates to ScannerCandidate using pre-computed composite scores."""
        candidates: list[ScannerCandidate] = []
        for idx, s in enumerate(scored):
            # Get composite score from the pre-computed mapping
            composite = symbol_to_composite.get(s.market_data.symbol, Decimal("0"))

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
                    regime=self._current_regime,
                    rank=idx + 1,
                    timestamp_utc=s.market_data.timestamp_utc,
                    close_price=s.market_data.close_price,
                    metadata={
                        "adx": str(s.market_data.adx),
                        "atr_pct": str(s.market_data.atr_pct),
                        "strength_score": str(s.strength_score),
                        "regime": self._current_regime.value,
                    },
                )
            )
        return candidates


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
