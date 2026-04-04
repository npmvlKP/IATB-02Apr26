from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import ZerodhaSession

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


def test_saved_access_token_is_rejected_when_date_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script_module()
    stale_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token-old")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN_DATE_UTC", stale_date)
    assert module._resolve_saved_access_token() is None


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

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        ["--env-file", str(env_path), "--no-auto-login", "--save-access-token"],
    )
    assert exit_code == 0
    assert calls == [(None, "token-today")]


def test_main_uses_auto_login_when_saved_token_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    stale_date = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token-old")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN_DATE_UTC", stale_date)
    monkeypatch.setenv("ZERODHA_REDIRECT_URL", "http://localhost:5000/callback")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=token-old",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={stale_date}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    calls: list[tuple[str | None, str | None]] = []
    session = _session("token-new")

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
            if access_token is not None:
                raise ConfigError("HTTP Error 403: Forbidden")
            return session

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    monkeypatch.setattr(
        module,
        "_auto_acquire_request_token",
        lambda *args, **kwargs: "req-fresh",
    )
    exit_code = module.main(["--env-file", str(env_path), "--save-access-token", "--auto-login"])
    assert exit_code == 0
    assert calls == [("req-fresh", None)]
    persisted = env_path.read_text(encoding="utf-8")
    assert "ZERODHA_ACCESS_TOKEN=token-new" in persisted
    assert "ZERODHA_REQUEST_TOKEN=req-fresh" in persisted
    assert "BROKER_OAUTH_2FA_VERIFIED=true" in persisted


def test_main_returns_login_required_when_auto_capture_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )

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
            _ = request_token, access_token
            msg = "should not be called"
            raise AssertionError(msg)

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    monkeypatch.setattr(module, "_auto_acquire_request_token", lambda *args, **kwargs: None)
    exit_code = module.main(["--env-file", str(env_path), "--auto-login"])
    assert exit_code == 2
