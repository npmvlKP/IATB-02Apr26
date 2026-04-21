"""
Multi-factor scoring engine for instrument selection.

Combines fundamental, technical, sentiment, and market strength factors
into a unified score with configurable weights and normalization.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FundamentalFactor:
    """Fundamental analysis factors."""

    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    roe: Decimal | None = None
    debt_to_equity: Decimal | None = None
    current_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    earnings_growth: Decimal | None = None


@dataclass(frozen=True)
class TechnicalFactor:
    """Technical analysis factors."""

    rsi: Decimal | None = None
    macd_signal: Decimal | None = None
    moving_average_cross: Decimal | None = None
    bollinger_position: Decimal | None = None
    volume_trend: Decimal | None = None
    price_momentum: Decimal | None = None


@dataclass(frozen=True)
class SentimentFactor:
    """Sentiment analysis factors."""

    news_score: Decimal = Decimal("0")
    social_score: Decimal = Decimal("0")
    analyst_rating: Decimal = Decimal("0")
    insider_trading_score: Decimal = Decimal("0")


@dataclass(frozen=True)
class StrengthFactor:
    """Market strength factors."""

    relative_strength: Decimal = Decimal("0")
    sector_strength: Decimal = Decimal("0")
    volume_confirmation: Decimal = Decimal("0")


@dataclass(frozen=True)
class MultiFactorInputs:
    """All input factors for multi-factor scoring."""

    symbol: str
    fundamental: FundamentalFactor
    technical: TechnicalFactor
    sentiment: SentimentFactor
    strength: StrengthFactor


@dataclass(frozen=True)
class FactorWeights:
    """Weights for each factor category."""

    fundamental: Decimal = Decimal("0.25")
    technical: Decimal = Decimal("0.25")
    sentiment: Decimal = Decimal("0.25")
    strength: Decimal = Decimal("0.25")

    def __post_init__(self) -> None:
        total = self.fundamental + self.technical + self.sentiment + self.strength
        if abs(total - Decimal("1")) > Decimal("0.01"):
            msg = f"factor weights must sum to 1.0, got {total}"
            raise ConfigError(msg)
        for name, value in self._fields():
            if value < Decimal("0") or value > Decimal("1"):
                msg = f"weight {name} must be in [0, 1], got {value}"
                raise ConfigError(msg)

    def _fields(self) -> list[tuple[str, Decimal]]:
        return [
            ("fundamental", self.fundamental),
            ("technical", self.technical),
            ("sentiment", self.sentiment),
            ("strength", self.strength),
        ]


@dataclass(frozen=True)
class FactorScores:
    """Normalized scores for each factor."""

    fundamental_score: Decimal
    technical_score: Decimal
    sentiment_score: Decimal
    strength_score: Decimal
    fundamental_confidence: Decimal = Decimal("1")
    technical_confidence: Decimal = Decimal("1")
    sentiment_confidence: Decimal = Decimal("1")
    strength_confidence: Decimal = Decimal("1")


@dataclass(frozen=True)
class MultiFactorResult:
    """Result of multi-factor scoring."""

    symbol: str
    composite_score: Decimal
    factor_scores: FactorScores
    weights_used: FactorWeights
    component_contributions: dict[str, Decimal]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class MultiFactorScorerConfig:
    """Configuration for multi-factor scorer."""

    weights: FactorWeights = field(default_factory=FactorWeights)
    min_pe: Decimal = Decimal("5")
    max_pe: Decimal = Decimal("100")
    min_pb: Decimal = Decimal("0.5")
    max_pb: Decimal = Decimal("10")
    min_roe: Decimal = Decimal("0.05")
    max_debt_equity: Decimal = Decimal("2.0")
    rsi_oversold: Decimal = Decimal("30")
    rsi_overbought: Decimal = Decimal("70")
    min_volume_confirmation: Decimal = Decimal("0.5")


class MultiFactorScorer:
    """Multi-factor scoring engine for instrument selection."""

    def __init__(self, config: MultiFactorScorerConfig | None = None) -> None:
        self._config = config or MultiFactorScorerConfig()

    def score(self, inputs: MultiFactorInputs) -> MultiFactorResult:
        """Compute multi-factor score for a single instrument."""
        factor_scores = self._compute_factor_scores(inputs)
        composite = self._compute_composite(factor_scores)
        contributions = self._compute_contributions(factor_scores, composite)
        logger.debug("Scored %s: composite=%.2f", inputs.symbol, composite)
        return MultiFactorResult(
            symbol=inputs.symbol,
            composite_score=composite,
            factor_scores=factor_scores,
            weights_used=self._config.weights,
            component_contributions=contributions,
        )

    def score_batch(self, inputs_list: list[MultiFactorInputs]) -> list[MultiFactorResult]:
        """Score multiple instruments with rank-percentile normalization."""
        if not inputs_list:
            return []
        factor_scores_list = [self._compute_factor_scores(inp) for inp in inputs_list]
        normalized = self._normalize_scores_across_batch(factor_scores_list)
        results: list[MultiFactorResult] = []
        for inputs, norm in zip(inputs_list, normalized, strict=True):
            composite = self._compute_composite(norm)
            contributions = self._compute_contributions(norm, composite)
            results.append(
                MultiFactorResult(
                    symbol=inputs.symbol,
                    composite_score=composite,
                    factor_scores=norm,
                    weights_used=self._config.weights,
                    component_contributions=contributions,
                )
            )
        logger.info("Scored %d instruments", len(results))
        return results

    def _compute_factor_scores(self, inputs: MultiFactorInputs) -> FactorScores:
        """Compute raw scores for each factor category."""
        fundamental = self._score_fundamental(inputs.fundamental)
        technical = self._score_technical(inputs.technical)
        sentiment = self._score_sentiment(inputs.sentiment)
        strength = self._score_strength(inputs.strength)
        return FactorScores(
            fundamental_score=fundamental,
            technical_score=technical,
            sentiment_score=sentiment,
            strength_score=strength,
        )

    def _score_fundamental(self, factor: FundamentalFactor) -> Decimal:
        """Score fundamental factors (0-1)."""
        if not any(
            getattr(factor, field) is not None
            for field in [
                "pe_ratio",
                "pb_ratio",
                "roe",
                "debt_to_equity",
                "current_ratio",
                "dividend_yield",
                "earnings_growth",
            ]
        ):
            return Decimal("0.5")
        score = Decimal("0")
        count = 0
        if factor.pe_ratio is not None:
            pe_score = self._normalize_pe(factor.pe_ratio)
            score += pe_score
            count += 1
        if factor.pb_ratio is not None:
            pb_score = self._normalize_pb(factor.pb_ratio)
            score += pb_score
            count += 1
        if factor.roe is not None:
            roe_score = min(Decimal("1"), factor.roe / self._config.min_roe * Decimal("0.5"))
            score += roe_score
            count += 1
        if factor.debt_to_equity is not None:
            de_score = max(
                Decimal("0"),
                Decimal("1")
                - (factor.debt_to_equity / self._config.max_debt_equity * Decimal("0.5")),
            )
            score += de_score
            count += 1
        if factor.dividend_yield is not None:
            div_score = min(Decimal("1"), factor.dividend_yield * Decimal("10"))
            score += div_score
            count += 1
        if factor.earnings_growth is not None:
            growth_score = min(Decimal("1"), max(Decimal("0"), factor.earnings_growth))
            score += growth_score
            count += 1
        return score / max(count, 1)

    def _normalize_pe(self, pe: Decimal) -> Decimal:
        """Normalize P/E ratio (lower is better within range)."""
        if pe < self._config.min_pe:
            return Decimal("0.3")
        if pe > self._config.max_pe:
            return Decimal("0.3")
        ideal = (self._config.min_pe + self._config.max_pe) / Decimal("2")
        distance = abs(pe - ideal)
        max_distance = (self._config.max_pe - self._config.min_pe) / Decimal("2")
        return max(Decimal("0"), Decimal("1") - (distance / max_distance))

    def _normalize_pb(self, pb: Decimal) -> Decimal:
        """Normalize P/B ratio (lower is generally better)."""
        if pb < self._config.min_pb:
            return Decimal("0.4")
        if pb > self._config.max_pb:
            return Decimal("0.2")
        ideal = self._config.min_pb + (self._config.max_pb - self._config.min_pb) / Decimal("3")
        distance = abs(pb - ideal)
        max_distance = self._config.max_pb - self._config.min_pb
        return max(Decimal("0"), Decimal("1") - (distance / max_distance))

    def _score_technical(self, factor: TechnicalFactor) -> Decimal:
        """Score technical factors (0-1)."""
        score = Decimal("0")
        count = 0
        if factor.rsi is not None:
            rsi_score = self._score_rsi(factor.rsi)
            score += rsi_score
            count += 1
        if factor.macd_signal is not None:
            macd_score = min(
                Decimal("1"),
                max(Decimal("0"), factor.macd_signal + Decimal("0.5")),
            )
            score += macd_score
            count += 1
        if factor.moving_average_cross is not None:
            ma_score = min(Decimal("1"), max(Decimal("0"), factor.moving_average_cross))
            score += ma_score
            count += 1
        if factor.bollinger_position is not None:
            bb_score = min(Decimal("1"), max(Decimal("0"), factor.bollinger_position))
            score += bb_score
            count += 1
        if factor.volume_trend is not None:
            vol_score = min(Decimal("1"), max(Decimal("0"), factor.volume_trend))
            score += vol_score
            count += 1
        if factor.price_momentum is not None:
            mom_score = min(
                Decimal("1"),
                max(Decimal("0"), (factor.price_momentum + Decimal("1")) / Decimal("2")),
            )
            score += mom_score
            count += 1
        return score / max(count, 1)

    def _score_rsi(self, rsi: Decimal) -> Decimal:
        """Score RSI indicator."""
        if rsi <= self._config.rsi_oversold:
            return Decimal("0.8")
        if rsi >= self._config.rsi_overbought:
            return Decimal("0.3")
        mid = (self._config.rsi_oversold + self._config.rsi_overbought) / Decimal("2")
        distance = abs(rsi - mid)
        max_distance = (self._config.rsi_overbought - self._config.rsi_oversold) / Decimal("2")
        return max(Decimal("0"), Decimal("1") - (distance / max_distance))

    def _score_sentiment(self, factor: SentimentFactor) -> Decimal:
        """Score sentiment factors (0-1)."""
        avg_sentiment = (factor.news_score + factor.social_score + factor.analyst_rating) / Decimal(
            "3"
        )
        weighted = (avg_sentiment * Decimal("0.7")) + (
            factor.insider_trading_score * Decimal("0.3")
        )
        return min(Decimal("1"), max(Decimal("0"), weighted))

    def _score_strength(self, factor: StrengthFactor) -> Decimal:
        """Score strength factors (0-1)."""
        avg = (
            factor.relative_strength + factor.sector_strength + factor.volume_confirmation
        ) / Decimal("3")
        return min(Decimal("1"), max(Decimal("0"), avg))

    def _compute_composite(self, scores: FactorScores) -> Decimal:
        """Compute weighted composite score."""
        weights = self._config.weights
        composite = (
            scores.fundamental_score * weights.fundamental
            + scores.technical_score * weights.technical
            + scores.sentiment_score * weights.sentiment
            + scores.strength_score * weights.strength
        )
        return max(Decimal("0"), min(Decimal("1"), composite))

    def _compute_contributions(
        self, scores: FactorScores, composite: Decimal
    ) -> dict[str, Decimal]:
        """Compute contribution of each factor to composite."""
        weights = self._config.weights
        return {
            "fundamental": scores.fundamental_score * weights.fundamental,
            "technical": scores.technical_score * weights.technical,
            "sentiment": scores.sentiment_score * weights.sentiment,
            "strength": scores.strength_score * weights.strength,
        }

    def _normalize_scores_across_batch(self, scores_list: list[FactorScores]) -> list[FactorScores]:
        """Normalize scores across batch using rank-percentile."""
        if not scores_list:
            return []
        fundamental = _rank_percentile([s.fundamental_score for s in scores_list])
        technical = _rank_percentile([s.technical_score for s in scores_list])
        sentiment = _rank_percentile([s.sentiment_score for s in scores_list])
        strength = _rank_percentile([s.strength_score for s in scores_list])
        return [
            FactorScores(
                fundamental_score=fundamental[i],
                technical_score=technical[i],
                sentiment_score=sentiment[i],
                strength_score=strength[i],
                fundamental_confidence=scores_list[i].fundamental_confidence,
                technical_confidence=scores_list[i].technical_confidence,
                sentiment_confidence=scores_list[i].sentiment_confidence,
                strength_confidence=scores_list[i].strength_confidence,
            )
            for i in range(len(scores_list))
        ]


def _rank_percentile(values: list[Decimal]) -> list[Decimal]:
    """Convert values to rank percentiles (0-1)."""
    if not values:
        return []
    sorted_vals = sorted((v, i) for i, v in enumerate(values))
    result = [Decimal("0")] * len(values)
    for rank, (_, original_idx) in enumerate(sorted_vals):
        result[original_idx] = (
            Decimal(rank) / Decimal(len(values) - 1) if len(values) > 1 else Decimal("0.5")
        )
    return result
