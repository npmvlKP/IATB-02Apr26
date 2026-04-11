"""
Zerodha broker connection management with secure token exchange.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from iatb.core.exceptions import ConfigError

_DEFAULT_TIMEOUT_SECONDS = 10
_DEFAULT_MAX_RETRIES = 3
# API boundary: retry delay is time-based, not financial calculation.
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_LOGIN_BASE_URL = "https://kite.zerodha.com"
_API_BASE_URL = "https://api.kite.trade"
_KITE_VERSION = "3"
_AUTHORIZATION_HEADER = "Authorization"
_KITE_VERSION_HEADER = "X-Kite-Version"
_AUTH_HEADER_TEMPLATE = "token {api_key}:{access_token}"
_REQUEST_TOKEN_PATTERN = re.compile(r"(?:^|[?&\\s])request_token=([^&\\s]+)")

HttpRequest = Callable[[str, str, Mapping[str, str], bytes | None, int], Mapping[str, object]]


@dataclass(frozen=True)
class ZerodhaSession:
    """Active Zerodha session details."""

    api_key: str
    access_token: str
    user_id: str
    user_name: str
    user_email: str
    available_balance: Decimal
    connected_at_utc: datetime


class ZerodhaConnection:
    """Handles Zerodha session creation and account verification."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        request_token: str | None = None,
        access_token: str | None = None,
        base_url: str = _API_BASE_URL,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        # API boundary: retry delay is time-based, not financial calculation.
        retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
        http_request: HttpRequest | None = None,
    ) -> None:
        self._api_key = _require_non_empty(api_key, field_name="api_key")
        self._api_secret = _require_non_empty(api_secret, field_name="api_secret")
        self._request_token = _normalize_optional_token(request_token)
        self._access_token = _normalize_optional_token(access_token)
        self._base_url = base_url.rstrip("/")
        _validate_http_url(self._base_url)
        if timeout_seconds <= 0:
            msg = "timeout_seconds must be positive"
            raise ConfigError(msg)
        if max_retries <= 0:
            msg = "max_retries must be positive"
            raise ConfigError(msg)
        if retry_delay_seconds < 0:
            msg = "retry_delay_seconds must be non-negative"
            raise ConfigError(msg)
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._http_request = http_request or _default_http_request

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env_var: str = "ZERODHA_API_KEY",
        api_secret_env_var: str = "ZERODHA_API_SECRET",  # noqa: S107
        request_token_env_var: str = "ZERODHA_REQUEST_TOKEN",  # noqa: S107
        access_token_env_var: str = "ZERODHA_ACCESS_TOKEN",  # noqa: S107
        base_url: str = _API_BASE_URL,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        # API boundary: retry delay is time-based, not financial calculation.
        retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
        http_request: HttpRequest | None = None,
    ) -> ZerodhaConnection:
        return cls(
            api_key=_required_env_var(api_key_env_var),
            api_secret=_required_env_var(api_secret_env_var),
            request_token=_optional_env_var(request_token_env_var),
            access_token=_optional_env_var(access_token_env_var),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            http_request=http_request,
        )

    def login_url(self) -> str:
        """Return OAuth login URL for obtaining request token."""
        query = urlencode({"v": "3", "api_key": self._api_key})
        return f"{_LOGIN_BASE_URL}/connect/login?{query}"

    def establish_session(
        self,
        *,
        request_token: str | None = None,
        access_token: str | None = None,
    ) -> ZerodhaSession:
        """Establish and verify a Zerodha session."""
        active_access_token = self._resolve_access_token(
            request_token=request_token,
            access_token=access_token,
        )
        user_id, user_name, user_email = self._fetch_profile_fields(active_access_token)
        available_balance = self._fetch_available_balance(active_access_token)
        return ZerodhaSession(
            api_key=self._api_key,
            access_token=active_access_token,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            available_balance=available_balance,
            connected_at_utc=datetime.now(UTC),
        )

    def _resolve_access_token(
        self,
        *,
        request_token: str | None,
        access_token: str | None,
    ) -> str:
        explicit_access_token = _normalize_optional_token(access_token)
        if explicit_access_token:
            return explicit_access_token
        explicit_request_token = _normalize_optional_token(request_token)
        if explicit_request_token:
            return self._exchange_request_token(explicit_request_token)
        if self._access_token:
            return self._access_token
        if self._request_token:
            return self._exchange_request_token(self._request_token)
        msg = (
            "Zerodha request token is required for session exchange. "
            "Complete OAuth login and set ZERODHA_REQUEST_TOKEN."
        )
        raise ConfigError(msg)

    def _exchange_request_token(self, request_token: str) -> str:
        checksum = hashlib.sha256(
            f"{self._api_key}{request_token}{self._api_secret}".encode(),
        ).hexdigest()
        payload = urlencode(
            {
                "api_key": self._api_key,
                "request_token": request_token,
                "checksum": checksum,
            },
        ).encode()
        response = self._request_json(
            path="/session/token",
            method="POST",
            headers=self._request_headers({"Content-Type": "application/x-www-form-urlencoded"}),
            body=payload,
        )
        data = _extract_data_mapping(response)
        return _extract_string(data, ("access_token",), field_name="access_token")

    def _fetch_profile_fields(self, access_token: str) -> tuple[str, str, str]:
        response = self._request_json(
            path="/user/profile",
            method="GET",
            headers=self._auth_headers(access_token),
            body=None,
        )
        data = _extract_data_mapping(response)
        user_id = _extract_string(data, ("user_id",), field_name="user_id")
        user_name = _extract_string(data, ("user_name", "user_shortname"), field_name="user_name")
        user_email = _extract_string(data, ("email",), field_name="email")
        return user_id, user_name, user_email

    def _fetch_available_balance(self, access_token: str) -> Decimal:
        response = self._request_json(
            path="/user/margins",
            method="GET",
            headers=self._auth_headers(access_token),
            body=None,
        )
        data = _extract_data_mapping(response)
        return _extract_available_balance(data)

    def _request_json(
        self,
        *,
        path: str,
        method: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> Mapping[str, object]:
        url = f"{self._base_url}{path}"
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._http_request(url, method, headers, body, self._timeout_seconds)
            except ConfigError:
                raise
            except (HTTPError, OSError, TimeoutError, URLError) as exc:
                if not _is_retryable_exception(exc) or attempt >= self._max_retries:
                    msg = f"Zerodha API request failed for {path}: {exc}"
                    raise ConfigError(msg) from exc
                if self._retry_delay_seconds > 0:
                    time.sleep(self._retry_delay_seconds * attempt)
        msg = f"Zerodha API request failed for {path}: exhausted retries"
        raise ConfigError(msg)

    def _auth_headers(self, access_token: str) -> dict[str, str]:
        token_value = _AUTH_HEADER_TEMPLATE.format(
            api_key=self._api_key,
            access_token=access_token,
        )
        return self._request_headers({_AUTHORIZATION_HEADER: token_value})

    @staticmethod
    def _request_headers(extra_headers: Mapping[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {_KITE_VERSION_HEADER: _KITE_VERSION}
        if extra_headers:
            headers.update(extra_headers)
        return headers


def extract_request_token_from_redirect_url(redirect_url: str) -> str:
    """Extract request_token from Zerodha login redirect URL."""
    parsed = urlparse(_normalize_redirect_text(redirect_url))
    if not parsed.query:
        msg = "redirect_url must include request_token query parameter"
        raise ConfigError(msg)
    values = parse_qs(parsed.query, keep_blank_values=False)
    token_values = values.get("request_token")
    if not token_values or not token_values[0].strip():
        msg = "redirect_url is missing request_token"
        raise ConfigError(msg)
    return token_values[0].strip()


def extract_request_token_from_text(text: str) -> str:
    """Extract request_token from URL, query fragment, or pasted redirect text."""
    normalized = _normalize_redirect_text(text)
    token = _match_request_token(normalized)
    if token is not None:
        return token
    return extract_request_token_from_redirect_url(normalized)


def _normalize_redirect_text(value: str) -> str:
    normalized = value.strip().strip('"').strip("'")
    return normalized.replace("&amp;", "&")


def _match_request_token(value: str) -> str | None:
    matched = _REQUEST_TOKEN_PATTERN.search(value)
    if not matched:
        return None
    token = unquote(matched.group(1)).strip()
    return token if token else None


def _required_env_var(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    msg = f"{name} is required"
    raise ConfigError(msg)


def _optional_env_var(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value if value else None


def _require_non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    msg = f"{field_name} cannot be empty"
    raise ConfigError(msg)


def _normalize_optional_token(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = "Zerodha base_url must use http or https"
        raise ConfigError(msg)
    if not parsed.netloc:
        msg = "Zerodha base_url must include host"
        raise ConfigError(msg)


def _extract_data_mapping(payload: Mapping[str, object]) -> Mapping[str, object]:
    status = str(payload.get("status", "success")).strip().lower()
    if status and status != "success":
        message = str(payload.get("message", "unknown API error")).strip()
        msg = f"Zerodha API rejected request: {message}"
        raise ConfigError(msg)
    data = payload.get("data")
    if isinstance(data, Mapping):
        return data
    msg = "Zerodha API response missing data mapping"
    raise ConfigError(msg)


def _extract_available_balance(payload: Mapping[str, object]) -> Decimal:
    for segment in ("equity", "commodity"):
        balance = _extract_segment_balance(payload, segment)
        if balance is not None:
            return balance
    msg = "Zerodha API response missing available balance in equity/commodity segments"
    raise ConfigError(msg)


def _extract_segment_balance(payload: Mapping[str, object], segment: str) -> Decimal | None:
    segment_data = payload.get(segment)
    if not isinstance(segment_data, Mapping):
        return None
    available_data = segment_data.get("available")
    if isinstance(available_data, Mapping):
        available_balance = _extract_decimal_optional(
            available_data,
            keys=("live_balance", "cash", "opening_balance"),
        )
        if available_balance is not None:
            return available_balance
    return _extract_decimal_optional(segment_data, keys=("net",))


def _extract_decimal_optional(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
) -> Decimal | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            msg = f"Zerodha API response field {key} must be numeric"
            raise ConfigError(msg)
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            msg = f"Zerodha API response field {key} must be numeric"
            raise ConfigError(msg) from exc
    return None


def _extract_string(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
    *,
    field_name: str,
) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    msg = f"Zerodha API response missing {field_name}"
    raise ConfigError(msg)


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code == 429 or exc.code >= 500
    if isinstance(exc, URLError):
        return True
    return isinstance(exc, TimeoutError | OSError)


def _default_http_request(
    url: str,
    method: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_seconds: int,
) -> Mapping[str, object]:
    request = Request(url=url, data=body, headers=dict(headers), method=method)  # noqa: S310  # nosec B310
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310  # nosec B310
        raw_payload = response.read().decode("utf-8")
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        msg = "Zerodha API response is not valid JSON"
        raise ConfigError(msg) from exc
    if not isinstance(decoded, Mapping):
        msg = "Zerodha API response must decode into JSON object"
        raise ConfigError(msg)
    return decoded
