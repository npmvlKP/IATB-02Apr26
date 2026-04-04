"""
Zerodha token lifecycle management with day-scoped validity and persistence.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

_ACCESS_TOKEN_ENV = "ZERODHA_ACCESS_TOKEN"  # noqa: S105  # nosec B105
_ACCESS_TOKEN_DATE_ENV = "ZERODHA_ACCESS_TOKEN_DATE_UTC"  # noqa: S105  # nosec B105
_REQUEST_TOKEN_ENV = "ZERODHA_REQUEST_TOKEN"  # noqa: S105  # nosec B105
_REQUEST_TOKEN_DATE_ENV = "ZERODHA_REQUEST_TOKEN_DATE_UTC"  # noqa: S105  # nosec B105
_BROKER_VERIFIED_ENV = "BROKER_OAUTH_2FA_VERIFIED"


def load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def apply_env_defaults(values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if value and key not in os.environ:
            os.environ[key] = value


def _persist_env_updates(env_path: Path, updates: Mapping[str, str]) -> None:
    original_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    rewritten: list[str] = []
    touched_keys: set[str] = set()
    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key, _ = line.split("=", maxsplit=1)
            normalized_key = key.strip()
            if normalized_key in updates:
                rewritten.append(f"{normalized_key}={updates[normalized_key]}")
                touched_keys.add(normalized_key)
                continue
        rewritten.append(line)
    for key, value in updates.items():
        if key not in touched_keys:
            rewritten.append(f"{key}={value}")
    env_path.write_text("\n".join(rewritten).rstrip() + "\n", encoding="utf-8")


def _utc_today() -> date:
    return datetime.now(UTC).date()


class ZerodhaTokenManager:
    """Manages day-scoped Zerodha token reuse and persistence."""

    def __init__(
        self,
        *,
        env_path: Path,
        env_values: Mapping[str, str],
        today_utc: date | None = None,
    ) -> None:
        self._env_path = env_path
        self._env_values = dict(env_values)
        self._today_utc = today_utc or _utc_today()
        self._token_store_path = self._resolve_token_store_path(env_path)
        self._token_store_values = (
            load_env_file(self._token_store_path)
            if self._token_store_path != self._env_path
            else self._env_values
        )

    @property
    def token_store_path(self) -> Path:
        return self._token_store_path

    def resolve_saved_access_token(self) -> str | None:
        return self._resolve_day_token(
            token_key=_ACCESS_TOKEN_ENV,
            date_key=_ACCESS_TOKEN_DATE_ENV,
        )

    def resolve_saved_request_token(self) -> str | None:
        return self._resolve_day_token(
            token_key=_REQUEST_TOKEN_ENV,
            date_key=_REQUEST_TOKEN_DATE_ENV,
        )

    def persist_session_tokens(
        self,
        *,
        access_token: str,
        request_token: str | None,
    ) -> Path:
        today = self._today_utc.isoformat()
        updates = {
            _ACCESS_TOKEN_ENV: access_token,
            _ACCESS_TOKEN_DATE_ENV: today,
            _BROKER_VERIFIED_ENV: "true",
        }
        if request_token:
            updates[_REQUEST_TOKEN_ENV] = request_token
            updates[_REQUEST_TOKEN_DATE_ENV] = today
        _persist_env_updates(self._token_store_path, updates)
        self._token_store_values.update(updates)
        return self._token_store_path

    def _resolve_day_token(self, *, token_key: str, date_key: str) -> str | None:
        token = self._read_value(token_key)
        if not token:
            return None
        token_date = self._read_value(date_key)
        if token_date and not self._is_today(token_date):
            return None
        return token

    def _read_value(self, key: str) -> str:
        env_value = os.getenv(key, "").strip()
        if env_value:
            return env_value
        if self._token_store_path != self._env_path:
            return self._token_store_values.get(key, "").strip()
        primary_value = self._env_values.get(key, "").strip()
        if primary_value:
            return primary_value
        return ""

    def _is_today(self, date_text: str) -> bool:
        normalized = date_text.strip()
        if not normalized:
            return False
        try:
            return date.fromisoformat(normalized) == self._today_utc
        except ValueError:
            return False

    @staticmethod
    def _resolve_token_store_path(env_path: Path) -> Path:
        if env_path.name.endswith(".example"):
            return env_path.with_name(".env")
        return env_path
