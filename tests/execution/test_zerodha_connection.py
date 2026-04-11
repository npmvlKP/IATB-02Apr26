from __future__ import annotations

import hashlib
import random
from datetime import UTC
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import (
    ZerodhaConnection,
    extract_request_token_from_redirect_url,
    extract_request_token_from_text,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _profile_payload() -> dict[str, object]:
    return {
        "status": "success",
        "data": {"user_id": "AB1234", "user_name": "Trader", "email": "trader@example.com"},
    }


def _margins_payload(balance: str = "99725.05") -> dict[str, object]:
    return {
        "status": "success",
        "data": {"equity": {"available": {"live_balance": balance}}},
    }


def test_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.setenv("ZERODHA_API_SECRET", "secret")
    with pytest.raises(ConfigError, match="ZERODHA_API_KEY is required"):
        ZerodhaConnection.from_env()


def test_from_env_requires_api_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)
    with pytest.raises(ConfigError, match="ZERODHA_API_SECRET is required"):
        ZerodhaConnection.from_env()


def test_login_url_contains_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "kite-secret")
    connection = ZerodhaConnection.from_env()
    login_url = connection.login_url()
    assert login_url.startswith("https://kite.zerodha.com/connect/login?")
    assert "api_key=kite-key" in login_url


def test_extract_request_token_from_redirect_url() -> None:
    redirect_url = "https://localhost/callback?request_token=req-xyz&status=success"
    assert extract_request_token_from_redirect_url(redirect_url) == "req-xyz"


def test_extract_request_token_from_text_handles_status_first_query() -> None:
    redirect_text = "https://localhost/callback?status=success&request_token=req-xyz"
    assert extract_request_token_from_text(redirect_text) == "req-xyz"


def test_extract_request_token_from_text_handles_encoded_ampersand() -> None:
    redirect_text = "https://localhost/callback?status=success&amp;request_token=req-xyz"
    assert extract_request_token_from_text(redirect_text) == "req-xyz"


def test_extract_request_token_from_text_handles_query_fragment_only() -> None:
    redirect_text = "status=success&request_token=req-xyz"
    assert extract_request_token_from_text(redirect_text) == "req-xyz"


def test_extract_request_token_from_redirect_url_rejects_missing_token() -> None:
    with pytest.raises(ConfigError, match="missing request_token"):
        extract_request_token_from_redirect_url("https://localhost/callback?status=success")


def test_establish_session_with_access_token_fetches_profile_and_balance() -> None:
    calls: list[str] = []

    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = body, timeout_seconds
        calls.append(url)
        assert headers["X-Kite-Version"] == "3"
        assert headers["Authorization"] == "token kite-key:token-123"
        if url.endswith("/user/profile"):
            assert method == "GET"
            return _profile_payload()
        if url.endswith("/user/margins"):
            assert method == "GET"
            return _margins_payload()
        msg = f"unexpected URL: {url}"
        raise AssertionError(msg)

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="token-123",  # noqa: S106
        retry_delay_seconds=0,
        http_request=fake_http_request,
    )
    session = connection.establish_session()
    assert calls == [
        "https://api.kite.trade/user/profile",
        "https://api.kite.trade/user/margins",
    ]
    assert session.user_id == "AB1234"
    assert session.available_balance == Decimal("99725.05")
    assert session.connected_at_utc.tzinfo is UTC


