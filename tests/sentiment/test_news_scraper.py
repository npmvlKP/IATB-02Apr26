from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.news_scraper import (
    NewsScraper,
    _default_article_extractor,
    _default_fetcher,
)

_RSS_MONEYC = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Sensex jumps 500 points on banking rally</title>
    <link>https://moneycontrol.example/news1</link>
    <pubDate>Fri, 03 Apr 2026 08:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""

_ATOM_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Bank Nifty extends gains as PSU banks rally</title>
    <link href="https://atom.example/news3"/>
    <updated>2026-04-03T08:10:00Z</updated>
  </entry>
</feed>
"""

_RSS_NO_LINK = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Midcaps consolidate after volatile open</title>
    <pubDate>Fri, 03 Apr 2026 08:20:00 GMT</pubDate>
  </item>
</channel></rss>
"""

_RSS_ET = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Nifty IT slips as rupee strengthens</title>
    <link>https://etmarkets.example/news2</link>
    <pubDate>Fri, 03 Apr 2026 08:05:00 GMT</pubDate>
  </item>
</channel></rss>
"""


def test_news_scraper_fetches_headlines_with_rate_limit() -> None:
    sleep_calls: list[float] = []
    feeds = {"moneycontrol": "mc", "et_markets": "et"}
    payloads = {"mc": _RSS_MONEYC, "et": _RSS_ET}
    scraper = NewsScraper(
        rss_feeds=feeds,
        rate_limit_seconds=0.5,
        fetcher=lambda url: payloads[url],
        article_extractor=lambda url: f"article:{url}",
        sleep_func=lambda seconds: sleep_calls.append(seconds),
    )
    headlines = scraper.fetch_headlines(max_items_per_feed=1)
    assert len(headlines) == 2
    assert "Sensex jumps" in headlines[0].title
    assert "Nifty IT slips" in headlines[1].title
    assert sleep_calls == [0.5]


def test_news_scraper_fallbacks_when_article_extract_fails() -> None:
    scraper = NewsScraper(
        rss_feeds={"moneycontrol": "mc"},
        fetcher=lambda url: _RSS_MONEYC,
        article_extractor=lambda url: (_ for _ in ()).throw(RuntimeError("boom")),
        sleep_func=lambda seconds: None,
    )
    headlines = scraper.fetch_headlines(max_items_per_feed=1)
    assert headlines[0].article_text == headlines[0].title


def test_news_scraper_rejects_bad_rss_payload() -> None:
    scraper = NewsScraper(
        rss_feeds={"nse_announcements": "nse"},
        fetcher=lambda url: "<rss><broken>",
        article_extractor=lambda url: "",
        sleep_func=lambda seconds: None,
    )
    with pytest.raises(ConfigError, match="Invalid RSS payload"):
        scraper.fetch_headlines(max_items_per_feed=1)


def test_news_scraper_rejects_invalid_limits() -> None:
    scraper = NewsScraper(
        rss_feeds={"moneycontrol": "mc"},
        fetcher=lambda url: _RSS_MONEYC,
        article_extractor=lambda url: "",
        sleep_func=lambda seconds: None,
    )
    with pytest.raises(ConfigError, match="must be positive"):
        scraper.fetch_headlines(max_items_per_feed=0)


def test_news_scraper_rejects_negative_rate_limit() -> None:
    with pytest.raises(ConfigError, match="cannot be negative"):
        NewsScraper(
            rss_feeds={"moneycontrol": "mc"},
            rate_limit_seconds=-0.1,
            fetcher=lambda url: _RSS_MONEYC,
            article_extractor=lambda url: "",
            sleep_func=lambda seconds: None,
        )


def test_default_fetcher_decodes_response_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            _ = (exc_type, exc, tb)

        def read(self) -> bytes:
            return b"<rss/>"

    monkeypatch.setattr(
        "iatb.sentiment.news_scraper.urllib.request.urlopen",
        lambda request, timeout: _Response(),
    )
    assert _default_fetcher("https://example.com/feed.xml") == "<rss/>"


def test_default_article_extractor_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.news_scraper.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="newspaper3k dependency"):
        _default_article_extractor("https://example.com/news")


def test_default_article_extractor_missing_article_class_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.sentiment.news_scraper.importlib.import_module",
        lambda _: SimpleNamespace(),
    )
    with pytest.raises(ConfigError, match="Article is unavailable"):
        _default_article_extractor("https://example.com/news")


def test_default_article_extractor_returns_parsed_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Article:
        def __init__(self, url: str) -> None:
            self._url = url
            self.text = "  India VIX cools after RBI commentary.  "

        def download(self) -> None:
            return None

        def parse(self) -> None:
            return None

    monkeypatch.setattr(
        "iatb.sentiment.news_scraper.importlib.import_module",
        lambda _: SimpleNamespace(Article=_Article),
    )
    assert (
        _default_article_extractor("https://example.com/news")
        == "India VIX cools after RBI commentary."
    )


def test_news_scraper_parses_atom_entry_link_href() -> None:
    scraper = NewsScraper(
        rss_feeds={"moneycontrol": "atom"},
        fetcher=lambda url: _ATOM_FEED,
        article_extractor=lambda url: f"article:{url}",
        sleep_func=lambda seconds: None,
    )
    headlines = scraper.fetch_headlines(max_items_per_feed=1)
    assert headlines[0].url == "https://atom.example/news3"
    assert headlines[0].article_text == "article:https://atom.example/news3"


def test_news_scraper_fallbacks_when_url_missing_or_article_empty() -> None:
    scraper = NewsScraper(
        rss_feeds={"moneycontrol": "nolink", "et_markets": "withlink"},
        fetcher=lambda url: _RSS_NO_LINK if url == "nolink" else _RSS_MONEYC,
        article_extractor=lambda url: "",
        sleep_func=lambda seconds: None,
    )
    headlines = scraper.fetch_headlines(max_items_per_feed=1)
    assert headlines[0].url == ""
    assert headlines[0].article_text == headlines[0].title
    assert headlines[1].article_text == headlines[1].title
