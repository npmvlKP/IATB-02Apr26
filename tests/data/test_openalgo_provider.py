"""
Tests for OpenAlgo provider integration.
"""

import random
from typing import Any

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.openalgo_provider import OpenAlgoProvider

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _http_get_factory(responses: dict[str, dict[str, object]]) -> Any:
    def _http_get(url: str, headers: dict[str, str]) -> dict[str, object]:
        _ = headers
        for key, payload in responses.items():
            if key in url:
                return payload
        return {"data": []}

    return _http_get


class TestOpenAlgoProvider:
    @pytest.mark.asyncio
    async def test_get_ohlcv_parses_data_list(self) -> None:
        payload = {
            "data": [
                {
                    "timestamp": "2026-01-01T09:15:00+00:00",
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 1000,
                }
            ]
        }
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": payload}),
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            limit=1,
        )
        assert len(bars) == 1
        assert bars[0].close == create_price("101")

    @pytest.mark.asyncio
    async def test_get_ticker_parses_mapping_payload(self) -> None:
        payload = {"data": {"bid": 100.5, "ask": 101.5, "last": 101, "volume_24h": 900}}
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")

    @pytest.mark.asyncio
    async def test_get_ticker_missing_data_mapping_raises(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": {"data": []}}),
        )
        with pytest.raises(ConfigError, match="missing data mapping"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_ohlcv_non_positive_limit_raises(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": []}}),
        )
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=0,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_missing_data_list_raises(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": {"not": "a-list"}}}),
        )
        with pytest.raises(ConfigError, match="missing data list"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_non_mapping_http_payload_raises(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: [],
        )
        with pytest.raises(ConfigError, match="must be mapping-like JSON"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_ticker_invalid_numeric_payload_raises(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory(
                {"market/ticker": {"data": {"bid": object(), "ask": 1, "last": 1, "volume": 1}}},
            ),
        )
        with pytest.raises(ConfigError, match="numeric-compatible"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    def test_constructor_uses_env_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENALGO_API_KEY", "from-env")
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key=None,
            http_get=_http_get_factory({"market/ticker": {"data": {}}}),
        )
        assert provider._api_key == "from-env"

    def test_constructor_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENALGO_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="API key is required"):
            OpenAlgoProvider(base_url="https://api.openalgo.local")

    def test_constructor_invalid_base_url_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            OpenAlgoProvider(base_url="ftp://api.openalgo.local", api_key="secret")

    def test_constructor_base_url_without_host_raises(self) -> None:
        with pytest.raises(ConfigError, match="must include host"):
            OpenAlgoProvider(base_url="https://", api_key="secret")
