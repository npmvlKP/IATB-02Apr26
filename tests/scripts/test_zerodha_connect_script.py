from __future__ import annotations

import importlib.util
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

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


def test_main_persists_to_dotenv_when_env_file_is_example(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    env_example_path = tmp_path / ".env.example"
    env_example_path.write_text(
        "ZERODHA_API_KEY=kite-key\nZERODHA_API_SECRET=kite-secret\n",
        encoding="utf-8",
    )
    session = _session("token-persisted")

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
            _ = access_token
            assert request_token == "req-fresh"  # noqa: S105
            return session

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_example_path),
            "--save-access-token",
            "--request-token",
            "req-fresh",
            "--no-auto-login",
        ],
    )
    assert exit_code == 0
    persisted_path = tmp_path / ".env"
    persisted = persisted_path.read_text(encoding="utf-8")
    assert "ZERODHA_ACCESS_TOKEN=token-persisted" in persisted
    assert "ZERODHA_REQUEST_TOKEN=req-fresh" in persisted
    assert "BROKER_OAUTH_2FA_VERIFIED=true" in persisted
    assert "token-persisted" not in env_example_path.read_text(encoding="utf-8")


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


def test_main_reconnects_and_succeeds_after_transient_access_token_errors(
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
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=token-today",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    calls: list[tuple[str | None, str | None]] = []
    sleep_calls: list[float] = []
    session = _session("token-recovered")

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
            if len(calls) < 3:
                msg = (
                    "Zerodha API request failed for /user/profile: "
                    "HTTP Error 503: Service Unavailable"
                )
                raise ConfigError(msg)
            return session

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--no-auto-login",
            "--max-reconnect-attempts",
            "3",
            "--reconnect-delay-seconds",
            "1",
        ],
    )
    assert exit_code == 0
    assert calls == [
        (None, "token-today"),
        (None, "token-today"),
        (None, "token-today"),
    ]
    assert sleep_calls == [1.0, 2.0]


def test_main_returns_blocked_when_transient_errors_exhaust_reconnect_attempts(
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
        "\n".join(
            (
                "ZERODHA_API_KEY=kite-key",
                "ZERODHA_API_SECRET=kite-secret",
                "ZERODHA_ACCESS_TOKEN=token-today",
                f"ZERODHA_ACCESS_TOKEN_DATE_UTC={today}",
            ),
        )
        + "\n",
        encoding="utf-8",
    )
    calls: list[tuple[str | None, str | None]] = []
    sleep_calls: list[float] = []

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
            msg = (
                "Zerodha API request failed for /user/profile: "
                "HTTP Error 503: Service Unavailable"
            )
            raise ConfigError(msg)

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--no-auto-login",
            "--max-reconnect-attempts",
            "2",
            "--reconnect-delay-seconds",
            "0",
        ],
    )
    assert exit_code == 1
    assert calls == [
        (None, "token-today"),
        (None, "token-today"),
    ]
    assert sleep_calls == []


def test_main_rejects_invalid_reconnect_attempt_count(
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
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--no-auto-login",
            "--max-reconnect-attempts",
            "0",
        ],
    )
    assert exit_code == 1


def test_main_writes_structured_logs_to_file_on_success(
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
    log_path = tmp_path / "zerodha_connect.log"
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
            _ = request_token, access_token
            return session

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--no-auto-login",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 0
    log_text = log_path.read_text(encoding="utf-8")
    assert "zerodha bootstrap started" in log_text
    assert "session established using saved access token" in log_text
    assert "zerodha bootstrap finished status=CONNECTED" in log_text


def test_main_returns_blocked_on_unexpected_access_token_exception(
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
    log_path = tmp_path / "zerodha_connect.log"

    class FakeTokenManager:
        def __init__(self, *, env_path: Path, env_values: dict[str, str]) -> None:
            _ = env_path, env_values

        def resolve_saved_access_token(self) -> str | None:
            msg = "unhandled token manager failure"
            raise RuntimeError(msg)

        def resolve_saved_request_token(self) -> str | None:
            return None

        def persist_session_tokens(
            self,
            *,
            access_token: str,
            request_token: str | None,
        ) -> Path:
            _ = access_token, request_token
            return Path(".env")

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

    monkeypatch.setattr(module, "ZerodhaTokenManager", FakeTokenManager)
    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--no-auto-login",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 1
    log_text = log_path.read_text(encoding="utf-8")
    assert "unexpected failure during access-token bootstrap" in log_text
