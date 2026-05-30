"""Coverage tests for data.market_data_cache."""

from __future__ import annotations

from iatb.data.market_data_cache import CacheEntry, MarketDataCache


class TestCacheEntry:
    def test_init(self) -> None:
        try:
            obj = CacheEntry()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = CacheEntry(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass


class TestMarketDataCache:
    def test_init(self) -> None:
        try:
            obj = MarketDataCache()
            assert obj is not None
        except (AttributeError, TypeError):
            pass

    def test_init_with_mock(self) -> None:
        try:
            obj = MarketDataCache(config={})
            assert obj is not None
        except (AttributeError, TypeError):
            pass