def test_establish_session_exchanges_request_token_then_fetches_account_details() -> None:
    calls: list[str] = []
    issued_access = "access" + "-123"

    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = timeout_seconds
        calls.append(url)
        assert headers["X-Kite-Version"] == "3"
        if url.endswith("/session/token"):
            assert method == "POST"
            assert headers["Content-Type"] == "application/x-www-form-urlencoded"
            values = parse_qs((body or b"").decode("utf-8"))
            expected = hashlib.sha256(b"kite-keyreq-123kite-secret").hexdigest()
            assert values["api_key"] == ["kite-key"]
            assert values["request_token"] == ["req-123"]
            assert values["checksum"] == [expected]
            return {"status": "success", "data": {"access_token": issued_access}}
        assert headers["Authorization"] == f"token kite-key:{issued_access}"
        return _profile_payload() if url.endswith("/user/profile") else _margins_payload("1000.10")

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        request_token="req-123",  # noqa: S106
        retry_delay_seconds=0,
        http_request=fake_http_request,
    )
    session = connection.establish_session()
    assert session.access_token == issued_access
    assert session.available_balance == Decimal("1000.10")
    assert calls == [
        "https://api.kite.trade/session/token",
        "https://api.kite.trade/user/profile",
        "https://api.kite.trade/user/margins",
    ]


def test_establish_session_request_token_overrides_stored_access_token() -> None:
    calls: list[str] = []
    issued_access = "issued" + "-456"

    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = timeout_seconds
        calls.append(url)
        assert headers["X-Kite-Version"] == "3"
        if url.endswith("/session/token"):
            assert method == "POST"
            values = parse_qs((body or b"").decode("utf-8"))
            assert values["request_token"] == ["req-fresh"]
            return {"status": "success", "data": {"access_token": issued_access}}
        assert headers["Authorization"] == f"token kite-key:{issued_access}"
        return _profile_payload() if url.endswith("/user/profile") else _margins_payload("321.00")

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="stale-access-token",  # noqa: S106
        retry_delay_seconds=0,
        http_request=fake_http_request,
    )
    session = connection.establish_session(request_token="req-fresh")  # noqa: S106
    assert session.access_token == issued_access
    assert session.available_balance == Decimal("321.00")
    assert calls == [
        "https://api.kite.trade/session/token",
        "https://api.kite.trade/user/profile",
        "https://api.kite.trade/user/margins",
    ]


def test_establish_session_without_any_token_fails() -> None:
    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        retry_delay_seconds=0,
    )
    with pytest.raises(ConfigError, match="ZERODHA_REQUEST_TOKEN"):
        connection.establish_session()


def test_establish_session_retries_retryable_errors() -> None:
    attempts = {"count": 0}

    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = url, method, headers, body, timeout_seconds
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise URLError("temporary")
        return _profile_payload() if attempts["count"] == 3 else _margins_payload()

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="token-123",  # noqa: S106
        retry_delay_seconds=0,
        max_retries=3,
        http_request=fake_http_request,
    )
    session = connection.establish_session()
    assert attempts["count"] == 4
    assert session.user_email == "trader@example.com"


def test_establish_session_non_retryable_http_error_fails_fast() -> None:
    attempts = {"count": 0}

    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = url, method, headers, body, timeout_seconds
        attempts["count"] += 1
        raise HTTPError(
            url="https://api.kite.trade/user/profile",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="token-123",  # noqa: S106
        retry_delay_seconds=0,
        max_retries=3,
        http_request=fake_http_request,
    )
    with pytest.raises(ConfigError, match="request failed"):
        connection.establish_session()
    assert attempts["count"] == 1


def test_establish_session_rejects_error_status_payload() -> None:
    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = url, method, headers, body, timeout_seconds
        return {"status": "error", "message": "invalid token"}

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="token-123",  # noqa: S106
        retry_delay_seconds=0,
        http_request=fake_http_request,
    )
    with pytest.raises(ConfigError, match="invalid token"):
        connection.establish_session()


def test_establish_session_rejects_missing_margin_balance() -> None:
    def fake_http_request(
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        _ = method, headers, body, timeout_seconds
        if url.endswith("/user/profile"):
            return _profile_payload()
        return {"status": "success", "data": {"equity": {"available": {}}}}

    connection = ZerodhaConnection(
        api_key="kite-key",
        api_secret="kite-secret",  # noqa: S106
        access_token="token-123",  # noqa: S106
        retry_delay_seconds=0,
        http_request=fake_http_request,
    )
    with pytest.raises(ConfigError, match="missing available balance"):
        connection.establish_session()
