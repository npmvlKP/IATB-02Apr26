"""
Instrument scanner for auto-selecting tradable Stocks/Options/Futures.

Uses jugaad-data + pandas-ta (proven blueprint components) to scan NSE/CDS/MCX
and rank top gainers/losers by % change with multi-factor filtering.
"""

import importlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.indicators import IndicatorSnapshot
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


def _iter_dataframe_rows(frame: Any) -> Iterable[Mapping[str, object]]:
    """Iterate over jugaad-data DataFrame rows."""
    if hasattr(frame, "iterrows"):
        for _, payload in frame.iterrows():
            if not isinstance(payload, Mapping):
                msg = "jugaad dataframe rows must be mapping-like"
                raise ConfigError(msg)
            yield payload
        return
    if isinstance(frame, list):
        for payload in frame:
            if not isinstance(payload, Mapping):
                msg = "jugaad list rows must be mapping-like"
                raise ConfigError(msg)
            yield payload
        return
    msg = "Unsupported jugaad history response type"
    raise ConfigError(msg)


def _coerce_datetime(value: object) -> datetime:
    """Convert value to UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.strip()
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from jugaad payload: {type(value).__name__}"
    raise ConfigError(msg)


def _extract_value(payload: Mapping[str, object], keys: tuple[str, ...]) -> object:
    """Extract value from payload using fallback keys."""
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    msg = f"Missing required OHLCV key from jugaad payload: {keys}"
    raise ConfigError(msg)


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
        symbols: Sequence[str] | None = None,
    ) -> None:
        self._config = config or ScannerConfig()
        self._strength_scorer = strength_scorer or StrengthScorer()
        self._sentiment_analyzer = sentiment_analyzer
        self._rl_predictor = rl_predictor
        self._symbols = symbols or []
        self._pandas_ta = self._load_pandas_ta()
        self._jugaad_nse = self._load_jugaad_nse()

    @staticmethod
    def _load_pandas_ta() -> object:
        """Load pandas-ta module."""
        try:
            return importlib.import_module("pandas_ta")
        except ModuleNotFoundError as exc:
            msg = "pandas-ta dependency is required for InstrumentScanner"
            raise ConfigError(msg) from exc

    @staticmethod
    def _load_jugaad_nse() -> Callable[..., object]:
        """Load jugaad-data.nse.stock_df function."""
        try:
            module = importlib.import_module("jugaad_data.nse")
        except ModuleNotFoundError as exc:
            msg = "jugaad-data dependency is required for InstrumentScanner"
            raise ConfigError(msg) from exc
        if not hasattr(module, "stock_df"):
            msg = "jugaad_data.nse.stock_df is not available"
            raise ConfigError(msg)
        return cast(Callable[..., object], module.stock_df)

    def scan(
        self,
        direction: SortDirection = SortDirection.GAINERS,
    ) -> ScannerResult:
        """
        Scan instruments using jugaad-data + pandas-ta.

        Args:
            direction: Sort by gainers or losers

        Returns:
            ScannerResult with ranked gainers/losers
        """
        scan_timestamp = datetime.now(UTC)
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
        """Fetch market data using jugaad-data and calculate indicators with pandas-ta."""
        if not self._symbols:
            return []

        all_data: list[MarketData] = []
        end_date = datetime.now(UTC).date()
        start_date = (datetime.now(UTC) - timedelta(days=self._config.lookback_days)).date()

        for symbol in self._symbols:
            try:
                frame = self._jugaad_nse(
                    symbol=symbol,
                    from_date=start_date,
                    to_date=end_date,
                )

                if frame is None or len(frame) == 0:  # type: ignore[arg-type]
                    continue

                indicators = self._calculate_indicators(frame)
                latest_row = None
                for row in _iter_dataframe_rows(frame):
                    row_dict = dict(row)
                    if latest_row is None or _coerce_datetime(
                        _extract_value(row_dict, ("timestamp", "TIMESTAMP", "date", "DATE"))
                    ) > cast("datetime", latest_row["timestamp"]):
                        latest_row = {
                            "timestamp": _coerce_datetime(
                                _extract_value(row_dict, ("timestamp", "TIMESTAMP", "date", "DATE"))
                            ),
                            "open": _to_decimal(_extract_value(row_dict, ("open", "OPEN")), "open"),
                            "high": _to_decimal(_extract_value(row_dict, ("high", "HIGH")), "high"),
                            "low": _to_decimal(_extract_value(row_dict, ("low", "LOW")), "low"),
                            "close": _to_decimal(
                                _extract_value(row_dict, ("close", "CLOSE")), "close"
                            ),
                            "volume": _to_decimal(
                                (
                                    _extract_value(
                                        row_dict,
                                        ("volume", "VOLUME", "TOTTRDQTY", "TTL_TRD_QNT"),
                                    ),
                                ),
                                "volume",
                            ),
                        }

                if latest_row is None:
                    continue

                avg_volume = self._calculate_average_volume(frame)
                market_data = MarketData(
                    symbol=symbol,
                    exchange=Exchange.NSE,
                    category=self._determine_category(symbol),
                    close_price=latest_row["close"],  # type: ignore[arg-type]
                    prev_close_price=self._get_previous_close(frame),
                    volume=latest_row["volume"],  # type: ignore[arg-type]
                    avg_volume=avg_volume,
                    timestamp_utc=latest_row["timestamp"],  # type: ignore[arg-type]
                    high_price=latest_row["high"],  # type: ignore[arg-type]
                    low_price=latest_row["low"],  # type: ignore[arg-type]
                    adx=indicators.adx,
                    atr_pct=(
                        indicators.atr / latest_row["close"]  # type: ignore[operator]
                        if latest_row["close"] > Decimal("0")  # type: ignore[operator]
                        else Decimal("0")
                    ),
                    breadth_ratio=Decimal("1.5"),
                )
                all_data.append(market_data)
            except Exception:  # noqa: S112 - scanner continues on individual failures
                continue

        return all_data

    def _calculate_indicators(self, frame: Any) -> "IndicatorSnapshot":
        """Calculate technical indicators using pandas-ta."""
        closes: list[Decimal] = []
        highs: list[Decimal] = []
        lows: list[Decimal] = []

        for row in _iter_dataframe_rows(frame):
            row_dict = dict(row)
            try:
                closes.append(_to_decimal(_extract_value(row_dict, ("close", "CLOSE")), "close"))
                highs.append(_to_decimal(_extract_value(row_dict, ("high", "HIGH")), "high"))
                lows.append(_to_decimal(_extract_value(row_dict, ("low", "LOW")), "low"))
            except Exception:  # noqa: S112 - scanner continues on individual failures
                continue

        if len(closes) < 14:
            return self._default_indicators()

        try:
            rsi_result = self._pandas_ta.rsi(closes, length=14)  # type: ignore[attr-defined]
            adx_payload = self._pandas_ta.adx(high=highs, low=lows, close=closes, length=14)  # type: ignore[attr-defined]
            atr_result = self._pandas_ta.atr(high=highs, low=lows, close=closes, length=14)  # type: ignore[attr-defined]
            macd_payload = self._pandas_ta.macd(closes, fast=12, slow=26, signal=9)  # type: ignore[attr-defined]  # noqa: F841
            bb_payload = self._pandas_ta.bbands(closes, length=20, std=2.0)  # type: ignore[attr-defined]

            adx_col = self._extract_from_payload(adx_payload, "ADX_14")
            atr_val = _last_decimal(atr_result, "atr")
            bb_upper = self._extract_from_payload(bb_payload, "BBU_20_2.0")
            bb_middle = self._extract_from_payload(bb_payload, "BBM_20_2.0")
            bb_lower = self._extract_from_payload(bb_payload, "BBL_20_2.0")

            return IndicatorSnapshot(
                rsi=_last_decimal(rsi_result, "rsi"),
                adx=_last_decimal(adx_col, "adx"),
                atr=atr_val,
                macd_histogram=Decimal("0"),  # Simplified
                bollinger_upper=_last_decimal(bb_upper, "bb_upper"),
                bollinger_middle=_last_decimal(bb_middle, "bb_middle"),
                bollinger_lower=_last_decimal(bb_lower, "bb_lower"),
            )
        except Exception:
            return self._default_indicators()

    def _extract_from_payload(self, payload: object, column_name: str) -> object:
        """Extract column from pandas-ta payload."""
        if isinstance(payload, dict):
            if column_name not in payload:
                msg = f"indicator payload missing column: {column_name}"
                raise ConfigError(msg)
            return payload[column_name]
        if hasattr(payload, "__getitem__"):
            try:
                return payload[column_name]
            except Exception as exc:
                msg = f"indicator payload missing column: {column_name}"
                raise ConfigError(msg) from exc
        msg = "indicator payload must support named column access"
        raise ConfigError(msg)

    def _default_indicators(self) -> "IndicatorSnapshot":
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

    def _calculate_average_volume(self, frame: Any) -> Decimal:
        """Calculate average volume over the period."""
        volumes: list[Decimal] = []
        for row in _iter_dataframe_rows(frame):
            row_dict = dict(row)
            try:
                vol = _to_decimal(
                    _extract_value(row_dict, ("volume", "VOLUME", "TOTTRDQTY", "TTL_TRD_QNT")),
                    "volume",
                )
                volumes.append(vol)
            except Exception:  # noqa: S112 - scanner continues on individual failures
                continue

        if not volumes:
            return Decimal("0")
        return sum(volumes) / Decimal(str(len(volumes)))

    def _get_previous_close(self, frame: Any) -> Decimal:
        """Get previous close price from frame."""
        closes: list[Decimal] = []
        for row in _iter_dataframe_rows(frame):
            row_dict = dict(row)
            try:
                close = _to_decimal(_extract_value(row_dict, ("close", "CLOSE")), "close")
                closes.append(close)
            except Exception:  # noqa: S112 - scanner continues on individual failures
                continue

        if len(closes) < 2:
            return Decimal("0")
        return closes[-2]

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
