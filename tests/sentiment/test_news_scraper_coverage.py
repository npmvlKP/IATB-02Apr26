"""Tests for sentiment/news_scraper.py — headline scraping."""

from datetime import UTC
from unittest.mock import patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_scraper import (
    NewsHeadline,
    NewsScraper,
    _default_article_extractor,
    _default_fetcher,
    _parse_rss_date,
    headlines_to_articles,
)


class TestNewsHeadline:
    def test_creation(self) -> None:
        h = NewsHeadline(
            source="test",
            title="Test Title",
            url="https://example.com",
            published="Mon, 01 Jan 2024 10:00:00 GMT",
            article_text="Body",
        )
        assert h.source == "test"
        assert h.title == "Test Title"


class TestParseRssDate:
    def test_rfc2822_format(self) -> None:
        result = _parse_rss_date("Mon, 01 Jan 2024 10:00:00 GMT")
        assert result.tzinfo is not None

    def test_empty_string_returns_now(self) -> None:
        result = _parse_rss_date("")
        assert result.tzinfo == UTC

    def test_iso_format(self) -> None:
        result = _parse_rss_date("2024-01-01T10:00:00+00:00")
        assert result.tzinfo is not None

    def test_invalid_format_returns_now(self) -> None:
        result = _parse_rss_date("not-a-date")
        assert result.tzinfo == UTC


class TestHeadlinesToArticles:
    def test_converts_to_articles(self) -> None:
        headlines = [
            NewsHeadline(
                source="test",
                title="Title",
                url="https://example.com",
                published="Mon, 01 Jan 2024 10:00:00 GMT",
                article_text="Body",
            ),
        ]
        articles = headlines_to_articles(headlines)
        assert len(articles) == 1
        assert articles[0].title == "Title"

    def test_empty_headlines(self) -> None:
        assert headlines_to_articles([]) == []

    def test_fallback_to_title_when_no_article_text(self) -> None:
        headlines = [
            NewsHeadline(
                source="test",
                title="Title Only",
                url="https://example.com",
                published="Mon, 01 Jan 2024 10:00:00 GMT",
                article_text="",
            ),
        ]
        articles = headlines_to_articles(headlines)
        assert articles[0].content == "Title Only"


class TestNewsScraper:
    def test_negative_rate_limit_raises(self) -> None:
        with pytest.raises(ConfigError, match="rate_limit_seconds cannot be negative"):
            NewsScraper(rate_limit_seconds=-1.0)

    def test_zero_max_items_raises(self) -> None:
        scraper = NewsScraper(fetcher=lambda _url: "", sleep_func=lambda _s: None)
        with pytest.raises(ConfigError, match="max_items_per_feed must be positive"):
            scraper.fetch_headlines(max_items_per_feed=0)

    def test_fetch_with_mock(self) -> None:
        rss_xml = '<?xml version="1.0"?><rss><channel><item><title>Test</title><link>https://example.com</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item></channel></rss>'
        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed"},
            fetcher=lambda _url: rss_xml,
            article_extractor=lambda _url: "Extracted text",
            sleep_func=lambda _s: None,
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=5)
        assert len(headlines) >= 1
        assert headlines[0].title == "Test"

    def test_invalid_xml_raises(self) -> None:
        scraper = NewsScraper(
            rss_feeds={"test": "https://example.com/feed"},
            fetcher=lambda _url: "not-xml",
            sleep_func=lambda _s: None,
        )
        with pytest.raises(ConfigError, match="Invalid RSS"):
            scraper.fetch_headlines(max_items_per_feed=5)

    def test_multiple_feeds(self) -> None:
        rss_xml = '<?xml version="1.0"?><rss><channel><item><title>Test</title><link>https://example.com</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item></channel></rss>'
        scraper = NewsScraper(
            rss_feeds={"a": "https://a.com/feed", "b": "https://b.com/feed"},
            fetcher=lambda _url: rss_xml,
            article_extractor=lambda _url: "text",
            sleep_func=lambda _s: None,
        )
        headlines = scraper.fetch_headlines(max_items_per_feed=1)
        assert len(headlines) >= 2

    def test_resolve_link_atom(self) -> None:
        from xml.etree import ElementTree

        xml = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Test</title><link href="https://example.com/article"/><published>2024-01-01T10:00:00Z</published></entry></feed>'
        root = ElementTree.fromstring(xml)
        _scraper = NewsScraper(
            fetcher=lambda _url: "",
            sleep_func=lambda _s: None,
        )
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        if entry is not None:
            link = NewsScraper._resolve_link(entry)
            assert isinstance(link, str)

    def test_raises_without_network(self) -> None:
        with patch(
            "urllib.request.urlopen", side_effect=Exception("no network")
        ), pytest.raises(Exception, match="no network"):
            _default_fetcher("https://example.com")

    def test_missing_newspaper_raises(self) -> None:
        with patch(
            "importlib.import_module", side_effect=ModuleNotFoundError
        ), pytest.raises(ConfigError, match="newspaper3k dependency"):
            _default_article_extractor("https://example.com")
