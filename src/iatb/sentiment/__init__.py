"""
Sentiment analysis package.
"""

from iatb.sentiment.aggregator import SentimentAggregator, SentimentGateResult
from iatb.sentiment.aion_analyzer import AionAnalyzer
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.finbert_analyzer import FinbertAnalyzer
from iatb.sentiment.news_scraper import NewsHeadline, NewsScraper
from iatb.sentiment.vader_analyzer import VaderAnalyzer
from iatb.sentiment.volume_filter import MIN_VOLUME_RATIO, has_volume_confirmation

__all__ = [
    "AionAnalyzer",
    "FinbertAnalyzer",
    "MIN_VOLUME_RATIO",
    "NewsHeadline",
    "NewsScraper",
    "SentimentAggregator",
    "SentimentAnalyzer",
    "SentimentGateResult",
    "SentimentScore",
    "VaderAnalyzer",
    "has_volume_confirmation",
    "sentiment_label_from_score",
]
