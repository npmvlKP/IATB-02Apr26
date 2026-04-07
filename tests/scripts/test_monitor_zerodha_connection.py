from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.exceptions import ConfigError
from iatb.execution.zerodha_connection import ZerodhaSession

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "monitor_zerodha_connection.py"
_RELEVANT_ENV_VARS = (
    "ZERODHA_API_KEY",
    "ZERODHA_API_SECRET",
    "ZERODHA_ACCESS_TOKEN",
    "ZERODHA_ACCESS_TOKEN_DATE_UTC",
    "ZERODHA_REQUEST_TOKEN",
    "ZERODHA_REQUEST_TOKEN_DATE_UTC",
    "BROKER_OAUTH_2FA_VERIFIED",
)


def _load_script_module() -> object:
    spec = importlib.util.spec_from_file_location("monitor_zerodha_connection_script", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        msg = "Unable to load monitor_zerodha_connection.py"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _RELEVANT_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "kite-secret")


def _session(access_token: str | None = None) -> ZerodhaSession:
    token_value = access_token if access_token is not None else "token-live"
    return ZerodhaSession(
        api_key="kite-key",
        access_token=token_value,
        user_id="AB1234",
        user_name="Trader",
        user_email="trader@example.com",
        available_balance=Decimal("100.25"),
        connected_at_utc=datetime.now(UTC),
    )


def test_main_once_reports_connected_with_saved_access_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    today = datetime.now(UTC).date().isoformat()
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
    log_path = tmp_path / "monitor.log"
    calls: list[tuple[str | None, str | None]] = []

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
            return _session("token-today")

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--once",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 0
    assert calls == [(None, "token-today")]
    log_text = log_path.read_text(encoding="utf-8")
    assert "status=CONNECTED" in log_text


def test_main_once_returns_login_required_without_tokens(
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
    log_path = tmp_path / "monitor.log"

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
            msg = "establish_session should not be called"
            raise AssertionError(msg)

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--once",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 2
    log_text = log_path.read_text(encoding="utf-8")
    assert "status=LOGIN_REQUIRED" in log_text


def test_main_once_logs_api_error_for_non_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    today = datetime.now(UTC).date().isoformat()
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
    log_path = tmp_path / "monitor.log"

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
            msg = (
                "Zerodha API request failed for /user/profile: "
                "HTTP Error 500: Internal Server Error"
            )
            raise ConfigError(msg)

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--once",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 1
    log_text = log_path.read_text(encoding="utf-8")
    assert "status=API_ERROR" in log_text


def test_main_periodic_runs_max_checks_and_sleeps_between_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_script_module()
    _seed_required_env(monkeypatch)
    today = datetime.now(UTC).date().isoformat()
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
    log_path = tmp_path / "monitor.log"
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
            _ = request_token, access_token
            return _session("token-today")

    monkeypatch.setattr(module, "ZerodhaConnection", FakeConnection)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    exit_code = module.main(
        [
            "--env-file",
            str(env_path),
            "--max-checks",
            "2",
            "--interval-seconds",
            "7",
            "--log-file",
            str(log_path),
        ],
    )
    assert exit_code == 0
    assert sleep_calls == [7.0]
    log_text = log_path.read_text(encoding="utf-8")
    assert log_text.count("status=CONNECTED") == 2
