"""
Tests for jugaad-data provider integration.
"""


import random

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.jugaad_provider import JugaadProvider

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeFrame:
    """Fake jugaad DataFrame supporting both iterrows() and to_dict()."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self) -> list[tuple[int, dict[str, object]]]:
        """Legacy iterrows() support."""
        return list(enumerate(self._rows))

    def to_dict(self, orient: str = "records") -> list[dict[str, object]]:
        """Vectorized to_dict() support for performance."""
        if orient != "records":
            msg = f"Unsupported orient: {orient}"
            raise ValueError(msg)
        return self._rows


class _InvalidRowFrame:
    def iterrows(self) -> list[tuple[int, object]]:
        return [(0, "invalid-row")]


class TestJugaadProvider:
    @pytest.mark.asyncio
    async def test_get_ohlcv_uses_stock_df_payload(self) -> None:
        rows = [
            {
                "DATE": "2026-01-01T00:00:00+00:00",
                "OPEN": 100,
                "HIGH": 110,
                "LOW": 90,
                "CLOSE": 105,
                "TOTTRDQTY": 1000,
            },
            {
                "DATE": "2026-01-02T00:00:00+00:00",
                "OPEN": 105,
                "HIGH": 115,
                "LOW": 95,
                "CLOSE": 110,
                "TOTTRDQTY": 2000,
            },
        ]

        def _stock_df(**_: object) -> _FakeFrame:
            return _FakeFrame(rows)

        provider = JugaadProvider(stock_df_loader=lambda: _stock_df)
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )
        assert len(bars) == 2
        assert bars[0].close == create_price("105")

    @pytest.mark.asyncio
    async def test_get_ticker_derives_from_latest_bar(self) -> None:
        rows = [
            {
                "DATE": "2026-01-02T00:00:00+00:00",
                "OPEN": 100,
                "HIGH": 110,
                "LOW": 90,
                "CLOSE": 105,
                "TOTTRDQTY": 1000,
            }
        ]
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _FakeFrame(rows)))
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.last == create_price("105")

    @pytest.mark.asyncio
    async def test_get_ohlcv_non_nse_exchange_raises(self) -> None:
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _FakeFrame([])))
        with pytest.raises(ConfigError, match="only supports NSE"):
            await provider.get_ohlcv(
                symbol="SBIN",
                exchange=Exchange.BSE,
                timeframe="1d",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_non_daily_timeframe_raises(self) -> None:
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _FakeFrame([])))
        with pytest.raises(ConfigError, match="supports only 1d timeframe"):
            await provider.get_ohlcv(
                symbol="SBIN",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_non_positive_limit_raises(self) -> None:
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _FakeFrame([])))
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="SBIN",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=0,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_no_market_data_raises(self) -> None:
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _FakeFrame([])))
        with pytest.raises(ConfigError, match="No market data found"):
            await provider.get_ticker(symbol="SBIN", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_ohlcv_invalid_row_payload_raises(self) -> None:
        provider = JugaadProvider(stock_df_loader=lambda: (lambda **_: _InvalidRowFrame()))
        with pytest.raises(ConfigError, match="rows must be mapping-like"):
            await provider.get_ohlcv(
                symbol="SBIN",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=1,
            )

    def test_default_loader_missing_dependency_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "iatb.data.jugaad_provider.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="jugaad_data dependency"):
            JugaadProvider._default_stock_df_loader()

    def test_default_loader_missing_stock_df_symbol_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "iatb.data.jugaad_provider.importlib.import_module",
            lambda _: object(),
        )
        with pytest.raises(ConfigError, match="stock_df is not available"):
            JugaadProvider._default_stock_df_loader()

    @pytest.mark.asyncio
    async def test_vectorized_extraction_large_dataset_performance(self) -> None:
        """Test that vectorized extraction handles large datasets efficiently.

        This test verifies that the to_dict('records') approach (vectorized)
        can handle 30 days of data for multiple symbols efficiently.
        Target: <500ms for 10 symbols with 30 days each.
        """
        import time

        # Generate 30 days of data (simulating real workload)
        rows = []
        for day in range(30):
            rows.append(
                {
                    "DATE": f"2026-01-{day+1:02d}T00:00:00+00:00",
                    "OPEN": 100 + day,
                    "HIGH": 102 + day,
                    "LOW": 99 + day,
                    "CLOSE": 101 + day,
                    "TOTTRDQTY": 1000 + day * 100,
                }
            )

        def _stock_df(**_: object) -> _FakeFrame:
            return _FakeFrame(rows)

        provider = JugaadProvider(stock_df_loader=lambda: _stock_df)

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
    async def test_vectorized_extraction_handles_alternate_column_names(self) -> None:
        """Test that vectorized extraction handles alternate column naming conventions."""
        rows = [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1000,
            },
            {
                "TIMESTAMP": "2026-01-02T00:00:00+00:00",
                "OPEN": 105,
                "HIGH": 115,
                "LOW": 95,
                "CLOSE": 110,
                "VOLUME": 2000,
            },
        ]

        def _stock_df(**_: object) -> _FakeFrame:
            return _FakeFrame(rows)

        provider = JugaadProvider(stock_df_loader=lambda: _stock_df)
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=2,
        )

        assert len(bars) == 2
        assert bars[0].close == create_price("105")
        assert bars[1].close == create_price("110")

    @pytest.mark.asyncio
    async def test_fallback_to_iterrows_when_to_dict_fails(self) -> None:
        """Test that code falls back to iterrows() when to_dict() fails."""

        class _BadDictFrame:
            """DataFrame that fails on to_dict() but supports iterrows()."""

            def __init__(self, rows: list[dict[str, object]]) -> None:
                self._rows = rows

            def iterrows(self) -> list[tuple[int, dict[str, object]]]:
                return list(enumerate(self._rows))

            def to_dict(self, orient: str = "records") -> list[dict[str, object]]:
                # Simulate failure in to_dict()
                msg = "Simulated to_dict() failure"
                raise ValueError(msg)

        rows = [
            {
                "DATE": "2026-01-01T00:00:00+00:00",
                "OPEN": 100,
                "HIGH": 110,
                "LOW": 90,
                "CLOSE": 105,
                "TOTTRDQTY": 1000,
            },
            {
                "DATE": "2026-01-02T00:00:00+00:00",
                "OPEN": 105,
                "HIGH": 115,
                "LOW": 95,
                "CLOSE": 110,
                "TOTTRDQTY": 2000,
            },
        ]

        def _stock_df(**_: object) -> _BadDictFrame:
            return _BadDictFrame(rows)

        provider = JugaadProvider(stock_df_loader=lambda: _stock_df)

        # Should fall back to iterrows() and still work
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=2,
        )

        assert len(bars) == 2
        assert bars[0].close == create_price("105")
        assert bars[1].close == create_price("110")

    @pytest.mark.asyncio
    async def test_list_input_still_supported(self) -> None:
        """Test that list input (for testing) is still supported after vectorization."""
        rows = [
            {
                "DATE": "2026-01-01T00:00:00+00:00",
                "OPEN": 100,
                "HIGH": 110,
                "LOW": 90,
                "CLOSE": 105,
                "TOTTRDQTY": 1000,
            },
        ]

        def _stock_df(**_: object) -> list[dict[str, object]]:
            return rows

        provider = JugaadProvider(stock_df_loader=lambda: _stock_df)
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert bars[0].close == create_price("105")
