"""
Unit tests for src/iatb/data/openalgo_provider.py.

Tests cover: Zerodha login happy path, auth errors, per-exchange feed status,
timezone handling, DataFeedStatus summary.
All external calls are mocked.
"""

import random
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.openalgo_provider import (
    DataFeedStatus,
    ExchangeFeedState,
    FeedStatus,
    OpenAlgoProvider,
    ZerodhaAuth,
    check_exchange_feed,
    initialize_feed_status,
)

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


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


class TestZerodhaAuthLoginHappyPath:
    def test_authenticate_with_env_access_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "env-token-abc")
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        token = auth.authenticate()
        assert token == "env-token-abc"
        assert auth.is_authenticated

    def test_authenticate_with_explicit_access_token(self) -> None:
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="explicit-token-xyz",
        )
        token = auth.authenticate()
        assert token == "explicit-token-xyz"

    def test_authenticate_request_token_exchange(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        post_fn = _http_post_factory(
            {
                "auth/token": {"data": {"access_token": "exchanged-token"}},
            }
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            http_post=post_fn,
        )
        auth._request_token = "req-token"
        auth._api_key = "api-key"
        auth._api_secret = "api-secret"
        token = auth.authenticate()
        assert token == "exchanged-token"
        assert auth.is_authenticated


class TestZerodhaAuthErrors:
    def test_no_tokens_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("ZERODHA_REQUEST_TOKEN", raising=False)
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        with pytest.raises(ConfigError, match="no access_token or request_token"):
            auth.authenticate()

    def test_request_token_missing_api_credentials(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        auth = ZerodhaAuth(base_url="http://localhost:5000")
        auth._request_token = "req-token"
        auth._api_key = None
        auth._api_secret = None
        with pytest.raises(ConfigError, match="API_KEY and API_SECRET required"):
            auth.authenticate()

    def test_request_token_exchange_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
        post_fn = _http_post_factory(
            {
                "auth/token": {"data": {"error": "invalid"}},
            }
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            http_post=post_fn,
        )
        auth._request_token = "bad-token"
        auth._api_key = "key"
        auth._api_secret = "secret"
        with pytest.raises(ConfigError, match="failed to exchange request_token"):
            auth.authenticate()

    def test_invalid_base_url_scheme(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            ZerodhaAuth(base_url="ftp://bad", access_token="tok")

    def test_not_authenticated_initially(self) -> None:
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="tok",
        )
        assert not auth.is_authenticated


class TestPerExchangeStatus:
    def test_check_exchange_feed_live(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda url, headers: {
                "data": {"bid": 100, "ask": 101, "last": 100},
            },
        )
        state = check_exchange_feed(provider, Exchange.NSE)
        assert state.status == FeedStatus.LIVE
        assert state.exchange == Exchange.NSE
        assert state.source == "Zerodha/OpenAlgo"
        assert state.checked_at_utc.tzinfo == UTC

    def test_check_exchange_feed_fallback_on_error(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: (_ for _ in ()).throw(ConfigError("fail")),
        )
        state = check_exchange_feed(provider, Exchange.CDS)
        assert state.status == FeedStatus.FALLBACK
        assert state.error is not None

    def test_check_exchange_feed_mcx(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda url, headers: {
                "data": {"bid": 60000, "ask": 60100, "last": 60050},
            },
        )
        state = check_exchange_feed(provider, Exchange.MCX)
        assert state.status == FeedStatus.LIVE
        assert state.exchange == Exchange.MCX


class TestTimezoneHandling:
    def test_exchange_feed_state_utc_timestamp(self) -> None:
        now = datetime.now(UTC)
        state = ExchangeFeedState(
            exchange=Exchange.NSE,
            status=FeedStatus.LIVE,
            source="test",
            checked_at_utc=now,
        )
        assert state.checked_at_utc.tzinfo == UTC

    def test_feed_status_summary_contains_all_exchanges(self) -> None:
        now = datetime.now(UTC)
        status = DataFeedStatus(
            exchanges={
                Exchange.NSE: ExchangeFeedState(
                    exchange=Exchange.NSE,
                    status=FeedStatus.LIVE,
                    source="test",
                    checked_at_utc=now,
                ),
                Exchange.CDS: ExchangeFeedState(
                    exchange=Exchange.CDS,
                    status=FeedStatus.FALLBACK,
                    source="test",
                    checked_at_utc=now,
                ),
                Exchange.MCX: ExchangeFeedState(
                    exchange=Exchange.MCX,
                    status=FeedStatus.UNAVAILABLE,
                    source="test",
                    checked_at_utc=now,
                ),
            },
        )
        summary = status.summary_line()
        assert "NSE: LIVE" in summary
        assert "CDS: FALLBACK" in summary
        assert "MCX: UNAVAILABLE" in summary

    def test_initialize_feed_status_with_unauthenticated(self) -> None:
        provider = OpenAlgoProvider(
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda url, headers: {"data": {}},
        )
        auth = ZerodhaAuth(
            base_url="http://localhost:5000",
            access_token="token",
        )
        status = initialize_feed_status(auth, provider)
        for state in status.exchanges.values():
            assert state.checked_at_utc.tzinfo == UTC
