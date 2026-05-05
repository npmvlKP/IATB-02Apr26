"""
Weighted sentiment ensemble and tradability gate.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer
from iatb.sentiment.helpers import compute_weighted_ensemble
from iatb.sentiment.news_analyzer import NewsAnalyzer, NewsArticle, NewsSentimentResult
from iatb.sentiment.recency_weighting import recency_weighted_score
from iatb.sentiment.social_sentiment import SocialPost, SocialSentimentAnalyzer
from iatb.sentiment.vader_analyzer import VaderAnalyzer
from iatb.sentiment.volume_filter import has_volume_confirmation

_LOGGER = logging.getLogger(__name__)
VERY_STRONG_THRESHOLD = Decimal("0.75")

# Updated weights per spec: FinBERT 0.35, AION 0.25, VADER 0.10, News 0.15, Social 0.15
DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "finbert": Decimal("0.35"),
    "aion": Decimal("0.25"),
    "vader": Decimal("0.10"),
    "news": Decimal("0.15"),
    "social": Decimal("0.15"),
}


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
    Includes news and social sentiment in the weighted ensemble with
    recency-weighted article scoring.
    """

    def __init__(
        self,
        finbert: SentimentAnalyzer | None = None,
        aion: SentimentAnalyzer | None = None,
        vader: SentimentAnalyzer | None = None,
        news_analyzer: NewsAnalyzer | None = None,
        social_analyzer: SocialSentimentAnalyzer | None = None,
        weights: dict[str, Decimal] | None = None,
        very_strong_threshold: Decimal = VERY_STRONG_THRESHOLD,
        enable_graceful_fallback: bool = True,
        enable_news: bool = True,
        enable_social: bool = True,
    ) -> None:
        if very_strong_threshold <= Decimal("0") or very_strong_threshold > Decimal("1"):
            msg = "very_strong_threshold must be in (0, 1]"
            raise ConfigError(msg)
        self._very_strong_threshold = very_strong_threshold
        self._enable_graceful_fallback = enable_graceful_fallback
        self._enable_news = enable_news
        self._enable_social = enable_social
        # Store analyzers
        self._news_analyzer = news_analyzer or NewsAnalyzer()
        self._social_analyzer = social_analyzer or SocialSentimentAnalyzer()
        # Weight configuration
        self._weights = weights or DEFAULT_WEIGHTS.copy()

        # Initialize text analyzers with graceful fallback
        self._analyzers: dict[str, tuple[SentimentAnalyzer, Decimal]] = {}
        self._initialize_analyzers(finbert, aion, vader)

    def _initialize_analyzer_with_fallback(
        self,
        name: str,
        analyzer: SentimentAnalyzer | None,
        fallback: SentimentAnalyzer | None,
        status: object | None,
    ) -> tuple[SentimentAnalyzer, Decimal]:
        """Initialize a single analyzer with graceful fallback.

        Args:
            name: Analyzer name (finbert, aion, etc.).
            analyzer: Optional analyzer instance.
            fallback: Fallback analyzer instance.
            status: RegistryStatus from registry (optional).

        Returns:
            Tuple of (analyzer, weight).
        """
        # Avoid circular import in TYPE_CHECKING
        try:
            from iatb.ml.model_registry import RegistryStatus, get_registry

            _ = RegistryStatus  # ensure type reference
            registry = get_registry()
            status = registry.get_status() if status is None else status
        except Exception:
            status = None

        health = getattr(status, "model_health", {}).get(name) if status else None
        if health and getattr(getattr(health, "status", object()), "value", None) == "available":
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

    def _get_weight(self, name: str) -> Decimal:
        """Get weight for a given source name.

        Falls back to DEFAULT_WEIGHTS if not explicitly set.
        """
        return self._weights.get(name, DEFAULT_WEIGHTS.get(name, Decimal("0")))

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
            self._analyzers["finbert"] = self._initialize_analyzer_with_fallback(
                "finbert", finbert, vader, None
            )
            self._analyzers["aion"] = self._initialize_analyzer_with_fallback(
                "aion", aion, vader, None
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

    # ------------------------------------------------------------------
    # News & Social integration
    # ------------------------------------------------------------------

    def analyze_news(
        self,
        articles: list["NewsArticle"],
        symbol: str,
    ) -> NewsSentimentResult:
        """Analyze news articles and return result with recency weighting.

        Uses recency_weighted_score to weight recent articles more heavily
        in the final aggregate score.

        Args:
            articles: List of NewsArticle objects.
            symbol: Financial instrument symbol.

        Returns:
            NewsSentimentResult with recency-weighted scores.
        """
        result = self._news_analyzer.analyze(articles, symbol)
        # Apply recency weighting if articles are available
        if result.articles:
            recency_scores = [
                (article.score, datetime.fromisoformat(article.metadata.get("published_at", "")))
                for article in result.articles
                if "published_at" in article.metadata
            ]
            if recency_scores:
                try:
                    recency_score = recency_weighted_score(
                        recency_scores,
                        datetime.now(UTC),
                    )
                    # Blend original score with recency-weighted score (70/30)
                    blended = result.overall_score * Decimal("0.7") + recency_score * Decimal("0.3")
                    from dataclasses import replace

                    result = replace(result, overall_score=blended)
                except Exception as exc:
                    _LOGGER.debug("Recency weighting failed, using raw score: %s", exc)
        return result

    def analyze_social(
        self,
        posts: list[SocialPost],
        symbol: str,
    ) -> SentimentScore:
        """Analyze social posts and return a unified SentimentScore.

        Args:
            posts: List of SocialPost objects.
            symbol: Financial instrument symbol.

        Returns:
            SentimentScore representing social sentiment.
        """
        return self._social_analyzer.analyze_to_sentiment_score(posts, symbol)

    def _collect_news_component(
        self,
        news_articles: list["NewsArticle"],
        symbol: str,
    ) -> SentimentScore | None:
        """Analyze news and return a SentimentScore for the ensemble."""
        try:
            result = self.analyze_news(news_articles, symbol)
            return SentimentScore(
                source="news",
                score=result.overall_score,
                confidence=result.overall_confidence,
                label=sentiment_label_from_score(result.overall_score),
                text_excerpt=f"News sentiment for {symbol}: {result.sentiment_label}",
                metadata={
                    "article_count": str(result.article_count),
                    "timestamp": result.timestamp.isoformat(),
                },
            )
        except Exception as exc:
            _LOGGER.warning("News analysis failed: %s", exc)
            return None

    def _collect_social_component(
        self,
        social_posts: list[SocialPost],
        symbol: str,
    ) -> SentimentScore | None:
        """Analyze social posts and return a SentimentScore for the ensemble."""
        try:
            return self.analyze_social(social_posts, symbol)
        except Exception as exc:
            _LOGGER.warning("Social analysis failed: %s", exc)
            return None

    def _compute_full_ensemble(
        self,
        text_composite: SentimentScore,
        component_scores: dict[str, SentimentScore],
    ) -> tuple[SentimentScore, dict[str, SentimentScore]]:
        """Normalize weights and compute the final ensemble score."""
        weights: dict[str, Decimal] = {}
        available_scores: dict[str, SentimentScore] = {}
        for name, score in component_scores.items():
            weight = self._get_weight(name)
            if weight > Decimal("0"):
                weights[name] = weight
                available_scores[name] = score

        total_weight = sum(weights.values(), Decimal("0"))
        if total_weight == Decimal("0"):
            return text_composite, component_scores

        normalized_weights = {name: w / total_weight for name, w in weights.items()}
        composite_score, composite_confidence = compute_weighted_ensemble(
            available_scores, normalized_weights
        )
        composite = SentimentScore(
            source="full_ensemble",
            score=composite_score,
            confidence=composite_confidence,
            label=sentiment_label_from_score(composite_score),
            text_excerpt=text_composite.text_excerpt,
        )
        return composite, component_scores

    def analyze_full_ensemble(
        self,
        text: str,
        news_articles: list["NewsArticle"] | None = None,
        social_posts: list[SocialPost] | None = None,
        symbol: str = "",
    ) -> tuple[SentimentScore, dict[str, SentimentScore]]:
        """Run full ensemble including text, news, and social analyzers.

        Uses the configured weights: FinBERT 0.35, AION 0.25, VADER 0.10,
        News 0.15, Social 0.15.

        Args:
            text: Primary text to analyze (for FinBERT/AION/VADER).
            news_articles: Optional list of NewsArticle objects.
            social_posts: Optional list of SocialPost objects.
            symbol: Financial instrument symbol (for news/social context).

        Returns:
            Tuple of (composite_score, component_scores_dict).
        """
        text_composite, text_components = self.analyze(text)
        component_scores: dict[str, SentimentScore] = dict(text_components)

        if self._enable_news and news_articles:
            news_score = self._collect_news_component(news_articles, symbol or "unknown")
            if news_score is not None:
                component_scores["news"] = news_score

        if self._enable_social and social_posts:
            social_score = self._collect_social_component(social_posts, symbol or "unknown")
            if social_score is not None:
                component_scores["social"] = social_score

        return self._compute_full_ensemble(text_composite, component_scores)

    def evaluate_instrument_full(
        self,
        text: str,
        volume_ratio: Decimal,
        news_articles: list["NewsArticle"] | None = None,
        social_posts: list[SocialPost] | None = None,
        symbol: str = "",
    ) -> SentimentGateResult:
        """Evaluate instrument with full sentiment ensemble including news and social.

        Args:
            text: Primary text to analyze.
            volume_ratio: Volume ratio for confirmation check.
            news_articles: Optional news articles.
            social_posts: Optional social posts.
            symbol: Financial instrument symbol.

        Returns:
            SentimentGateResult with full component breakdown.
        """
        composite, components = self.analyze_full_ensemble(
            text, news_articles, social_posts, symbol
        )
        very_strong = abs(composite.score) >= self._very_strong_threshold
        volume_confirmed = has_volume_confirmation(volume_ratio)
        return SentimentGateResult(
            composite=composite,
            very_strong=very_strong,
            volume_confirmed=volume_confirmed,
            tradable=very_strong and volume_confirmed,
            component_scores={name: score.score for name, score in components.items()},
        )
