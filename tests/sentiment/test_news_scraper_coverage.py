"""
Comprehensive coverage tests for news_scraper.py.

Tests RSS news scraping, date parsing, and error paths.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_scraper import (
    DEFAULT_RSS_FEEDS,
    NewsHeadline,
    NewsScraper,
    _parse_rss_date,
    headlines_to_articles,
)


class TestParseRssDate:
    """Test _parse_rss_date function."""

    def test_parse_rfc2822_date(self) -> None:
        """Test parsing RFC 2822 date format."""
        date_str = "Mon, 01 Jan 2024 12:00:00 +0000"
        result = _parse_rss_date(date_str)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_iso8601_date(self) -> None:
        """Test parsing ISO 8601 date format."""
        date_str = "2024-01-01T12:00:00Z"
        result = _parse_rss_date(date_str)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_naive_datetime(self) -> None:
        """Test parsing naive datetime (no timezone)."""
        date_str = "Mon, 01 Jan 2024 12:00:00"
        result = _parse_rss_date(date_str)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_empty_string_returns_now(self) -> None:
        """Test empty string returns current UTC time."""
        result = _parse_rss_date("")
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_invalid_date_returns_now(self) -> None:
        """Test invalid date string returns current UTC time."""
        result = _parse_rss_date("invalid date")
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_parse_iso_format_with_timezone(self) -> None:
        """Test ISO format with timezone."""
        date_str = "2024-01-01T12:00:00+05:30"
        result = _parse_rss_date(date_str)
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC


class TestNewsScraper:
    """Test NewsScraper class."""

    def test_scraper_initialization(self) -> None:
        """Test scraper initialization."""
        scraper = NewsScraper()
        assert scraper is not None

    def test_scraper_with_custom_feeds(self) -> None:
        """Test scraper with custom RSS feeds."""
        custom_feeds = {
            "test": "https://example.com/feed.xml",
        }
        scraper = NewsScraper(rss_feeds=custom_feeds)
        assert scraper is not None

    def test_scraper_with_custom_rate_limit(self) -> None:
        """Test scraper with custom rate limit."""
        scraper = NewsScraper(rate_limit_seconds=2.0)
        assert scraper is not None

    def test_rate_limit_negative_raises_error(self) -> None:
        """Test negative rate limit raises ConfigError."""
        with pytest.raises(ConfigError, match="rate_limit_seconds cannot be negative"):
            NewsScraper(rate_limit_seconds=-1.0)

    def test_max_items_per_feed_negative_raises_error(self) -> None:
        """Test negative max_items_per_feed raises ConfigError."""
        scraper = NewsScraper()
        with pytest.raises(ConfigError, match="max_items_per_feed must be positive"):
            scraper.fetch_headlines(max_items_per_feed=-1)

    def test_max_items_per_feed_zero_raises_error(self) -> None:
        """Test zero max_items_per_feed raises ConfigError."""
        scraper = NewsScraper()
        with pytest.raises(ConfigError, match="max_items_per_feed must be positive"):
            scraper.fetch_headlines(max_items_per_feed=0)


class TestNewsScraperWithMockFetcher:
    """Test NewsScraper with mocked fetcher."""

    def test_fetch_headlines_with_valid_rss(self) -> None:
        """Test fetching headlines with valid RSS XML."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Test Article</title>
      <link>https://example.com/article1</link>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <description>Test content</description>
    </item>
  </channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)

        assert len(headlines) == 1
        assert headlines[0].title == "Test Article"
        assert headlines[0].source == "test"

    def test_fetch_headlines_with_atom_feed(self) -> None:
        """Test fetching headlines with Atom feed."""
        mock_atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Feed</title>
  <entry>
    <title>Test Article</title>
    <link href="https://example.com/article1"/>
    <published>2024-01-01T12:00:00Z</published>
    <content>Test content</content>
  </entry>
