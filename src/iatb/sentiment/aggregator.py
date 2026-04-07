"""
Weighted sentiment ensemble and tradability gate.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer
from iatb.sentiment.vader_analyzer import VaderAnalyzer
from iatb.sentiment.volume_filter import has_volume_confirmation

VERY_STRONG_THRESHOLD = Decimal("0.75")


@dataclass(frozen=True)
class SentimentGateResult:
    composite: SentimentScore
    very_strong: bool
    volume_confirmed: bool
    tradable: bool
    component_scores: dict[str, Decimal]


class SentimentAggregator:
    """Weighted ensemble with VERY_STRONG and volume confirmation filters."""

    def __init__(
        self,
        finbert: SentimentAnalyzer | None = None,
        aion: SentimentAnalyzer | None = None,
        vader: SentimentAnalyzer | None = None,
        very_strong_threshold: Decimal = VERY_STRONG_THRESHOLD,
    ) -> None:
        if very_strong_threshold <= Decimal("0") or very_strong_threshold > Decimal("1"):
            msg = "very_strong_threshold must be in (0, 1]"
            raise ConfigError(msg)
        self._very_strong_threshold = very_strong_threshold
        self._analyzers: dict[str, tuple[SentimentAnalyzer, Decimal]] = {
            "finbert": (finbert or FinbertAnalyzer(), FinbertAnalyzer.weight),
            "aion": (aion or AionAnalyzer(), AionAnalyzer.weight),
            "vader": (vader or VaderAnalyzer(), VaderAnalyzer.weight),
        }

    def analyze(self, text: str) -> tuple[SentimentScore, dict[str, SentimentScore]]:
        component_scores = {
            name: analyzer.analyze(text) for name, (analyzer, _) in self._analyzers.items()
        }
        total_weight = sum((weight for _, weight in self._analyzers.values()), Decimal("0"))
        weighted_score = sum(
            (score.score * self._analyzers[name][1] for name, score in component_scores.items()),
            Decimal("0"),
        )
        weighted_confidence = sum(
            (
                score.confidence * self._analyzers[name][1]
                for name, score in component_scores.items()
            ),
            Decimal("0"),
        )
        composite_score = weighted_score / total_weight
        composite_confidence = min(Decimal("1"), weighted_confidence / total_weight)
        composite = SentimentScore(
            source="ensemble",
            score=composite_score,
            confidence=composite_confidence,
            label=sentiment_label_from_score(composite_score),
            text_excerpt=text[:140],
        )
        return composite, component_scores

    def evaluate_instrument(self, text: str, volume_ratio: Decimal) -> SentimentGateResult:
        composite, components = self.analyze(text)
        very_strong = abs(composite.score) >= self._very_strong_threshold
        volume_confirmed = has_volume_confirmation(volume_ratio)
        return SentimentGateResult(
            composite=composite,
            very_strong=very_strong,
            volume_confirmed=volume_confirmed,
            tradable=very_strong and volume_confirmed,
            component_scores={name: score.score for name, score in components.items()},
        )
