"""
Comprehensive coverage tests for news_scraper.py.

Tests RSS news scraper for Indian financial sources.
"""

from datetime import UTC, datetime

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_scraper import (
    DEFAULT_RSS_FEEDS,
    NewsHeadline,
    NewsScraper,
    _parse_rss_date,
    headlines_to_articles,
)


class TestNewsHeadline:
    """Test news headline dataclass."""

    def test_create_headline(self):
        """Test creating news headline."""
        headline = NewsHeadline(
            source="Test Source",
            title="Test Title",
            url="https://example.com",
            published="Mon, 01 Jan 2024 12:00:00 GMT",
            article_text="Test content",
        )

        assert headline.source == "Test Source"
        assert headline.title == "Test Title"


class TestParseRSSDate:
    """Test RSS date parsing."""

    def test_parse_rfc2822_date(self):
        """Test parsing RFC 2822 date format."""
        date_str = "Mon, 01 Jan 2024 12:00:00 GMT"
        result = _parse_rss_date(date_str)

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_iso_date(self):
        """Test parsing ISO date format."""
        date_str = "2024-01-01T12:00:00Z"
        result = _parse_rss_date(date_str)

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_empty_date_returns_now(self):
        """Test that empty date returns current UTC time."""
        result = _parse_rss_date("")

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_invalid_date_returns_now(self):
        """Test that invalid date returns current UTC time."""
        result = _parse_rss_date("invalid-date")

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC


class TestHeadlinesToArticles:
    """Test converting headlines to articles."""

    def test_convert_single_headline(self):
        """Test converting single headline to article."""
        headlines = [
            NewsHeadline(
                source="Test",
                title="Test Title",
                url="https://example.com",
                published="Mon, 01 Jan 2024 12:00:00 GMT",
                article_text="Test content",
            )
        ]

        articles = headlines_to_articles(headlines)

        assert len(articles) == 1
        assert articles[0].title == "Test Title"
        assert articles[0].symbols == []

    def test_convert_multiple_headlines(self):
        """Test converting multiple headlines to articles."""
        headlines = [
            NewsHeadline(
                source="Test1",
                title="Title1",
                url="https://example1.com",
                published="Mon, 01 Jan 2024 12:00:00 GMT",
                article_text="Content1",
            ),
            NewsHeadline(
                source="Test2",
                title="Title2",
                url="https://example2.com",
                published="Mon, 01 Jan 2024 13:00:00 GMT",
                article_text="Content2",
            ),
        ]

        articles = headlines_to_articles(headlines)

        assert len(articles) == 2
        assert articles[0].title == "Title1"
        assert articles[1].title == "Title2"

    def test_headline_without_article_text_uses_title(self):
        """Test that headline without article text uses title as content."""
        headlines = [
            NewsHeadline(
                source="Test",
                title="Title Only",
                url="https://example.com",
                published="Mon, 01 Jan 2024 12:00:00 GMT",
                article_text="",
            )
        ]

        articles = headlines_to_articles(headlines)

        assert articles[0].content == "Title Only"


class TestNewsScraper:
    """Test news scraper."""

    def test_create_scraper_with_defaults(self):
        """Test creating scraper with default settings."""
        scraper = NewsScraper()

        assert scraper is not None
        assert scraper._rate_limit_seconds == 1.0

    def test_create_scraper_custom_rate_limit(self):
        """Test creating scraper with custom rate limit."""
        scraper = NewsScraper(rate_limit_seconds=2.0)

        assert scraper._rate_limit_seconds == 2.0

    def test_negative_rate_limit_raises_error(self):
        """Test that negative rate limit raises ConfigError."""
        with pytest.raises(ConfigError, match="rate_limit_seconds cannot be negative"):
            NewsScraper(rate_limit_seconds=-1.0)

    def test_create_scraper_custom_feeds(self):
        """Test creating scraper with custom RSS feeds."""
        custom_feeds = {"custom": "https://example.com/feed.xml"}
        scraper = NewsScraper(rss_feeds=custom_feeds)

        assert scraper._rss_feeds == custom_feeds

    def test_fetch_headlines_invalid_max_items_raises_error(self):
        """Test that invalid max_items raises ConfigError."""
        scraper = NewsScraper()

        with pytest.raises(ConfigError, match="max_items_per_feed must be positive"):
            scraper.fetch_headlines(max_items_per_feed=0)

    def test_default_rss_feeds_not_empty(self):
        """Test that default RSS feeds are not empty."""
        assert len(DEFAULT_RSS_FEEDS) > 0
        assert "moneycontrol" in DEFAULT_RSS_FEEDS
        assert "et_markets" in DEFAULT_RSS_FEEDS