</feed>
"""

        def mock_fetcher(url: str) -> str:
            return mock_atom

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)

        assert len(headlines) == 1
        assert headlines[0].title == "Test Article"

    def test_fetch_headlines_with_multiple_items(self) -> None:
        """Test fetching headlines with multiple items."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Article 1</title>
      <link>https://example.com/article1</link>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
      <description>Content 1</description>
    </item>
    <item>
      <title>Article 2</title>
      <link>https://example.com/article2</link>
      <pubDate>Mon, 01 Jan 2024 13:00:00 GMT</pubDate>
      <description>Content 2</description>
    </item>
  </channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)

        assert len(headlines) == 2

    def test_fetch_headlines_respects_limit(self) -> None:
        """Test max_items_per_feed limit is respected."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item><title>1</title><link>https://1</link><pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate></item>
    <item><title>2</title><link>https://2</link><pubDate>Mon, 01 Jan 2024 13:00:00 GMT</pubDate></item>
    <item><title>3</title><link>https://3</link><pubDate>Mon, 01 Jan 2024 14:00:00 GMT</pubDate></item>
    <item><title>4</title><link>https://4</link><pubDate>Mon, 01 Jan 2024 15:00:00 GMT</pubDate></item>
    <item><title>5</title><link>https://5</link><pubDate>Mon, 01 Jan 2024 16:00:00 GMT</pubDate></item>
    <item><title>6</title><link>https://6</link><pubDate>Mon, 01 Jan 2024 17:00:00 GMT</pubDate></item>
  </channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=3)

        assert len(headlines) == 3

    def test_fetch_headlines_with_empty_feed(self) -> None:
        """Test fetching headlines with empty feed."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
  </channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)

        assert len(headlines) == 0

    def test_fetch_headlines_with_invalid_xml_raises_error(self) -> None:
        """Test invalid XML raises ConfigError."""
        invalid_xml = "This is not valid XML"

        def mock_fetcher(url: str) -> str:
            return invalid_xml

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        with pytest.raises(ConfigError, match="Invalid RSS payload"):
            scraper.fetch_headlines(max_items_per_feed=5)

    def test_fetch_headlines_missing_fields(self) -> None:
        """Test headlines with missing fields."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <link>https://example.com/article</link>
    </item>
  </channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed.xml"}, fetcher=mock_fetcher
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)

        # Should still create headline with defaults
        assert len(headlines) == 1
        assert headlines[0].title == "UNTITLED"

    def test_rate_limiting_between_feeds(self) -> None:
        """Test rate limiting between multiple feeds."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel><item><title>Test</title><link>https://test</link></item></channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        sleep_calls = []

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        scraper = NewsScraper(
            rss_feeds={
                "feed1": "https://feed1.xml",
                "feed2": "https://feed2.xml",
            },
            fetcher=mock_fetcher,
            sleep_func=mock_sleep,
            rate_limit_seconds=1.0,
        )

        _headlines = scraper.fetch_headlines(max_items_per_feed=5)

        # Should sleep once between feeds
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == 1.0

    def test_no_sleep_for_last_feed(self) -> None:
        """Test no sleep after last feed."""
        mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel><item><title>Test</title><link>https://test</link></item></channel>
