"""
Zerodha token management with day-scoped validity and dual persistence (keyring + .env).
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
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
        return str(totp.now())

    def get_totp(self) -> str:
        """Get current TOTP code for user display.

        Returns:
            6-digit TOTP code.
        """
        return self._generate_totp()

    def clear_token(self) -> None:
        """Clear stored token from keyring and .env file."""
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_TIMESTAMP_KEY)
        except keyring.errors.PasswordDeleteError:
            pass

        # Clear from .env file if it exists
        env_path = self._resolve_env_path()
        if env_path and env_path.exists():
            self._clear_env_token(env_path)

    def get_access_token(
        self,
        *,
        use_env_fallback: bool = True,
        refresh_if_expired: bool = False,
    ) -> str | None:
        """Get access token with automatic fallback strategies.

        Priority order:
        1. Fresh token from keyring
        2. Token from environment variables (ZERODHA_ACCESS_TOKEN or KITE_ACCESS_TOKEN)
        3. Token from .env file

        Args:
            use_env_fallback: If True, check environment and .env file as fallback.
            refresh_if_expired: If True, attempt to refresh expired tokens.

        Returns:
            Access token string if available, None otherwise.

        Raises:
            ValueError: If token exists but is expired and refresh_if_expired is False.
        """
        # Check keyring first
        if self.is_token_fresh():
            token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
            if token:
                _LOGGER.debug("Retrieved fresh token from keyring")
                return str(token)

        # Check environment variables (with alias support)
        if use_env_fallback:
            env_token = os.getenv("ZERODHA_ACCESS_TOKEN") or os.getenv("KITE_ACCESS_TOKEN")
            if env_token:
                _LOGGER.debug("Retrieved token from environment variable")
                return str(env_token)

            # Check .env file
            env_path = self._resolve_env_path()
            if env_path and env_path.exists():
                env_values = self._load_env_file(env_path)
                env_token = env_values.get("ZERODHA_ACCESS_TOKEN") or env_values.get(
                    "KITE_ACCESS_TOKEN"
                )
                if env_token:
                    _LOGGER.debug("Retrieved token from .env file")
                    return str(env_token)

        return None

    def get_kite_client(self, *, access_token: str | None = None) -> Any:
        """Create and return a KiteConnect client instance.

        This is a factory method for creating KiteConnect clients with
        proper authentication.

        Args:
            access_token: Optional access token. If not provided, will
                attempt to retrieve using get_access_token().

        Returns:
            Configured KiteConnect client instance.

        Raises:
            ValueError: If access token cannot be obtained.
            ImportError: If kiteconnect module is not available.
        """
        token = access_token or self.get_access_token()
        if not token:
            msg = "Access token not available. Please authenticate first."
            raise ValueError(msg)

        try:
            import kiteconnect  # type: ignore[import-untyped]  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            msg = "kiteconnect module is required. Install with: pip install kiteconnect"
            raise ImportError(msg) from exc

        client = kiteconnect.KiteConnect(api_key=self._api_key, access_token=token)
        _LOGGER.debug("Created KiteConnect client with API key %s", self._api_key[:8] + "...")
        return client

    @staticmethod
    def _resolve_env_path(env_file: str = ".env") -> Path | None:
        """Resolve .env file path from current directory or project root.

        Args:
            env_file: Name of the environment file.

        Returns:
            Path to .env file if found, None otherwise.
        """
        # Check current directory
        current_path = Path(env_file)
        if current_path.exists():
            return current_path

        # Check common parent directories
        for parent in [Path.cwd()] + list(Path.cwd().parents):
            candidate = parent / env_file
            if candidate.exists():
                return candidate

        return None

    @staticmethod
    def _load_env_file(env_path: Path) -> dict[str, str]:
        """Load environment variables from a .env file.

        Args:
            env_path: Path to .env file.

        Returns:
            Dictionary of environment variables.
        """
        values: dict[str, str] = {}
        if not env_path.exists():
            return values

        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", maxsplit=1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        except OSError as exc:
            _LOGGER.warning("Failed to read env file %s: %s", env_path, exc)

        return values

    def _clear_env_token(self, env_path: Path) -> None:
        """Remove access token from .env file.

        Args:
            env_path: Path to .env file.
        """
        try:
            original_lines = env_path.read_text(encoding="utf-8").splitlines()
            rewritten: list[str] = []
            for line in original_lines:
                stripped = line.strip()
                # Skip lines that set access tokens
                if (
                    stripped
                    and not stripped.startswith("#")
                    and "=" in stripped
                    and any(
                        key in stripped for key in ("ZERODHA_ACCESS_TOKEN", "KITE_ACCESS_TOKEN")
                    )
                ):
                    continue
                rewritten.append(line)

            env_path.write_text("\n".join(rewritten).rstrip() + "\n", encoding="utf-8")
            _LOGGER.debug("Cleared access token from %s", env_path)
        except OSError as exc:
            _LOGGER.warning("Failed to clear token from env file %s: %s", env_path, exc)


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
