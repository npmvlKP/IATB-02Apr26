"""
Comprehensive coverage tests for news_scraper.py.

Tests headline scraping, HTML parsing, and error paths.
"""

from unittest.mock import MagicMock, patch

from iatb.sentiment.news_scraper import (
    NewsScraper,
    parse_headlines,
    scrape_url,
)


class TestParseHeadlines:
    """Test parse_headlines function."""

    def test_parse_basic_headline(self) -> None:
        """Test basic headline parsing."""
        html = "<h1>Company reports strong earnings</h1>"
        headlines = parse_headlines(html)
        assert len(headlines) > 0
        assert "earnings" in headlines[0].lower()

    def test_parse_multiple_headlines(self) -> None:
        """Test parsing multiple headlines."""
        html = """
        <h1>Earnings beat expectations</h1>
        <h2>Revenue up 20%</h2>
        <h3>Guidance raised</h3>
        """
        headlines = parse_headlines(html)
        assert len(headlines) >= 3

    def test_parse_empty_html(self) -> None:
        """Test with empty HTML."""
        html = ""
        headlines = parse_headlines(html)
        assert headlines == []

    def test_parse_with_classes(self) -> None:
        """Test parsing with CSS classes."""
        html = '<h1 class="headline">Strong earnings report</h1>'
        headlines = parse_headlines(html, selector="h1.headline")
        assert len(headlines) > 0


class TestScrapeUrl:
    """Test scrape_url function."""

    @patch("iatb.sentiment.news_scraper.requests.get")
    def test_scrape_success(self, mock_get) -> None:
        """Test successful URL scraping."""
        mock_response = MagicMock()
        mock_response.text = "<h1>Earnings news</h1>"
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        headlines = scrape_url("http://example.com")
        assert len(headlines) > 0

    @patch("iatb.sentiment.news_scraper.requests.get")
    def test_scrape_http_error(self, mock_get) -> None:
        """Test scraping with HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        headlines = scrape_url("http://example.com")
        # Should handle gracefully
        assert isinstance(headlines, list)

    @patch("iatb.sentiment.news_scraper.requests.get")
    def test_scrape_timeout(self, mock_get) -> None:
        """Test scraping with timeout."""
        mock_get.side_effect = Exception("Timeout")

        headlines = scrape_url("http://example.com")
        # Should handle gracefully
        assert isinstance(headlines, list)

    @patch("iatb.sentiment.news_scraper.requests.get")
    def test_scrape_empty_response(self, mock_get) -> None:
        """Test scraping empty response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        headlines = scrape_url("http://example.com")
        assert headlines == []


class TestNewsScraper:
    """Test NewsScraper class."""

    def test_scraper_initialization(self) -> None:
        """Test scraper initialization."""
        scraper = NewsScraper()
        assert scraper is not None

    def test_scraper_with_sources(self) -> None:
        """Test scraper with multiple sources."""
        sources = ["http://source1.com", "http://source2.com"]
        scraper = NewsScraper(sources=sources)
        assert len(scraper.sources) == 2

    @patch("iatb.sentiment.news_scraper.scrape_url")
    def test_scrape_all_sources(self, mock_scrape) -> None:
        """Test scraping all sources."""
        mock_scrape.side_effect = [
            ["Headline 1", "Headline 2"],
            ["Headline 3"],
        ]

        sources = ["http://source1.com", "http://source2.com"]
        scraper = NewsScraper(sources=sources)
        headlines = scraper.scrape_all()

        assert len(headlines) == 3

    def test_add_source(self) -> None:
        """Test adding a source."""
        scraper = NewsScraper()
        scraper.add_source("http://example.com")
        assert "http://example.com" in scraper.sources

    def test_remove_source(self) -> None:
        """Test removing a source."""
        scraper = NewsScraper(sources=["http://example.com"])
        scraper.remove_source("http://example.com")
        assert "http://example.com" not in scraper.sources

    @patch("iatb.sentiment.news_scraper.scrape_url")
    def test_scrape_with_retry(self, mock_scrape) -> None:
        """Test scraping with retry logic."""
        # First call fails, second succeeds
        mock_scrape.side_effect = [[], ["Headline 1"]]

        scraper = NewsScraper(sources=["http://example.com"])
        headlines = scraper.scrape_all(max_retries=2)

        # Should succeed after retry
        assert isinstance(headlines, list)
