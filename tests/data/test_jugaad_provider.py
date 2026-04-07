"""
Tests for jugaad-data provider integration.
"""


import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.jugaad_provider import JugaadProvider


class _FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self) -> list[tuple[int, dict[str, object]]]:
        return list(enumerate(self._rows))


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
