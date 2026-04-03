"""
RSS news scraper for Indian financial sources with rate limiting.
"""

import importlib
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from xml.etree import ElementTree as XmlElementTree  # nosec B405

from iatb.core.exceptions import ConfigError

ATOM_NS = "{http://www.w3.org/2005/Atom}"
DEFAULT_RSS_FEEDS = {
    "moneycontrol": "https://www.moneycontrol.com/rss/latestnews.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "nse_announcements": "https://www.nseindia.com/rss/corporate-announcements.xml",
}


class XmlNode(Protocol):
    attrib: dict[str, str]

    def findtext(self, path: str) -> str | None:
        ...

    def find(self, path: str) -> "XmlNode | None":
        ...

    def findall(self, path: str) -> list["XmlNode"]:
        ...


@dataclass(frozen=True)
class NewsHeadline:
    source: str
    title: str
    url: str
    published: str
    article_text: str


def _default_fetcher(url: str) -> str:
    request = urllib.request.Request(url=url, method="GET")  # noqa: S310  # nosec B310
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310  # nosec B310
        payload = response.read()
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


def _default_article_extractor(url: str) -> str:
    try:
        newspaper = importlib.import_module("newspaper")
    except ModuleNotFoundError as exc:
        msg = "newspaper3k dependency is required for NewsScraper article extraction"
        raise ConfigError(msg) from exc
    article_cls = getattr(newspaper, "Article", None)
    if not callable(article_cls):
        msg = "newspaper.Article is unavailable"
        raise ConfigError(msg)
    article = article_cls(url)
    article.download()
    article.parse()
    return str(article.text).strip()


class NewsScraper:
    """Fetch RSS headlines from configured sources with feed-level throttling."""

    def __init__(
        self,
        rss_feeds: dict[str, str] | None = None,
        rate_limit_seconds: float = 1.0,
        fetcher: Callable[[str], str] | None = None,
        article_extractor: Callable[[str], str] | None = None,
        sleep_func: Callable[[float], None] | None = None,
    ) -> None:
        if rate_limit_seconds < 0:
            msg = "rate_limit_seconds cannot be negative"
            raise ConfigError(msg)
        self._rss_feeds = rss_feeds or DEFAULT_RSS_FEEDS
        self._rate_limit_seconds = rate_limit_seconds
        self._fetcher = fetcher or _default_fetcher
        self._article_extractor = article_extractor or _default_article_extractor
        self._sleep = sleep_func or time.sleep

    def fetch_headlines(self, max_items_per_feed: int = 5) -> list[NewsHeadline]:
        if max_items_per_feed <= 0:
            msg = "max_items_per_feed must be positive"
            raise ConfigError(msg)
        headlines: list[NewsHeadline] = []
        feed_items = list(self._rss_feeds.items())
        for index, (source, feed_url) in enumerate(feed_items):
            payload = self._fetcher(feed_url)
            headlines.extend(self._parse_feed(source, payload, max_items_per_feed))
            if index < len(feed_items) - 1 and self._rate_limit_seconds > 0:
                self._sleep(self._rate_limit_seconds)
        return headlines

    def _parse_feed(self, source: str, xml_payload: str, limit: int) -> list[NewsHeadline]:
        try:
            root = cast(
                XmlNode,
                XmlElementTree.fromstring(xml_payload),  # noqa: S314  # nosec B314
            )
        except XmlElementTree.ParseError as exc:
            msg = f"Invalid RSS payload for source: {source}"
            raise ConfigError(msg) from exc
        entries = root.findall(".//item") or root.findall(f".//{ATOM_NS}entry")
        return [self._entry_to_headline(source, entry) for entry in entries[:limit]]

    def _entry_to_headline(self, source: str, entry: XmlNode) -> NewsHeadline:
        title = self._find_text(entry, ("title", f"{ATOM_NS}title")) or "UNTITLED"
        url = self._resolve_link(entry)
        published = self._find_text(
            entry,
            ("pubDate", "published", "updated", f"{ATOM_NS}published", f"{ATOM_NS}updated"),
        )
        article_text = self._safe_extract_article(url, title)
        return NewsHeadline(
            source=source,
            title=title,
            url=url,
            published=published,
            article_text=article_text,
        )

    @staticmethod
    def _find_text(entry: XmlNode, tags: tuple[str, ...]) -> str:
        for tag in tags:
            value = entry.findtext(tag)
            if value is not None and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _resolve_link(entry: XmlNode) -> str:
        text_link = entry.findtext("link")
        if text_link is not None and text_link.strip():
            return text_link.strip()
        atom_link = entry.find(f"{ATOM_NS}link")
        if atom_link is not None:
            return str(atom_link.attrib.get("href", "")).strip()
        return ""

    def _safe_extract_article(self, url: str, fallback_text: str) -> str:
        if not url:
            return fallback_text
        try:
            extracted = self._article_extractor(url)
        except Exception:
            return fallback_text
        return extracted if extracted else fallback_text
