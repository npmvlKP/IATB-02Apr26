"""
Composite market strength scorer.

Memory optimization: Pre-computes and caches normalized indicator values
to avoid re-processing in repeated score calculations.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Final

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime

_MAX_ACCEPTABLE_ATR_PCT: Final = Decimal("0.08")
_EXCHANGE_MIN_SCORE: Final = {
    Exchange.NSE: Decimal("0.60"),
    Exchange.BSE: Decimal("0.58"),
    Exchange.MCX: Decimal("0.62"),
    Exchange.CDS: Decimal("0.60"),
    Exchange.BINANCE: Decimal("0.65"),
    Exchange.COINDCX: Decimal("0.65"),
}

# Cache size limits (number of unique parameter combinations)
_NORMALIZE_CACHE_SIZE: Final = 1024
_REGIME_SCORE_CACHE_SIZE: Final = 16


@dataclass(frozen=True)
class StrengthInputs:
    breadth_ratio: Decimal
    regime: MarketRegime
    adx: Decimal
    volume_ratio: Decimal
    volatility_atr_pct: Decimal


class StrengthScorer:
    """Compute tradability score and gate trading eligibility.

    Pre-computes normalized indicator values to avoid re-processing
    and reduce CPU usage in repeated calculations.
    """

    def __init__(self, cache_enabled: bool = True) -> None:
        """Initialize strength scorer with optional caching.

        Args:
            cache_enabled: If True, enables pre-computation caching.
        """
        self._cache_enabled = cache_enabled
        if cache_enabled:
            self._normalize = self._normalize_cached
            self._normalize_concave = self._normalize_concave_cached
            self._regime_score = self._regime_score_cached
        else:
            self._normalize = self._normalize_uncached
            self._normalize_concave = self._normalize_concave_uncached
            self._regime_score = self._regime_score_uncached

    def score(self, exchange: Exchange, inputs: StrengthInputs) -> Decimal:
        self._validate(exchange, inputs)
        breadth_score = self._normalize(inputs.breadth_ratio, cap=Decimal("2.0"))
        trend_score = self._normalize_concave(inputs.adx, cap=Decimal("40"))
        volume_score = self._normalize(inputs.volume_ratio, cap=Decimal("2.0"))
        regime_score = self._regime_score(inputs.regime)
        penalty = self._volatility_penalty(inputs.volatility_atr_pct)
        weighted = (
            (breadth_score * Decimal("0.25"))
            + (trend_score * Decimal("0.25"))
            + (volume_score * Decimal("0.20"))
            + (regime_score * Decimal("0.30"))
        )
        return max(Decimal("0"), min(Decimal("1"), weighted - penalty))

    def is_tradable(self, exchange: Exchange, inputs: StrengthInputs) -> bool:
        validated_exchange = self._validate(exchange, inputs)
        if inputs.regime == MarketRegime.BEAR:
            return False
        if inputs.volatility_atr_pct > _MAX_ACCEPTABLE_ATR_PCT:
            return False
        return self.score(validated_exchange, inputs) >= _EXCHANGE_MIN_SCORE[validated_exchange]

    @staticmethod
    def _validate(exchange: object, inputs: StrengthInputs) -> Exchange:
        if not isinstance(exchange, Exchange):
            msg = f"Unsupported exchange for strength scoring: {exchange!r}"
            raise ConfigError(msg)
        if exchange not in _EXCHANGE_MIN_SCORE:
            msg = f"Unsupported exchange for strength scoring: {exchange.value}"
            raise ConfigError(msg)
        if inputs.breadth_ratio < Decimal("0"):
            msg = "breadth_ratio cannot be negative"
            raise ConfigError(msg)
        if inputs.adx < Decimal("0"):
            msg = "adx cannot be negative"
            raise ConfigError(msg)
        if inputs.volume_ratio < Decimal("0"):
            msg = "volume_ratio cannot be negative"
            raise ConfigError(msg)
        if inputs.volatility_atr_pct < Decimal("0"):
            msg = "volatility_atr_pct cannot be negative"
            raise ConfigError(msg)
        return exchange

    # Cached versions with pre-computation
    @lru_cache(maxsize=_NORMALIZE_CACHE_SIZE)  # nosec B019
    def _normalize_cached(self, value: Decimal, *, cap: Decimal) -> Decimal:
        """Normalize value to [0, 1] range with caching."""
        normalized = value / cap if cap > Decimal("0") else Decimal("0")
        return max(Decimal("0"), min(Decimal("1"), normalized))

    @lru_cache(maxsize=_NORMALIZE_CACHE_SIZE)  # nosec B019
    def _normalize_concave_cached(self, value: Decimal, *, cap: Decimal) -> Decimal:
        """Concave (sqrt) normalization with caching: emphasizes early growth."""
        linear = value / cap if cap > Decimal("0") else Decimal("0")
        clamped = max(Decimal("0"), min(Decimal("1"), linear))
        return clamped.sqrt()

    @lru_cache(maxsize=_REGIME_SCORE_CACHE_SIZE)  # nosec B019
    def _regime_score_cached(self, regime: MarketRegime) -> Decimal:
        """Get regime score with caching."""
        if regime == MarketRegime.BULL:
            return Decimal("1.0")
        if regime == MarketRegime.SIDEWAYS:
            return Decimal("0.55")
        return Decimal("0.15")

    # Uncached versions (used when caching is disabled)
    @staticmethod
    def _normalize_uncached(value: Decimal, *, cap: Decimal) -> Decimal:
        normalized = value / cap if cap > Decimal("0") else Decimal("0")
        return max(Decimal("0"), min(Decimal("1"), normalized))

    @staticmethod
    def _normalize_concave_uncached(value: Decimal, *, cap: Decimal) -> Decimal:
        linear = value / cap if cap > Decimal("0") else Decimal("0")
        clamped = max(Decimal("0"), min(Decimal("1"), linear))
        return clamped.sqrt()

    @staticmethod
    def _regime_score_uncached(regime: MarketRegime) -> Decimal:
        if regime == MarketRegime.BULL:
            return Decimal("1.0")
        if regime == MarketRegime.SIDEWAYS:
            return Decimal("0.55")
        return Decimal("0.15")

    @staticmethod
    def _volatility_penalty(volatility_atr_pct: Decimal) -> Decimal:
        if volatility_atr_pct <= Decimal("0.03"):
            return Decimal("0")
        if volatility_atr_pct <= Decimal("0.05"):
            return Decimal("0.05")
        if volatility_atr_pct <= Decimal("0.08"):
            return Decimal("0.12")
        return Decimal("0.20")

    def clear_cache(self) -> None:
        """Clear all pre-computation caches."""
        if self._cache_enabled:
            self._normalize.cache_clear()
            self._normalize_concave.cache_clear()
            self._regime_score.cache_clear()

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics for monitoring."""
        if not self._cache_enabled:
            return {"cache_enabled": 0}

        return {
            "cache_enabled": 1,
            "normalize_cache_size": self._normalize.cache_info().currsize,
            "normalize_cache_hits": self._normalize.cache_info().hits,
            "normalize_cache_misses": self._normalize.cache_info().misses,
            "normalize_concave_cache_size": self._normalize_concave.cache_info().currsize,
            "normalize_concave_cache_hits": self._normalize_concave.cache_info().hits,
            "normalize_concave_cache_misses": self._normalize_concave.cache_info().misses,
            "regime_cache_size": self._regime_score.cache_info().currsize,
            "regime_cache_hits": self._regime_score.cache_info().hits,
            "regime_cache_misses": self._regime_score.cache_info().misses,
        }
