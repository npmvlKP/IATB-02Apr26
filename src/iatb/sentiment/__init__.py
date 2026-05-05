"""
Sentiment analysis package.
"""

from iatb.sentiment.aggregator import SentimentAggregator, SentimentGateResult
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer
from iatb.sentiment.news_analyzer import NewsAnalyzer, NewsArticle, NewsSentimentResult
from iatb.sentiment.news_scraper import NewsHeadline, NewsScraper, headlines_to_articles
from iatb.sentiment.recency_weighting import recency_weighted_score
from iatb.sentiment.social_sentiment import (
    MockSocialSource,
    SocialPost,
    SocialSentimentAnalyzer,
    SocialSentimentConfig,
)
from iatb.sentiment.vader_analyzer import VaderAnalyzer
from iatb.sentiment.volume_filter import MIN_VOLUME_RATIO, has_volume_confirmation

__all__ = [
    "AionAnalyzer",
    "FinbertAnalyzer",
    "MIN_VOLUME_RATIO",
    "MockSocialSource",
    "NewsAnalyzer",
    "NewsArticle",
    "NewsHeadline",
    "NewsScraper",
    "NewsSentimentResult",
    "SentimentAggregator",
    "SentimentAnalyzer",
    "SentimentGateResult",
    "SentimentScore",
    "SocialPost",
    "SocialSentimentAnalyzer",
    "SocialSentimentConfig",
    "VaderAnalyzer",
    "has_volume_confirmation",
    "headlines_to_articles",
    "recency_weighted_score",
    "sentiment_label_from_score",
]
