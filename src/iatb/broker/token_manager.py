"""
Zerodha token management with day-scoped validity and keyring persistence.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import urlencode

import keyring

_LOGGER = logging.getLogger(__name__)
_KEYRING_SERVICE = "iatb_zerodha"
_KEYRING_TOKEN_KEY = "access_token"  # noqa: S105  # nosec B105  # Keyring identifier, not a password
_KEYRING_TIMESTAMP_KEY = "token_timestamp_utc"
_KEYRING_API_KEY = "api_key"
_KEYRING_API_SECRET = "api_secret"  # noqa: S105  # nosec B105  # Keyring identifier, not a password
_KEYRING_TOTP_SECRET = "totp_secret"  # noqa: S105  # nosec B105  # Keyring identifier, not a password
_ZERODHA_EXPIRY_HOUR = 6  # 6 AM IST
_ZERODHA_EXPIRY_MINUTE = 0
_LOGIN_BASE_URL = "https://kite.zerodha.com"


class ZerodhaTokenManager:
    """Manages Zerodha access token lifecycle with freshness detection."""

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        totp_secret: str | None = None,
        http_post: (
            Callable[[str, Mapping[str, str], bytes | None], Mapping[str, Any]] | None
        ) = None,
    ) -> None:
        """Initialize token manager.

        Args:
            api_key: Zerodha API key.
            api_secret: Zerodha API secret.
            totp_secret: TOTP secret for 2FA (optional).
            http_post: HTTP POST function for API calls (optional, for testing).
        """
        self._api_key = api_key
        self._api_secret = api_secret
        self._totp_secret = totp_secret
        self._http_post = http_post or _default_http_post

    def is_token_fresh(self) -> bool:
        """Check if stored token is fresh (not expired past 6 AM IST).

        Returns:
            True if token is fresh, False otherwise.
        """
        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
        if not token:
            return False
        timestamp_str = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TIMESTAMP_KEY)
        if not timestamp_str:
            return False
        try:
            token_time = datetime.fromisoformat(timestamp_str)
        except ValueError:
            _LOGGER.error("Invalid token timestamp in keyring")
            return False
        now_utc = datetime.now(UTC)
        expiry_time = _get_next_expiry_utc(token_time)
        return now_utc < expiry_time

    def get_login_url(self) -> str:
        """Return Zerodha OAuth login URL.

        Returns:
            Login URL with API key.
        """
        return f"{_LOGIN_BASE_URL}/connect/login?v=3&api_key={self._api_key}"

    def exchange_request_token(self, request_token: str) -> str:
        """Exchange request token for access token via KiteConnect API.

        Args:
            request_token: Request token from OAuth callback.

        Returns:
            Access token string.

        Raises:
            ConfigError: If API call fails.
        """
        checksum = hashlib.sha256(
            f"{self._api_key}{request_token}{self._api_secret}".encode(),
        ).hexdigest()
        payload = {
            "api_key": self._api_key,
            "request_token": request_token,
            "checksum": checksum,
        }
        url = f"{_LOGIN_BASE_URL}/api/session/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = urlencode(payload).encode()
        response = self._http_post(url, headers, body)
        data = response.get("data", {})
        access_token = data.get("access_token")
        if not access_token:
            msg = "No access_token in API response"
            raise ValueError(msg)
        return str(access_token)

    def store_access_token(self, token: str) -> None:
        """Persist access token to keyring with timestamp.

        Args:
            token: Access token to store.
        """
        timestamp_utc = datetime.now(UTC).isoformat()
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY, token)
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_TIMESTAMP_KEY, timestamp_utc)
        _LOGGER.info("Access token stored with timestamp %s", timestamp_utc)

    def _generate_totp(self) -> str:
        """Generate TOTP code using pyotp.

        Returns:
            6-digit TOTP code.
        """
        if not self._totp_secret:
            msg = "TOTP secret not configured"
            raise ValueError(msg)
        import pyotp  # noqa: PLC0415

        totp = pyotp.TOTP(self._totp_secret)
        return totp.now()

    def get_totp(self) -> str:
        """Get current TOTP code for user display.

        Returns:
            6-digit TOTP code.
        """
        return self._generate_totp()

    def clear_token(self) -> None:
        """Clear stored token from keyring."""
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_TIMESTAMP_KEY)
        except keyring.errors.PasswordDeleteError:
            pass


def _get_next_expiry_utc(token_time: datetime) -> datetime:
    """Calculate next 6 AM IST expiry time in UTC.

    Args:
        token_time: Token creation time.

    Returns:
        Next expiry time in UTC.
    """
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    ist_tz = ZoneInfo("Asia/Kolkata")
    token_ist = token_time.astimezone(ist_tz)
    expiry_ist = datetime.combine(
        token_ist.date(),
        time(hour=_ZERODHA_EXPIRY_HOUR, minute=_ZERODHA_EXPIRY_MINUTE),
        tzinfo=ist_tz,
    )
    if token_ist < expiry_ist:
        return expiry_ist.astimezone(UTC)
    return (expiry_ist + timedelta(days=1)).astimezone(UTC)


def _default_http_post(
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> Mapping[str, Any]:  # noqa: S310  # nosec B310
    """Default HTTP POST implementation.

    URL is validated to be HTTPS-only before opening.

    Args:
        url: Request URL.
        headers: Request headers.
        body: Request body.

    Returns:
        JSON response as dict.

    Raises:
        ValueError: If URL is not HTTPS.
    """
    import json  # noqa: PLC0415
    from typing import cast  # noqa: PLC0415

    # Validate URL scheme to ensure HTTPS only
    if not url.startswith("https://"):
        msg = f"Only HTTPS URLs are allowed, got: {url}"
        raise ValueError(msg)

    from urllib.request import Request, urlopen

    req = Request(url=url, data=body, headers=dict(headers), method="POST")  # noqa: S310  # nosec B310  # URL validated as HTTPS-only above
    with urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310  # URL validated as HTTPS-only above
        raw = resp.read().decode("utf-8")
    return cast(Mapping[str, Any], json.loads(raw))
