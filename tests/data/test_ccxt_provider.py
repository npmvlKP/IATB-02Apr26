"""
Tests for CCXT provider integration.
"""


import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.ccxt_provider import CCXTProvider

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


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


class TestCCXTSymbolNormalization:
    """Test symbol normalization logic."""

    def test_normalizes_symbol_without_slash(self) -> None:
        """Test symbol without slash is normalized."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("BTCUSDT")
        assert result == "BTC/USDT"

    def test_normalizes_symbol_with_slash(self) -> None:
        """Test symbol with slash is returned as-is."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("BTC/USDT")
        assert result == "BTC/USDT"

    def test_normalizes_symbol_with_inr_quote(self) -> None:
        """Test INR quote currency is detected."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("BTCINR")
        assert result == "BTC/INR"

    def test_normalizes_symbol_with_btc_quote(self) -> None:
        """Test BTC quote currency is detected."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("ETHBTC")
        assert result == "ETH/BTC"

    def test_normalizes_symbol_with_eth_quote(self) -> None:
        """Test ETH quote currency is detected."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("ADAETH")
        assert result == "ADA/ETH"

    def test_returns_short_symbol_unchanged(self) -> None:
        """Test very short symbol is returned unchanged."""
        from iatb.data.ccxt_provider import _normalize_symbol

        result = _normalize_symbol("BTC")
        assert result == "BTC"


class TestCCXTExchangeID:
    """Test exchange ID mapping."""

    def test_maps_binance_exchange(self) -> None:
        """Test BINANCE maps to binance."""
        from iatb.data.ccxt_provider import _exchange_id

        result = _exchange_id(Exchange.BINANCE)
        assert result == "binance"

    def test_maps_coindcx_exchange(self) -> None:
        """Test COINDCX maps to coindcx."""
        from iatb.data.ccxt_provider import _exchange_id

        result = _exchange_id(Exchange.COINDCX)
        assert result == "coindcx"

    def test_rejects_unsupported_exchange(self) -> None:
        """Test unsupported exchange raises error."""
        from iatb.data.ccxt_provider import _exchange_id

        with pytest.raises(ConfigError, match="Unsupported exchange"):
            _exchange_id(Exchange.NSE)


class TestCCXTNumericCoercion:
    """Test numeric input coercion."""

    def test_rejects_boolean_input(self) -> None:
        """Test boolean values are rejected."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(True, field_name="test")

    def test_accepts_decimal_input(self) -> None:
        """Test Decimal values are accepted."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        result = _coerce_numeric_input(Decimal("123.45"), field_name="test")
        assert result == Decimal("123.45")

    def test_accepts_int_input(self) -> None:
        """Test int values are accepted."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        result = _coerce_numeric_input(100, field_name="test")
        assert result == 100

    def test_accepts_string_input(self) -> None:
        """Test string values are accepted."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        result = _coerce_numeric_input("123.45", field_name="test")
        assert result == "123.45"

    def test_converts_float_to_string(self) -> None:
        """Test float values are converted to string."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        result = _coerce_numeric_input(123.45, field_name="test")
        assert result == "123.45"

    def test_rejects_invalid_type(self) -> None:
        """Test invalid types are rejected."""
        from iatb.data.ccxt_provider import _coerce_numeric_input

        with pytest.raises(ConfigError, match="must be numeric-compatible"):
            _coerce_numeric_input([1, 2, 3], field_name="test")


