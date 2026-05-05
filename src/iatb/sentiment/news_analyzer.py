"""
News sentiment analyzer for financial instruments.

Analyzes news articles and headlines to extract sentiment scores
for trading instruments using NLP techniques.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore, sentiment_label_from_score

if TYPE_CHECKING:
    from iatb.sentiment.news_scraper import NewsHeadline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsArticle:
    """Represents a news article."""

    title: str
    content: str
    source: str
    published_at: datetime
    url: str = ""
    symbols: list[str] = field(default_factory=list)
    author: str = ""
    relevance_score: Decimal = Decimal("1.0")


@dataclass
class NewsAnalyzerConfig:
    """Configuration for news sentiment analyzer."""

    min_relevance: Decimal = Decimal("0.5")
    max_age_hours: int = 24
    positive_keywords: list[str] = field(
        default_factory=lambda: [
            "strong",
            "growth",
            "profit",
            "beat",
            "upgrade",
            "bullish",
            "rally",
            "surge",
            "outperform",
            "positive",
            "gain",
            "rally",
            "strength",
            "expansion",
            "record",
            "high",
            "optimistic",
            "opportunity",
            "success",
        ]
    )
    negative_keywords: list[str] = field(
        default_factory=lambda: [
            "weak",
            "decline",
            "loss",
            "miss",
            "downgrade",
            "bearish",
            "drop",
            "fall",
            "underperform",
            "negative",
            "risk",
            "concern",
            "worry",
            "plunge",
            "crash",
            "struggle",
            "pessimistic",
            "threat",
            "failure",
        ]
    )
    boost_factor: Decimal = Decimal("1.0")
    decay_hours: int = 6

    def __post_init__(self) -> None:
        if self.min_relevance < Decimal("0") or self.min_relevance > Decimal("1"):
            msg = "min_relevance must be in [0, 1]"
            raise ConfigError(msg)
        if self.max_age_hours < 0:
            msg = "max_age_hours cannot be negative"
            raise ConfigError(msg)
        if self.boost_factor < Decimal("0"):
            msg = "boost_factor cannot be negative"
            raise ConfigError(msg)
        if self.decay_hours < 0:
            msg = "decay_hours cannot be negative"
            raise ConfigError(msg)


@dataclass(frozen=True)
class NewsSentimentResult:
    """Result of news sentiment analysis."""

    symbol: str
    overall_score: Decimal
    overall_confidence: Decimal
    article_count: int
    sentiment_label: str
    articles: list[SentimentScore]
    timestamp: datetime


@runtime_checkable
class NewsSource(Protocol):
    """Protocol for news data sources."""

    def fetch_articles(self, symbol: str, limit: int = 10) -> list[NewsArticle]:
        """Fetch news articles for a symbol."""
        ...


class NewsAnalyzer:
    """Analyzes news sentiment for financial instruments."""

    def __init__(self, config: NewsAnalyzerConfig | None = None) -> None:
        self._config = config or NewsAnalyzerConfig()

    def analyze(self, articles: list[NewsArticle], symbol: str) -> NewsSentimentResult:
        """Analyze news articles for a symbol."""
        if not articles:
            logger.debug("No articles provided for %s", symbol)
            return self._empty_result(symbol)

        filtered = self._filter_articles(articles, symbol)
        if not filtered:
            logger.debug("No relevant articles for %s", symbol)
            return self._empty_result(symbol)

        sentiments = [self._analyze_article(article, symbol) for article in filtered]
        overall_score, overall_confidence = self._aggregate_sentiments(sentiments)
        sentiment_label = sentiment_label_from_score(overall_score)

        logger.info(
            "Analyzed %d articles for %s: score=%.2f, label=%s",
            len(filtered),
            symbol,
            overall_score,
            sentiment_label,
        )

        return NewsSentimentResult(
            symbol=symbol,
            overall_score=overall_score,
            overall_confidence=overall_confidence,
            article_count=len(filtered),
            sentiment_label=sentiment_label,
            articles=sentiments,
            timestamp=datetime.now(UTC),
        )

    def analyze_headlines(
        self,
        headlines: list["NewsHeadline"],
        symbol: str,
    ) -> NewsSentimentResult:
        """Convert NewsHeadline objects to NewsArticle and analyze.

        Provides a direct bridge from NewsScraper.fetch_headlines()
        output to NewsAnalyzer analysis.

        Args:
            headlines: List of NewsHeadline from NewsScraper.
            symbol: The financial instrument symbol.

        Returns:
            NewsSentimentResult with aggregated sentiment.
        """
        from iatb.sentiment.news_scraper import headlines_to_articles

        articles = headlines_to_articles(headlines)
        return self.analyze(articles, symbol)

    def analyze_batch(
        self, articles_by_symbol: dict[str, list[NewsArticle]]
    ) -> dict[str, NewsSentimentResult]:
        """Analyze news for multiple symbols."""
        results: dict[str, NewsSentimentResult] = {}
        for symbol, articles in articles_by_symbol.items():
            results[symbol] = self.analyze(articles, symbol)
        logger.info("Analyzed news for %d symbols", len(results))
        return results

    def _filter_articles(self, articles: list[NewsArticle], symbol: str) -> list[NewsArticle]:
        """Filter articles by relevance and age."""
        now = datetime.now(UTC)
        filtered: list[NewsArticle] = []
        for article in articles:
            if article.relevance_score < self._config.min_relevance:
                continue
            age_hours = (now - article.published_at).total_seconds() / 3600
            if age_hours > self._config.max_age_hours:
                continue
            if symbol not in article.symbols and symbol.lower() not in article.title.lower():
                continue
            filtered.append(article)
        return filtered

    def _analyze_article(self, article: NewsArticle, symbol: str) -> SentimentScore:
        """Analyze sentiment of a single article."""
        text = f"{article.title}. {article.content}"
        score = self._compute_sentiment_score(text)
        confidence = self._compute_confidence(article, score)
        label = sentiment_label_from_score(score)
        excerpt = text[:200] + "..." if len(text) > 200 else text
        return SentimentScore(
            source=article.source,
            score=score,
            confidence=confidence,
            label=label,
            text_excerpt=excerpt,
            metadata={
                "published_at": article.published_at.isoformat(),
                "url": article.url,
                "author": article.author,
                "relevance": str(article.relevance_score),
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

    def _compute_confidence(self, article: NewsArticle, score: Decimal) -> Decimal:
        """Compute confidence score for the sentiment."""
        age_hours = (datetime.now(UTC) - article.published_at).total_seconds() / 3600
        time_decay = max(
            Decimal("0"),
            Decimal("1") - (Decimal(age_hours) / Decimal(self._config.max_age_hours)),
        )
        relevance_weight = article.relevance_score
        score_magnitude = abs(score)
        base_confidence = (
            (time_decay * Decimal("0.4"))
            + (relevance_weight * Decimal("0.4"))
            + (score_magnitude * Decimal("0.2"))
        )
        return max(Decimal("0"), min(Decimal("1"), base_confidence))

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

    def _empty_result(self, symbol: str) -> NewsSentimentResult:
        """Return empty result for symbol with no articles."""
        return NewsSentimentResult(
            symbol=symbol,
            overall_score=Decimal("0"),
            overall_confidence=Decimal("0"),
            article_count=0,
            sentiment_label="NEUTRAL",
            articles=[],
            timestamp=datetime.now(UTC),
        )


class MockNewsSource:
    """Mock news source for testing."""

    def __init__(self, articles: list[NewsArticle] | None = None) -> None:
        self._articles = articles or []

    def fetch_articles(self, symbol: str, limit: int = 10) -> list[NewsArticle]:
        """Fetch mock articles for a symbol."""
        symbol_articles = [
            a for a in self._articles if symbol in a.symbols or symbol in a.title.lower()
        ]
        return symbol_articles[:limit]

    def add_article(self, article: NewsArticle) -> None:
        """Add an article to the mock source."""
        self._articles.append(article)
