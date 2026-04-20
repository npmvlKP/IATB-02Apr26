from __future__ import annotations

import importlib.util
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import ZerodhaSession

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "zerodha_connect.py"
_RELEVANT_ENV_VARS = (
    "ZERODHA_API_KEY",
    "ZERODHA_API_SECRET",
    "ZERODHA_ACCESS_TOKEN",
    "ZERODHA_ACCESS_TOKEN_DATE_UTC",
    "ZERODHA_REQUEST_TOKEN",
    "ZERODHA_REQUEST_TOKEN_DATE_UTC",
    "ZERODHA_REDIRECT_URL",
    "BROKER_OAUTH_2FA_VERIFIED",
)


def _load_script_module() -> object:
    spec = importlib.util.spec_from_file_location("zerodha_connect_script", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        msg = "Unable to load zerodha_connect.py"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _RELEVANT_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "kite-secret")


def _session(access_token: str | None = None) -> ZerodhaSession:
    token = access_token if access_token is not None else "token-live"
    return ZerodhaSession(
        api_key="kite-key",
        access_token=token,
        user_id="AB1234",
        user_name="Trader",
        user_email="trader@example.com",
        available_balance=Decimal("100.25"),
        connected_at_utc=datetime.now(UTC),
    )


def test_resolve_request_token_prefers_explicit_token() -> None:
    module = _load_script_module()
    resolved = module._resolve_request_token("req-direct", "")
    assert resolved == "req-direct"


def test_resolve_request_token_extracts_status_first_url() -> None:
    module = _load_script_module()
    redirect = "https://localhost/callback?status=success&request_token=req-xyz"
    resolved = module._resolve_request_token("", redirect)
    assert resolved == "req-xyz"


def test_resolve_request_token_rejects_split_status_only_url() -> None:
    module = _load_script_module()
    with pytest.raises(ConfigError, match="incomplete or was split"):
        module._resolve_request_token("", "https://localhost/callback?status=success")


def test_main_uses_valid_same_day_access_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    today = datetime.now(UTC).date().isoformat()
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token-today")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN_DATE_UTC", today)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    calls: list[tuple[str | None, str | None]] = []
    session = _session("token-today")

    class FakeTokenManager:
        def __init__(
            self,
            *,
            api_key: str,
            api_secret: str,
            totp_secret: str | None = None,
            http_post: Any = None,
        ) -> None:
            _ = api_key, api_secret, totp_secret, http_post

        def is_token_fresh(self) -> bool:
            return True

        def get_access_token(
            self, *, use_env_fallback: bool = True, refresh_if_expired: bool = False
        ) -> str | None:
            return "token-today"

        def store_access_token(self, token: str) -> None:
            pass

    class FakeConnection:
        @classmethod
        def from_env(cls) -> FakeConnection:
            return cls()

        def login_url(self) -> str:
            return "https://kite.zerodha.com/connect/login?api_key=kite-key"

        def establish_session(
            self,
            *,
            request_token: str | None = None,
            access_token: str | None = None,
        ) -> ZerodhaSession:
            calls.append((request_token, access_token))
            return session

    fake_token_manager = FakeTokenManager(api_key="kite-key", api_secret="kite-secret")
    monkeypatch.setattr(module, "ZerodhaTokenManager", lambda **kwargs: fake_token_manager)
    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        ["--env-file", str(env_path), "--no-auto-login", "--save-access-token"],
    )
    assert exit_code == 0
    assert calls == [(None, "token-today")]