class TestCCXTTickers:
    """Test ticker handling edge cases."""

    @pytest.mark.asyncio
    async def test_get_ticker_fallback_to_close(self) -> None:
        """Test ticker falls back to close when last is missing."""

        class _FallbackClient(_FakeCCXTClient):
            def fetch_ticker(self, symbol: str) -> dict[str, object]:
                return {"close": 101.5, "bid": 101, "ask": 102, "baseVolume": 3300}

        provider = CCXTProvider(exchange_factory=lambda _: _FallbackClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.last == create_price("101.5")

    @pytest.mark.asyncio
    async def test_get_ticker_fallback_bid_to_last(self) -> None:
        """Test ticker falls back to last when bid is missing."""

        class _FallbackClient(_FakeCCXTClient):
            def fetch_ticker(self, symbol: str) -> dict[str, object]:
                return {"last": 101.5, "ask": 102, "baseVolume": 3300}

        provider = CCXTProvider(exchange_factory=lambda _: _FallbackClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.bid == create_price("101.5")

    @pytest.mark.asyncio
    async def test_get_ticker_fallback_ask_to_last(self) -> None:
        """Test ticker falls back to last when ask is missing."""

        class _FallbackClient(_FakeCCXTClient):
            def fetch_ticker(self, symbol: str) -> dict[str, object]:
                return {"last": 101.5, "bid": 101, "baseVolume": 3300}

        provider = CCXTProvider(exchange_factory=lambda _: _FallbackClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.ask == create_price("101.5")

    @pytest.mark.asyncio
    async def test_get_ticker_fallback_volume_to_zero(self) -> None:
        """Test ticker falls back to zero when volume is missing."""

        class _FallbackClient(_FakeCCXTClient):
            def fetch_ticker(self, symbol: str) -> dict[str, object]:
                return {"last": 101.5, "bid": 101, "ask": 102}

        provider = CCXTProvider(exchange_factory=lambda _: _FallbackClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.volume_24h == create_price("0")

    @pytest.mark.asyncio
    async def test_get_ticker_uses_quote_volume(self) -> None:
        """Test ticker uses quoteVolume when baseVolume is missing."""

        class _VolumeFallbackClient(_FakeCCXTClient):
            def fetch_ticker(self, symbol: str) -> dict[str, object]:
                return {
                    "last": 101.5,
                    "bid": 101,
                    "ask": 102,
                    "quoteVolume": 5000,
                }

        provider = CCXTProvider(exchange_factory=lambda _: _VolumeFallbackClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)
        assert ticker.volume_24h == create_price("5000")


class TestCCXTOHLCVEncoding:
    """Test OHLCV data encoding and normalization."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_empty_response(self) -> None:
        """Test empty OHLCV response is handled."""

        class _EmptyClient(_FakeCCXTClient):
            def fetch_ohlcv(
                self,
                symbol: str,
                timeframe: str,
                since: int | None,
                limit: int,
            ) -> list[list[object]]:
                return []

        provider = CCXTProvider(exchange_factory=lambda _: _EmptyClient())
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            limit=10,
        )
        assert len(bars) == 0

    @pytest.mark.asyncio
    async def test_get_ohlcv_respects_limit(self) -> None:
        """Test that limit parameter is respected."""
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            limit=1,
        )
        assert len(bars) == 1

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_large_dataset(self) -> None:
        """Test handling of large OHLCV dataset."""

        class _LargeDatasetClient(_FakeCCXTClient):
            def __init__(self) -> None:
                self._rows = [
                    [1735722900000 + i * 60000, 100 + i, 105 + i, 95 + i, 101 + i, 1000 + i * 100]
                    for i in range(100)
                ]

        provider = CCXTProvider(exchange_factory=lambda _: _LargeDatasetClient())
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            limit=100,
        )
        assert len(bars) == 100

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_since_parameter(self) -> None:
        """Test that since parameter filters data."""
        from datetime import UTC, datetime

        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        since = datetime(2025, 1, 1, tzinfo=UTC)
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.BINANCE,
            timeframe="1m",
            since=since,
            limit=10,
        )
        # Since our mock data is from 2025-01-01, it should be included
        assert len(bars) == 2


class TestCCXTCoindCXIntegration:
    """Test CoinDCX exchange integration."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_coindcx(self) -> None:
        """Test OHLCV fetch from CoinDCX."""
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        bars = await provider.get_ohlcv(
            symbol="BTCUSDT",
            exchange=Exchange.COINDCX,
            timeframe="1m",
            limit=2,
        )
        assert len(bars) == 2

    @pytest.mark.asyncio
    async def test_get_ticker_coindcx(self) -> None:
        """Test ticker fetch from CoinDCX."""
        provider = CCXTProvider(exchange_factory=lambda _: _FakeCCXTClient())
        ticker = await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.COINDCX)
        assert ticker.symbol == "BTCUSDT"
        assert ticker.exchange == Exchange.COINDCX
