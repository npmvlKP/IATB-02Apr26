"""
Composite market strength scorer.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime

_MAX_ACCEPTABLE_ATR_PCT = Decimal("0.08")
_EXCHANGE_MIN_SCORE = {
    Exchange.NSE: Decimal("0.60"),
    Exchange.BSE: Decimal("0.58"),
    Exchange.MCX: Decimal("0.62"),
    Exchange.CDS: Decimal("0.60"),
    Exchange.BINANCE: Decimal("0.65"),
    Exchange.COINDCX: Decimal("0.65"),
}


@dataclass(frozen=True)
class StrengthInputs:
    breadth_ratio: Decimal
    regime: MarketRegime
    adx: Decimal
    volume_ratio: Decimal
    volatility_atr_pct: Decimal


class StrengthScorer:
    """Compute tradability score and gate trading eligibility."""

    def score(self, exchange: Exchange, inputs: StrengthInputs) -> Decimal:
        self._validate(exchange, inputs)
        breadth_score = self._normalize(inputs.breadth_ratio, cap=Decimal("2.0"))
        trend_score = self._normalize(inputs.adx, cap=Decimal("40"))
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

    @staticmethod
    def _normalize(value: Decimal, *, cap: Decimal) -> Decimal:
        normalized = value / cap if cap > Decimal("0") else Decimal("0")
        return max(Decimal("0"), min(Decimal("1"), normalized))

    @staticmethod
    def _regime_score(regime: MarketRegime) -> Decimal:
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
