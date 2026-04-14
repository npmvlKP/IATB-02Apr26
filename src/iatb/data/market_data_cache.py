"""
Market data cache with TTL support for reducing API calls.

Provides thread-safe, time-based caching for market data responses
to improve scan cycle performance.
"""

import hashlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    """Cached market data entry with metadata."""

    data: Any
    cached_at: datetime
    cache_key: str

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry has expired."""
        expiry_time = self.cached_at + timedelta(seconds=ttl_seconds)
        return datetime.now(UTC) >= expiry_time


class MarketDataCache:
    """
    Thread-safe cache for market data with TTL support.

    Reduces redundant API calls by caching responses for a configurable duration.
    """

    def __init__(self, default_ttl_seconds: int = 60) -> None:
        """
        Initialize market data cache.

        Args:
            default_ttl_seconds: Default time-to-live for cache entries in seconds.
        """
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._default_ttl_seconds = default_ttl_seconds
        self._hits: int = 0
        self._misses: int = 0

    def _generate_cache_key(self, symbol: str, start_date: str, end_date: str) -> str:
        """
        Generate a deterministic cache key for market data request.

        Args:
            symbol: Instrument symbol.
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).

        Returns:
            SHA256 hash-based cache key.
        """
        key_string = f"{symbol}:{start_date}:{end_date}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def get(self, symbol: str, start_date: str, end_date: str) -> Any | None:
        """
        Retrieve cached data if available and not expired.

        Args:
            symbol: Instrument symbol.
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).

        Returns:
            Cached data if available and valid, None otherwise.
        """
        cache_key = self._generate_cache_key(symbol, start_date, end_date)

        with self._lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired(self._default_ttl_seconds):
                del self._cache[cache_key]
                self._misses += 1
                _LOGGER.debug("Cache entry expired for %s", symbol)
                return None

            self._hits += 1
            _LOGGER.debug(
                "Cache hit for %s (hits: %d, misses: %d)",
                symbol,
                self._hits,
                self._misses,
            )
            return entry.data

    def put(self, symbol: str, start_date: str, end_date: str, data: Any) -> None:
        """
        Store data in cache with current timestamp.

        Args:
            symbol: Instrument symbol.
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).
            data: Market data to cache.
        """
        cache_key = self._generate_cache_key(symbol, start_date, end_date)
        entry = CacheEntry(
            data=data,
            cached_at=datetime.now(UTC),
            cache_key=cache_key,
        )

        with self._lock:
            self._cache[cache_key] = entry
            _LOGGER.debug("Cached data for %s (key: %s)", symbol, cache_key[:8])

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            entry_count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            _LOGGER.info("Cleared %d cache entries", entry_count)

    def purge_expired(self) -> int:
        """
        Remove all expired entries from cache.

        Returns:
            Number of entries purged.
        """
        with self._lock:
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if entry.is_expired(self._default_ttl_seconds)
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                _LOGGER.info("Purged %d expired cache entries", len(expired_keys))

            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics.
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else Decimal("0")

            return {
                "total_entries": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": float(hit_rate),
                "default_ttl_seconds": self._default_ttl_seconds,
            }

    def get_or_fetch(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        fetch_func: Callable[[], Any],
    ) -> Any:
        """
        Get data from cache or fetch using provided function.

        Args:
            symbol: Instrument symbol.
            start_date: Start date string (YYYY-MM-DD).
            end_date: End date string (YYYY-MM-DD).
            fetch_func: Function to call if data not in cache.

        Returns:
            Cached or freshly fetched data.
        """
        cached_data = self.get(symbol, start_date, end_date)
        if cached_data is not None:
            return cached_data

        data = fetch_func()
        if data is not None:
            self.put(symbol, start_date, end_date, data)

        return data
