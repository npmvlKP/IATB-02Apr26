"""
Weighted sentiment ensemble and tradability gate.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.model_registry import RegistryStatus, get_registry
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

    def _initialize_analyzer_with_fallback(
        self,
        name: str,
        analyzer: SentimentAnalyzer | None,
        fallback: SentimentAnalyzer | None,
        status: RegistryStatus | None,
    ) -> tuple[SentimentAnalyzer, Decimal]:
        """Initialize a single analyzer with graceful fallback.

        Args:
            name: Analyzer name (finbert, aion, etc.).
            analyzer: Optional analyzer instance.
            fallback: Fallback analyzer instance.
            status: RegistryStatus from registry.

        Returns:
            Tuple of (analyzer, weight).
        """
        health = status.model_health.get(name) if status else None
        if health and health.status.value == "available":
            return analyzer or self._get_analyzer_instance(name), self._get_analyzer_weight(name)
        else:
            _LOGGER.warning("%s unavailable, using VADER as fallback", name.upper())
            return fallback or VaderAnalyzer(), VaderAnalyzer.weight

    def _get_analyzer_instance(self, name: str) -> SentimentAnalyzer:
        """Get analyzer instance by name.

        Args:
            name: Analyzer name.

        Returns:
            Analyzer instance.

        Raises:
            ConfigError: If analyzer name is unknown.
        """
        analyzers: dict[str, type[SentimentAnalyzer]] = {
            "finbert": FinbertAnalyzer,
            "aion": AionAnalyzer,
            "vader": VaderAnalyzer,
        }
        if name not in analyzers:
            msg = f"Unknown analyzer: {name}"
            raise ConfigError(msg)
        return analyzers[name]()

    def _get_analyzer_weight(self, name: str) -> Decimal:
        """Get analyzer weight by name.

        Args:
            name: Analyzer name.

        Returns:
            Analyzer weight.

        Raises:
            ConfigError: If analyzer name is unknown.
        """
        weights = {
            "finbert": FinbertAnalyzer.weight,
            "aion": AionAnalyzer.weight,
            "vader": VaderAnalyzer.weight,
        }
        if name not in weights:
            msg = f"Unknown analyzer: {name}"
            raise ConfigError(msg)
        return weights[name]

    def _initialize_with_graceful_fallback(
        self,
        finbert: SentimentAnalyzer | None,
        aion: SentimentAnalyzer | None,
        vader: SentimentAnalyzer | None,
    ) -> None:
        """Initialize analyzers with graceful fallback enabled.

        Args:
            finbert: Optional FinbertAnalyzer instance.
            aion: Optional AionAnalyzer instance.
            vader: Optional VaderAnalyzer instance.
        """
        try:
            registry = get_registry()
            status = registry.get_status()

            self._analyzers["finbert"] = self._initialize_analyzer_with_fallback(
                "finbert", finbert, vader, status
            )
            self._analyzers["aion"] = self._initialize_analyzer_with_fallback(
                "aion", aion, vader, status
            )
            self._analyzers["vader"] = (vader or VaderAnalyzer(), VaderAnalyzer.weight)
        except Exception as exc:
            _LOGGER.warning("Graceful fallback failed, using defaults: %s", exc)
            self._analyzers = {
                "finbert": (finbert or FinbertAnalyzer(), FinbertAnalyzer.weight),
                "aion": (aion or AionAnalyzer(), AionAnalyzer.weight),
                "vader": (vader or VaderAnalyzer(), VaderAnalyzer.weight),
            }

    def _initialize_without_fallback(
        self,
        finbert: SentimentAnalyzer | None,
        aion: SentimentAnalyzer | None,
        vader: SentimentAnalyzer | None,
    ) -> None:
        """Initialize analyzers without graceful fallback.

        Args:
            finbert: Optional FinbertAnalyzer instance.
            aion: Optional AionAnalyzer instance.
            vader: Optional VaderAnalyzer instance.
        """
        self._analyzers = {
            "finbert": (finbert or FinbertAnalyzer(), FinbertAnalyzer.weight),
            "aion": (aion or AionAnalyzer(), AionAnalyzer.weight),
            "vader": (vader or VaderAnalyzer(), VaderAnalyzer.weight),
        }

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
        if self._enable_graceful_fallback:
            self._initialize_with_graceful_fallback(finbert, aion, vader)
        else:
            self._initialize_without_fallback(finbert, aion, vader)

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
