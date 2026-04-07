"""
Tests for CCXT provider integration.
"""


import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.ccxt_provider import CCXTProvider


class _FakeCCXTClient:
    def __init__(self) -> None:
        self._rows = [
            [1735722900000, 100, 105, 95, 101, 1000],
            [1735722960000, 101, 106, 96, 102, 1200],
        ]

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None,
        limit: int,
    ) -> list[list[object]]:
        _ = symbol, timeframe, since, limit
        return self._rows

    def fetch_ticker(self, symbol: str) -> dict[str, object]:
        _ = symbol
        return {"bid": 101, "ask": 102, "last": 101.5, "baseVolume": 3300}


class _InvalidRowsClient(_FakeCCXTClient):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None,
        limit: int,
    ) -> list[list[object]]:
        _ = symbol, timeframe, since, limit
        return [[1735722900000, 100, 105]]


class _NonMappingTickerClient(_FakeCCXTClient):
    def fetch_ticker(self, symbol: str) -> object:
        _ = symbol
        return ["invalid"]


class _MissingLastTickerClient(_FakeCCXTClient):
    def fetch_ticker(self, symbol: str) -> dict[str, object]:
        _ = symbol
        return {"bid": 100, "ask": 101}


class _InvalidNumericTickerClient(_FakeCCXTClient):
    def fetch_ticker(self, symbol: str) -> dict[str, object]:
        _ = symbol
        return {"bid": object(), "ask": 101, "last": 100, "baseVolume": 10}


class TestCCXTProvider:
    @pytest.mark.asyncio
    async def test_get_ohlcv_maps_ccxt_rows(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            limit=2,
        )
        assert len(bars) == 2
        assert bars[0].open == create_price("100")
        assert bars[1].close == create_price("102")

    @pytest.mark.asyncio
    async def test_get_ticker_maps_payload(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.bid == create_price("101")
        assert ticker.ask == create_price("102")

    @pytest.mark.asyncio
    async def test_get_ohlcv_unsupported_exchange_raises(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_rejects_invalid_limit(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="BTCUSDT",
                exchange=Exchange.BINANCE,
                timeframe="1m",
                limit=0,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_invalid_row_shape_raises(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _InvalidRowsClient())
        with pytest.raises(ConfigError, match="CCXT OHLCV row must include"):
            await provider.get_ohlcv(
                symbol="BTCUSDT",
                exchange=Exchange.BINANCE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_non_mapping_payload_raises(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _NonMappingTickerClient())
        with pytest.raises(ConfigError, match="must be mapping-like"):
            await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)

    @pytest.mark.asyncio
    async def test_get_ticker_missing_last_raises(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _MissingLastTickerClient())
        with pytest.raises(ConfigError, match="missing last/close"):
            await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)

    @pytest.mark.asyncio
    async def test_get_ticker_invalid_numeric_payload_raises(self) -> None:
        provider = CCXTProvider(exchange_factory=lambda _: _InvalidNumericTickerClient())
        with pytest.raises(ConfigError, match="numeric-compatible"):
            await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)

    def test_default_exchange_factory_missing_dependency_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "iatb.data.ccxt_provider.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="ccxt dependency"):
            CCXTProvider._default_exchange_factory("binance")

    def test_default_exchange_factory_missing_exchange_class_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "iatb.data.ccxt_provider.importlib.import_module",
            lambda _: object(),
        )
        with pytest.raises(ConfigError, match="exchange class not found"):
            CCXTProvider._default_exchange_factory("binance")
