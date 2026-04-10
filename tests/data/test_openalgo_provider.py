"""
Tests for OpenAlgo provider integration including Zerodha auth and feed status.
"""

import random
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price
from iatb.data.openalgo_provider import (
    DataFeedStatus,
    ExchangeFeedState,
    FeedStatus,
    OpenAlgoProvider,
    ZerodhaAuth,
    check_exchange_feed,
    initialize_feed_status,
)

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


def _http_post_factory(responses: dict[str, dict[str, object]]) -> Any:
    def _http_post(
        url: str,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, object]:
        _ = headers, body
        for key, payload in responses.items():
            if key in url:
                return payload
        return {"data": {}}

    return _http_post


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


class TestZerodhaAuth:
    def test_authenticate_with_existing_access_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "test-token-123")
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        token = auth.authenticate()
        assert token == "test-token-123"
        assert auth.is_authenticated is True

    def test_authenticate_with_explicit_access_token(self) -> None:
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="explicit-token",
        )
        token = auth.authenticate()
        assert token == "explicit-token"
        assert auth.is_authenticated is True

    def test_authenticate_no_tokens_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("ZERODHA_REQUEST_TOKEN", raising=False)
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        with pytest.raises(ConfigError, match="no access_token or request_token"):
            auth.authenticate()

    def test_authenticate_request_token_exchange(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        post_fn = _http_post_factory(
            {
                "auth/token": {"data": {"access_token": "new-access-token"}},
            }
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            http_post=post_fn,
        )
        auth._request_token = "test-request-token"
        auth._api_key = "test-api-key"
        auth._api_secret = "test-api-secret"
        token = auth.authenticate()
        assert token == "new-access-token"
        assert auth.is_authenticated is True

    def test_authenticate_request_token_missing_credentials_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        auth._request_token = "some-token"
        auth._api_key = None
        auth._api_secret = None
        with pytest.raises(ConfigError, match="API_KEY and API_SECRET required"):
            auth.authenticate()

    def test_authenticate_request_token_exchange_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        post_fn = _http_post_factory(
            {
                "auth/token": {"data": {"error": "invalid_token"}},
            }
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            http_post=post_fn,
        )
        auth._request_token = "bad-request-token"
        auth._api_key = "key"
        auth._api_secret = "secret"
        with pytest.raises(ConfigError, match="failed to exchange request_token"):
            auth.authenticate()

    def test_authenticate_not_authenticated_initially(self) -> None:
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="token",
        )
        assert auth.is_authenticated is False

    def test_invalid_base_url_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            ZerodhaAuth(base_url="ftp://bad", access_token="token")


class TestExchangeFeedState:
    def test_live_state_creation(self) -> None:
        state = ExchangeFeedState(
            exchange=Exchange.NSE,
            status=FeedStatus.LIVE,
            source="Zerodha/OpenAlgo",
            checked_at_utc=datetime.now(UTC),
        )
        assert state.status == FeedStatus.LIVE
        assert state.exchange == Exchange.NSE
        assert state.error is None

    def test_fallback_state_with_error(self) -> None:
        state = ExchangeFeedState(
            exchange=Exchange.CDS,
            status=FeedStatus.FALLBACK,
            source="jugaad-data (EOD)",
            checked_at_utc=datetime.now(UTC),
            error="Connection refused",
        )
        assert state.status == FeedStatus.FALLBACK
        assert state.error == "Connection refused"


class TestDataFeedStatus:
    def test_empty_status_summary(self) -> None:
        status = DataFeedStatus()
        summary = status.summary_line()
        assert "NSE: UNAVAILABLE" in summary
        assert "CDS: UNAVAILABLE" in summary
        assert "MCX: UNAVAILABLE" in summary

    def test_mixed_status_summary(self) -> None:
        now = datetime.now(UTC)
        status = DataFeedStatus(
            exchanges={
                Exchange.NSE: ExchangeFeedState(
                    exchange=Exchange.NSE,
                    status=FeedStatus.LIVE,
                    source="Zerodha/OpenAlgo",
                    checked_at_utc=now,
                ),
                Exchange.CDS: ExchangeFeedState(
                    exchange=Exchange.CDS,
                    status=FeedStatus.FALLBACK,
                    source="jugaad-data (EOD)",
                    checked_at_utc=now,
                ),
            },
        )
        summary = status.summary_line()
        assert "NSE: LIVE" in summary
        assert "CDS: FALLBACK" in summary

    def test_all_live_summary(self) -> None:
        now = datetime.now(UTC)
        exchanges = {
            e: ExchangeFeedState(
                exchange=e,
                status=FeedStatus.LIVE,
                source="Zerodha/OpenAlgo",
                checked_at_utc=now,
            )
            for e in (Exchange.NSE, Exchange.CDS, Exchange.MCX)
        }
        status = DataFeedStatus(exchanges=exchanges)
        summary = status.summary_line()
        assert "LIVE" in summary
        assert "UNAVAILABLE" not in summary


class TestCheckExchangeFeed:
    def test_check_feed_live(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory(
                {
                    "market/ticker": {"data": {"bid": 100, "ask": 101, "last": 100}},
                }
            ),
        )
        state = check_exchange_feed(provider, Exchange.NSE)
        assert state.status == FeedStatus.LIVE
        assert state.exchange == Exchange.NSE

    def test_check_feed_fallback_on_error(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: (_ for _ in ()).throw(ConfigError("Connection failed")),
        )
        state = check_exchange_feed(provider, Exchange.MCX)
        assert state.status == FeedStatus.FALLBACK
        assert state.error is not None


class TestInitializeFeedStatus:
    def test_initialize_with_authenticated_auth(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory(
                {
                    "market/ticker": {"data": {"bid": 100, "ask": 101, "last": 100}},
                }
            ),
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="test-token",
        )
        auth.authenticate()
        status = initialize_feed_status(auth, provider)
        for exchange in (Exchange.NSE, Exchange.CDS, Exchange.MCX):
            assert exchange in status.exchanges

    def test_initialize_with_unauthenticated_auth(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": {"data": {}}}),
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="token",
        )
        status = initialize_feed_status(auth, provider)
        assert all(s.status == FeedStatus.FALLBACK for s in status.exchanges.values())


class TestFeedStatus:
    def test_feed_status_enum_values(self) -> None:
        assert FeedStatus.LIVE == "LIVE"
        assert FeedStatus.FALLBACK == "FALLBACK"
        assert FeedStatus.UNAVAILABLE == "UNAVAILABLE"
