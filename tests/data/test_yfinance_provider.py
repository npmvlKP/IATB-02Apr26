"""
Tests for yfinance provider integration.
"""

import random
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_timestamp
from iatb.data.yfinance_provider import YFinanceProvider

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeHistory:
    """Fake yfinance history object supporting both iterrows() and to_dict()."""

    def __init__(
        self,
        rows: list[tuple[datetime, dict[str, object]]],
        use_vectorized: bool = True,
    ) -> None:
        self._rows = rows
        self._use_vectorized = use_vectorized
        self.index = [row[0] for row in rows]

    def iterrows(self) -> list[tuple[datetime, dict[str, object]]]:
        """Legacy iterrows() support."""
        return self._rows

    def to_dict(self, orient: str = "records") -> list[dict[str, object]]:
        """Vectorized to_dict() support for performance."""
        if orient != "records":
            msg = f"Unsupported orient: {orient}"
            raise ValueError(msg)
        return [row[1] for row in self._rows]


class _FakeTicker:
    def __init__(
        self,
        history_rows: list[tuple[datetime, dict[str, object]]],
        fast_info: dict[str, object],
    ) -> None:
        self._history = _FakeHistory(history_rows)
        self.fast_info = fast_info
        self.info = {"regularMarketPrice": 101, "volume": 1000}

    def history(self, *, interval: str, period: str) -> _FakeHistory:
        _ = interval, period
        return self._history


class _BadHistoryTicker:
    def history(self, *, interval: str, period: str) -> object:
        _ = interval, period
        return object()


