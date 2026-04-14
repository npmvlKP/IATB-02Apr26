"""
Weighted sentiment ensemble and tradability gate.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.model_registry import get_registry
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer
from iatb.sentiment.helpers import compute_weighted_ensemble
from iatb.sentiment.vader_analyzer import VaderAnalyzer
from iatb.sentiment.volume_filter import has_volume_confirmation

_LOGGER = logging.getLogger(__name__)
VERY_STRONG_THRESHOLD = Decimal("0.75")


@dataclass(frozen=True)
class SentimentGateResult:
    composite: SentimentScore
    very_strong: bool
    volume_confirmed: bool
    tradable: bool
    component_scores: dict[str, Decimal]


class SentimentAggregator:
    """Weighted ensemble with VERY_STRONG and volume confirmation filters.

    Implements graceful degradation: FinBERT → VADER fallback when models fail.
    """

    def __init__(
        self,
        finbert: SentimentAnalyzer | None = None,
        aion: SentimentAnalyzer | None = None,
        vader: SentimentAnalyzer | None = None,
        very_strong_threshold: Decimal = VERY_STRONG_THRESHOLD,
        enable_graceful_fallback: bool = True,
    ) -> None:
        if very_strong_threshold <= Decimal("0") or very_strong_threshold > Decimal("1"):
            msg = "very_strong_threshold must be in (0, 1]"
            raise ConfigError(msg)
        self._very_strong_threshold = very_strong_threshold
        self._enable_graceful_fallback = enable_graceful_fallback

        # Initialize analyzers with graceful fallback
        self._analyzers: dict[str, tuple[SentimentAnalyzer, Decimal]] = {}
        self._initialize_analyzers(finbert, aion, vader)

    def _initialize_analyzers(
        self,
        finbert: SentimentAnalyzer | None,
        aion: SentimentAnalyzer | None,
        vader: SentimentAnalyzer | None,
    ) -> None:
        """Initialize analyzers with graceful fallback support.

        Args:
            finbert: Optional FinbertAnalyzer instance.
            aion: Optional AionAnalyzer instance.
            vader: Optional VaderAnalyzer instance.
        """
        # Check model availability if graceful fallback is enabled
        if self._enable_graceful_fallback:
            try:
                registry = get_registry()
                status = registry.get_status()

                # Check FinBERT availability
                finbert_health = status.model_health.get("finbert")
                if finbert_health and finbert_health.status.value == "available":
                    self._analyzers["finbert"] = (
                        finbert or FinbertAnalyzer(),
                        FinbertAnalyzer.weight,
                    )
                else:
                    _LOGGER.warning("FinBERT unavailable, using VADER as fallback")
                    self._analyzers["finbert"] = (
                        vader or VaderAnalyzer(),
                        VaderAnalyzer.weight,
                    )

                # Check AION availability
                aion_health = status.model_health.get("aion")
                if aion_health and aion_health.status.value == "available":
                    self._analyzers["aion"] = (aion or AionAnalyzer(), AionAnalyzer.weight)
                else:
                    _LOGGER.warning("AION unavailable, using VADER as fallback")
                    self._analyzers["aion"] = (
                        vader or VaderAnalyzer(),
                        VaderAnalyzer.weight,
                    )

                # VADER is always included as the ultimate fallback
                self._analyzers["vader"] = (vader or VaderAnalyzer(), VaderAnalyzer.weight)
            except Exception as exc:
                _LOGGER.warning("Graceful fallback failed, using defaults: %s", exc)
                # Fall back to default initialization
                self._analyzers = {
                    "finbert": (finbert or FinbertAnalyzer(), FinbertAnalyzer.weight),
                    "aion": (aion or AionAnalyzer(), AionAnalyzer.weight),
                    "vader": (vader or VaderAnalyzer(), VaderAnalyzer.weight),
                }
        else:
            # No graceful fallback, use provided or default analyzers
            self._analyzers = {
                "finbert": (finbert or FinbertAnalyzer(), FinbertAnalyzer.weight),
                "aion": (aion or AionAnalyzer(), AionAnalyzer.weight),
                "vader": (vader or VaderAnalyzer(), VaderAnalyzer.weight),
            }

        _LOGGER.info(
            "Initialized analyzers: %s",
            list(self._analyzers.keys()),
        )

    def analyze(self, text: str) -> tuple[SentimentScore, dict[str, SentimentScore]]:
        component_scores = {
            name: analyzer.analyze(text) for name, (analyzer, _) in self._analyzers.items()
        }
        weights = {name: weight for name, (_, weight) in self._analyzers.items()}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
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