</rss>
"""

        def mock_fetcher(url: str) -> str:
            return mock_rss

        sleep_calls = []

        def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        scraper = NewsScraper(
            rss_feeds={"feed1": "https://feed1.xml"},
            fetcher=mock_fetcher,
            sleep_func=mock_sleep,
            rate_limit_seconds=1.0,
        )

        _headlines = scraper.fetch_headlines(max_items_per_feed=5)

        # Should not sleep after single feed
        assert len(sleep_calls) == 0


class TestNewsHeadline:
    """Test NewsHeadline dataclass."""

    def test_create_headline(self) -> None:
        """Test creating a news headline."""
        headline = NewsHeadline(
            source="test",
            title="Test Article",
            url="https://example.com/article",
            published="2024-01-01T12:00:00Z",
            article_text="Test content",
        )
        assert headline.source == "test"
        assert headline.title == "Test Article"
        assert headline.url == "https://example.com/article"


class TestHeadlinesToArticles:
    """Test headlines_to_articles function."""

    def test_convert_single_headline(self) -> None:
        """Test converting single headline to article."""
        headlines = [
            NewsHeadline(
                source="test",
                title="Test Article",
                url="https://example.com/article",
                published="2024-01-01T12:00:00Z",
                article_text="Test content",
            )
        ]
        articles = headlines_to_articles(headlines)

        assert len(articles) == 1
        assert articles[0].title == "Test Article"
        assert articles[0].content == "Test content"

    def test_convert_multiple_headlines(self) -> None:
        """Test converting multiple headlines."""
        headlines = [
            NewsHeadline(
                source="test1",
                title="Article 1",
                url="https://example.com/article1",
                published="2024-01-01T12:00:00Z",
                article_text="Content 1",
            ),
            NewsHeadline(
                source="test2",
                title="Article 2",
                url="https://example.com/article2",
                published="2024-01-01T13:00:00Z",
                article_text="Content 2",
            ),
        ]
        articles = headlines_to_articles(headlines)

        assert len(articles) == 2
        assert articles[0].title == "Article 1"
        assert articles[1].title == "Article 2"

    def test_convert_empty_list(self) -> None:
        """Test converting empty list."""
        articles = headlines_to_articles([])
        assert len(articles) == 0

    def test_fallback_to_title_when_content_empty(self) -> None:
        """Test using title when article_text is empty."""
        headlines = [
            NewsHeadline(
                source="test",
                title="Test Article",
                url="https://example.com/article",
                published="2024-01-01T12:00:00Z",
                article_text="",  # Empty
            )
        ]
        articles = headlines_to_articles(headlines)

        assert len(articles) == 1
        # Should use title as content
        assert articles[0].content == "Test Article"

    def test_article_datetime_parsed(self) -> None:
        """Test datetime is parsed from published string."""
        headlines = [
            NewsHeadline(
                source="test",
                title="Test Article",
                url="https://example.com/article",
                published="2024-01-01T12:00:00Z",
                article_text="Test content",
            )
        ]
        articles = headlines_to_articles(headlines)

        assert articles[0].published_at.tzinfo == UTC

    def test_article_default_values(self) -> None:
        """Test articles get default values."""
        headlines = [
            NewsHeadline(
                source="test",
                title="Test Article",
                url="https://example.com/article",
                published="2024-01-01T12:00:00Z",
                article_text="Test content",
            )
        ]
        articles = headlines_to_articles(headlines)

        assert articles[0].author == ""
        assert articles[0].symbols == []
        assert articles[0].relevance_score == Decimal("1.0")


class TestDefaultRssFeeds:
    """Test DEFAULT_RSS_FEEDS constant."""

    def test_default_feeds_is_dict(self) -> None:
        """Test DEFAULT_RSS_FEEDS is a dictionary."""
        assert isinstance(DEFAULT_RSS_FEEDS, dict)

    def test_default_feeds_not_empty(self) -> None:
        """Test DEFAULT_RSS_FEEDS is not empty."""
        assert len(DEFAULT_RSS_FEEDS) > 0

    def test_default_feed_values_are_strings(self) -> None:
        """Test all default feed values are strings."""
        for name, url in DEFAULT_RSS_FEEDS.items():
            assert isinstance(name, str)
            assert isinstance(url, str)
            assert url.startswith("http")


class TestArticleExtractionErrorHandling:
    """Test article extraction error handling."""

    def test_safe_extract_article_with_empty_url(self) -> None:
        """Test safe extraction with empty URL."""
        scraper = NewsScraper()
        # Should not raise error, just return fallback
        result = scraper._safe_extract_article("", "fallback text")
        assert result == "fallback text"

    def test_safe_extract_article_with_extraction_error(self) -> None:
        """Test safe extraction handles extraction errors."""

        def mock_extractor(url: str) -> str:
            raise Exception("Extraction failed")

        scraper = NewsScraper(article_extractor=mock_extractor)
        result = scraper._safe_extract_article("https://example.com", "fallback text")

        # Should return fallback on error
        assert result == "fallback text"
