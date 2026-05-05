"""
Social sentiment analyzer for financial instruments.

Analyzes social media posts, tweets, and discussions to extract
sentiment scores for trading instruments.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore, sentiment_label_from_score

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialPost:
    """Represents a social media post."""

    content: str
    platform: str
    author: str
    published_at: datetime
    likes: int = 0
    shares: int = 0
    comments: int = 0
    followers: int = 0
    symbols: list[str] = field(default_factory=list)
    url: str = ""
    relevance_score: Decimal = Decimal("1.0")


@dataclass
class SocialSentimentConfig:
    """Configuration for social sentiment analyzer."""

    min_relevance: Decimal = Decimal("0.5")
    max_age_hours: int = 12
    min_engagement: int = 10
    positive_keywords: list[str] = field(
        default_factory=lambda: [
            "buy",
            "long",
            "bullish",
            "strong",
            "rally",
            "moon",
            "pump",
            "breakout",
            "rocket",
            "gain",
            "up",
            "high",
            "grow",
            "profit",
            "win",
            "great",
            "good",
            "amazing",
            "excellent",
            "opportunity",
            "undervalued",
            "growth",
            "expansion",
        ]
    )
    negative_keywords: list[str] = field(
        default_factory=lambda: [
            "sell",
            "short",
            "bearish",
            "weak",
            "dump",
            "crash",
            "plunge",
            "fall",
            "down",
            "low",
            "loss",
            "bad",
            "terrible",
            "awful",
            "overvalued",
            "bubble",
            "risk",
            "danger",
            "avoid",
            "scam",
            "warning",
        ]
    )
    engagement_weight: Decimal = Decimal("0.3")
    follower_weight: Decimal = Decimal("0.2")
    recency_weight: Decimal = Decimal("0.5")
    boost_factor: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        if self.min_relevance < Decimal("0") or self.min_relevance > Decimal("1"):
            msg = "min_relevance must be in [0, 1]"
            raise ConfigError(msg)
        if self.max_age_hours < 0:
            msg = "max_age_hours cannot be negative"
            raise ConfigError(msg)
        if self.min_engagement < 0:
            msg = "min_engagement cannot be negative"
            raise ConfigError(msg)
        total_weight = self.engagement_weight + self.follower_weight + self.recency_weight
        if abs(total_weight - Decimal("1")) > Decimal("0.01"):
            msg = f"engagement, follower, and recency weights must sum to 1.0, got {total_weight}"
            raise ConfigError(msg)
        if self.boost_factor < Decimal("0"):
            msg = "boost_factor cannot be negative"
            raise ConfigError(msg)


@dataclass(frozen=True)
class SocialSentimentResult:
    """Result of social sentiment analysis."""

    symbol: str
    overall_score: Decimal
    overall_confidence: Decimal
    post_count: int
    total_engagement: int
    sentiment_label: str
    posts: list[SentimentScore]
    timestamp: datetime


@runtime_checkable
class SocialSource(Protocol):
    """Protocol for social media data sources."""

    def fetch_posts(self, symbol: str, limit: int = 50) -> list[SocialPost]:
        """Fetch social posts for a symbol."""
        ...


class SocialSentimentAnalyzer:
    """Analyzes social media sentiment for financial instruments."""

    def __init__(self, config: SocialSentimentConfig | None = None) -> None:
        self._config = config or SocialSentimentConfig()

    def analyze(self, posts: list[SocialPost], symbol: str) -> SocialSentimentResult:
        """Analyze social posts for a symbol."""
        if not posts:
            logger.debug("No posts provided for %s", symbol)
            return self._empty_result(symbol)

        filtered = self._filter_posts(posts, symbol)
        if not filtered:
            logger.debug("No relevant posts for %s", symbol)
            return self._empty_result(symbol)

        sentiments = [self._analyze_post(post, symbol) for post in filtered]
        overall_score, overall_confidence = self._aggregate_sentiments(sentiments)
        sentiment_label = sentiment_label_from_score(overall_score)
        total_engagement = sum(p.likes + p.shares + p.comments for p in filtered)

        logger.info(
            "Analyzed %d posts for %s: score=%.2f, label=%s, engagement=%d",
            len(filtered),
            symbol,
            overall_score,
            sentiment_label,
            total_engagement,
        )

        return SocialSentimentResult(
            symbol=symbol,
            overall_score=overall_score,
            overall_confidence=overall_confidence,
            post_count=len(filtered),
            total_engagement=total_engagement,
            sentiment_label=sentiment_label,
            posts=sentiments,
            timestamp=datetime.now(UTC),
        )

    def analyze_to_sentiment_score(
        self,
        posts: list[SocialPost],
        symbol: str,
    ) -> SentimentScore:
        """Analyze social posts and return a single SentimentScore for the aggregator.

        Provides a bridge from SocialSentimentAnalyzer output to the
        SentimentAggregator's weighted ensemble.

        Args:
            posts: List of SocialPost objects.
            symbol: The financial instrument symbol.

        Returns:
            A SentimentScore representing the aggregated social sentiment.
        """
        result = self.analyze(posts, symbol)
        label = sentiment_label_from_score(result.overall_score)
        return SentimentScore(
            source="social",
            score=result.overall_score,
            confidence=result.overall_confidence,
            label=label,
            text_excerpt=f"Social sentiment for {symbol}: {label}",
            metadata={
                "post_count": str(result.post_count),
                "total_engagement": str(result.total_engagement),
                "timestamp": result.timestamp.isoformat(),
            },
        )

    def analyze_batch(
        self, posts_by_symbol: dict[str, list[SocialPost]]
    ) -> dict[str, SocialSentimentResult]:
        """Analyze social posts for multiple symbols."""
        results: dict[str, SocialSentimentResult] = {}
        for symbol, posts in posts_by_symbol.items():
            results[symbol] = self.analyze(posts, symbol)
        logger.info("Analyzed social sentiment for %d symbols", len(results))
        return results

    def _filter_posts(self, posts: list[SocialPost], symbol: str) -> list[SocialPost]:
        """Filter posts by relevance, age, and engagement."""
        now = datetime.now(UTC)
        filtered: list[SocialPost] = []
        for post in posts:
            if post.relevance_score < self._config.min_relevance:
                continue
            age_hours = (now - post.published_at).total_seconds() / 3600
            if age_hours > self._config.max_age_hours:
                continue
            engagement = post.likes + post.shares + post.comments
            if engagement < self._config.min_engagement:
                continue
            if symbol not in post.symbols and symbol not in post.content.lower():
                continue
            filtered.append(post)
        return filtered

    def _analyze_post(self, post: SocialPost, symbol: str) -> SentimentScore:
        """Analyze sentiment of a single social post."""
        score = self._compute_sentiment_score(post.content)
        confidence = self._compute_confidence(post, score)
        label = sentiment_label_from_score(score)
        excerpt = post.content[:150] + "..." if len(post.content) > 150 else post.content
        return SentimentScore(
            source=post.platform,
            score=score,
            confidence=confidence,
            label=label,
            text_excerpt=excerpt,
            metadata={
                "author": post.author,
                "published_at": post.published_at.isoformat(),
                "likes": str(post.likes),
                "shares": str(post.shares),
                "comments": str(post.comments),
                "followers": str(post.followers),
                "url": post.url,
            },
        )

    def _compute_sentiment_score(self, text: str) -> Decimal:
        """Compute sentiment score from text using keyword analysis."""
        text_lower = text.lower()
        positive_count = sum(1 for kw in self._config.positive_keywords if kw in text_lower)
        negative_count = sum(1 for kw in self._config.negative_keywords if kw in text_lower)
        total = positive_count + negative_count
        if total == 0:
            return Decimal("0")
        raw_score = (positive_count - negative_count) / Decimal(total)
        weighted_score = raw_score * self._config.boost_factor
        return max(Decimal("-1"), min(Decimal("1"), weighted_score))

    def _compute_confidence(self, post: SocialPost, score: Decimal) -> Decimal:
        """Compute confidence score based on engagement, followers, and recency."""
        engagement_score = self._compute_engagement_score(post)
        follower_score = self._compute_follower_score(post)
        recency_score = self._compute_recency_score(post)
        score_magnitude = abs(score)

        weighted_confidence = (
            engagement_score * self._config.engagement_weight
            + follower_score * self._config.follower_weight
            + recency_score * self._config.recency_weight
        )

        final_confidence = (weighted_confidence * Decimal("0.8")) + (
            score_magnitude * Decimal("0.2")
        )
        return max(Decimal("0"), min(Decimal("1"), final_confidence))

    def _compute_engagement_score(self, post: SocialPost) -> Decimal:
        """Compute normalized engagement score."""
        engagement = post.likes + post.shares + post.comments
        if engagement <= self._config.min_engagement:
            return Decimal("0.3")
        max_expected = self._config.min_engagement * 10
        return min(Decimal("1"), Decimal(engagement) / Decimal(max_expected))

    def _compute_follower_score(self, post: SocialPost) -> Decimal:
        """Compute normalized follower score."""
        if post.followers == 0:
            return Decimal("0.3")
        min_followers = 1000
        max_followers = 1000000
        if post.followers < min_followers:
            return Decimal("0.3")
        if post.followers > max_followers:
            return Decimal("1.0")
        return Decimal(post.followers - min_followers) / Decimal(max_followers - min_followers)

    def _compute_recency_score(self, post: SocialPost) -> Decimal:
        """Compute normalized recency score."""
        age_hours = (datetime.now(UTC) - post.published_at).total_seconds() / 3600
        if age_hours >= self._config.max_age_hours:
            return Decimal("0")
        return max(
            Decimal("0"),
            Decimal("1") - (Decimal(age_hours) / Decimal(self._config.max_age_hours)),
        )

    def _aggregate_sentiments(self, sentiments: list[SentimentScore]) -> tuple[Decimal, Decimal]:
        """Aggregate multiple sentiment scores."""
        if not sentiments:
            return Decimal("0"), Decimal("0")

        weighted_sum = Decimal("0")
        total_confidence = Decimal("0")
        for sentiment in sentiments:
            weighted_sum += sentiment.score * sentiment.confidence
            total_confidence += sentiment.confidence

        if total_confidence == Decimal("0"):
            return Decimal("0"), Decimal("0")

        overall_score = weighted_sum / total_confidence
        avg_confidence = total_confidence / Decimal(len(sentiments))
        return overall_score, avg_confidence

    def _empty_result(self, symbol: str) -> SocialSentimentResult:
        """Return empty result for symbol with no posts."""
        return SocialSentimentResult(
            symbol=symbol,
            overall_score=Decimal("0"),
            overall_confidence=Decimal("0"),
            post_count=0,
            total_engagement=0,
            sentiment_label="NEUTRAL",
            posts=[],
            timestamp=datetime.now(UTC),
        )


class MockSocialSource:
    """Mock social media source for testing."""

    def __init__(self, posts: list[SocialPost] | None = None) -> None:
        self._posts = posts or []

    def fetch_posts(self, symbol: str, limit: int = 50) -> list[SocialPost]:
        """Fetch mock posts for a symbol."""
        symbol_posts = [
            p for p in self._posts if symbol in p.symbols or symbol in p.content.lower()
        ]
        return symbol_posts[:limit]

    def add_post(self, post: SocialPost) -> None:
        """Add a post to the mock source."""
        self._posts.append(post)