class TestYFinanceProvider:
    @pytest.mark.asyncio
    async def test_get_ohlcv_normalizes_history(self) -> None:
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        rows = [
            (
                now,
                {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500},
            ),
            (
                now + timedelta(minutes=1),
                {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1700},
            ),
        ]
        provider = YFinanceProvider(
            client_factory=lambda _: _FakeTicker(rows, {"lastPrice": 102}),
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            limit=2,
        )
        assert len(bars) == 2
        assert bars[0].open == create_price("100")
        assert bars[1].close == create_price("102")

    @pytest.mark.asyncio
    async def test_get_ohlcv_since_filters_rows(self) -> None:
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        rows = [
            (now, {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500}),
            (
                now + timedelta(minutes=1),
                {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1700},
            ),
        ]
        provider = YFinanceProvider(client_factory=lambda _: _FakeTicker(rows, {"lastPrice": 102}))
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            since=create_timestamp(now + timedelta(seconds=30)),
            limit=10,
        )
        assert len(bars) == 1
        assert bars[0].timestamp.minute == 16

    @pytest.mark.asyncio
    async def test_get_ticker_uses_fast_info(self) -> None:
        rows = [
            (
                datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500},
            )
        ]
        fast_info = {
            "bid": 100.5,
            "ask": 101.5,
            "lastPrice": 101,
            "lastVolume": 2200,
        }
        provider = YFinanceProvider(client_factory=lambda _: _FakeTicker(rows, fast_info))
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")
        assert ticker.last == create_price("101")

    @pytest.mark.asyncio
    async def test_get_ohlcv_unsupported_exchange_raises(self) -> None:
        provider = YFinanceProvider(client_factory=lambda _: _FakeTicker([], {}))
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ohlcv(
                symbol="BTCUSDT",
                exchange=Exchange.BINANCE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_unsupported_timeframe_raises(self) -> None:
        provider = YFinanceProvider(client_factory=lambda _: _FakeTicker([], {}))
        with pytest.raises(ConfigError, match="Unsupported yfinance timeframe"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="10m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_history_without_iterrows_raises(self) -> None:
        provider = YFinanceProvider(client_factory=lambda _: _BadHistoryTicker())
        with pytest.raises(ConfigError, match="iterrows"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_uses_info_fallback_when_fast_info_unavailable(self) -> None:
        rows = [
            (
                datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500},
            )
        ]
        ticker = _FakeTicker(rows, {})
        ticker.fast_info = []
        ticker.info = {"regularMarketPrice": 111, "volume": 700}
        provider = YFinanceProvider(client_factory=lambda _: ticker)
        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert snapshot.last == create_price("111")
        assert snapshot.bid == create_price("111")
        assert snapshot.ask == create_price("111")

    @pytest.mark.asyncio
    async def test_get_ticker_invalid_numeric_payload_raises(self) -> None:
        rows = [
            (
                datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500},
            )
        ]
        fast_info = {"bid": object(), "ask": 101, "lastPrice": 101, "lastVolume": 1000}
        provider = YFinanceProvider(client_factory=lambda _: _FakeTicker(rows, fast_info))
        with pytest.raises(ConfigError, match="numeric-compatible"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    def test_default_client_factory_missing_dependency_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "iatb.data.yfinance_provider.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="yfinance dependency"):
            YFinanceProvider._default_client_factory("RELIANCE.NS")

    @pytest.mark.asyncio
    async def test_vectorized_extraction_large_dataset_performance(self) -> None:
        """Test that vectorized extraction handles large datasets efficiently.

        This test verifies that the to_dict('records') approach (vectorized)
        can handle 30 days of data for multiple symbols efficiently.
        Target: <500ms for 10 symbols with 30 days each.
        """
        import time

        # Generate 30 days of data (simulating real workload)
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        rows = []
        for day in range(30):
            timestamp = now + timedelta(days=day)
            rows.append(
                (
                    timestamp,
                    {
                        "Open": 100 + day,
                        "High": 102 + day,
                        "Low": 99 + day,
                        "Close": 101 + day,
                        "Volume": 1000 + day * 100,
                    },
                )
            )

        provider = YFinanceProvider(
            client_factory=lambda _: _FakeTicker(rows, {"lastPrice": 131}),
        )

        start_time = time.perf_counter()
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Verify correctness
        assert len(bars) == 30
        assert bars[0].close == create_price("101")
        assert bars[-1].close == create_price("130")

        # Verify performance (should be very fast with vectorized approach)
        # Allow generous margin for test environment variations
        assert elapsed_ms < 100, f"Vectorized extraction took {elapsed_ms:.2f}ms, expected <100ms"

    @pytest.mark.asyncio
    async def test_vectorized_extraction_preserves_timestamps(self) -> None:
        """Test that vectorized extraction correctly preserves timestamps from DataFrame index."""
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        rows = [
            (now, {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500}),
            (
                now + timedelta(days=1),
                {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1700},
            ),
            (
                now + timedelta(days=2),
                {"Open": 102, "High": 104, "Low": 101, "Close": 103, "Volume": 1900},
            ),
        ]

        provider = YFinanceProvider(
            client_factory=lambda _: _FakeTicker(rows, {"lastPrice": 103}),
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=3,
        )

        # Verify timestamps are correctly preserved from index
        assert bars[0].timestamp == now
        assert bars[1].timestamp == now + timedelta(days=1)
        assert bars[2].timestamp == now + timedelta(days=2)

    @pytest.mark.asyncio
    async def test_fallback_to_iterrows_when_to_dict_fails(self) -> None:
        """Test that code falls back to iterrows() when to_dict() fails."""

        class _BadDictHistory:
            """History object that fails on to_dict() but supports iterrows()."""

            def __init__(self, rows: list[tuple[datetime, dict[str, object]]]) -> None:
                self._rows = rows

            def iterrows(self) -> list[tuple[datetime, dict[str, object]]]:
                return self._rows

            def to_dict(self, orient: str = "records") -> list[dict[str, object]]:
                # Simulate failure in to_dict()
                msg = "Simulated to_dict() failure"
                raise ValueError(msg)

        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        rows = [
            (now, {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1500}),
            (
                now + timedelta(days=1),
                {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1700},
            ),
        ]

        class _TickerWithBadHistory:
            def __init__(self) -> None:
                self._history = _BadDictHistory(rows)
                self.fast_info = {"lastPrice": 102}
                self.info = {}

            def history(self, *, interval: str, period: str) -> _BadDictHistory:
                return self._history

        provider = YFinanceProvider(
            client_factory=lambda _: _TickerWithBadHistory(),
        )

        # Should fall back to iterrows() and still work
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=2,
        )

        assert len(bars) == 2
        assert bars[0].close == create_price("101")
        assert bars[1].close == create_price("102")
