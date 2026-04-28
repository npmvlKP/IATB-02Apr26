"""
Zerodha token management with day-scoped validity and secure keyring persistence.

This module provides a unified token manager that handles both REST API and
scan pipeline use cases with 6 AM IST token expiry detection and secure storage.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
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
_KEYRING_REQUEST_TOKEN = (  # noqa: S105  # nosec B105  # Keyring identifier, not a password
    "request_token"  # noqa: S105  # nosec B105  # Keyring identifier, not a password
)
_KEYRING_REQUEST_TOKEN_DATE = (  # noqa: S105  # nosec B105  # Keyring identifier, not a password
    "request_token_date_utc"  # noqa: S105  # nosec B105  # Keyring identifier, not a password
)
_KEYRING_BROKER_VERIFIED = "broker_oauth_2fa_verified"
_ZERODHA_EXPIRY_HOUR = 6  # 6 AM IST
_ZERODHA_EXPIRY_MINUTE = 0
_LOGIN_BASE_URL = "https://kite.zerodha.com"


class ZerodhaTokenManager:
    """Manages Zerodha access token lifecycle with freshness detection.

    This unified token manager handles both REST API and scan pipeline use cases:
    - Secure keyring storage for production
    - 6 AM IST token expiry detection
    - TOTP-based automated re-login
    - Session token persistence for scan pipelines
    - Fallback to .env file for development
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        totp_secret: str | None = None,
        http_post: (
            Callable[[str, Mapping[str, str], bytes | None], Mapping[str, Any]] | None
        ) = None,
        env_path: Path | None = None,
        env_values: Mapping[str, str] | None = None,
        today_utc: date | None = None,
    ) -> None:
        """Initialize token manager.

        Args:
            api_key: Zerodha API key.
            api_secret: Zerodha API secret.
            totp_secret: TOTP secret for 2FA (optional).
            http_post: HTTP POST function for API calls (optional, for testing).
            env_path: Path to .env file for session persistence (optional).
            env_values: Environment values dict for session persistence (optional).
            today_utc: Current UTC date for testing (optional).
        """
        self._api_key = api_key
        self._api_secret = api_secret
        self._totp_secret = totp_secret
        self._http_post = http_post or _default_http_post
        self._env_path = env_path
        self._env_values = dict(env_values) if env_values else {}
        self._today_utc = today_utc or _utc_today()
        self._token_store_path = self._resolve_token_store_path(env_path) if env_path else None
        self._token_store_values = (
            _load_env_file(self._token_store_path)
            if self._token_store_path and self._token_store_path != self._env_path
            else self._env_values
        )

    @property
    def token_store_path(self) -> Path | None:
        """Get the path to the token store file."""
        return self._token_store_path

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

    def is_token_valid_for_pre_market(self) -> bool:
        """Check if token is valid for pre-market trading (before 9 AM IST).

        Pre-market trading starts at 9 AM IST. This method checks if the token
        will be valid at least until 9 AM IST today.

        Returns:
            True if token is valid for pre-market, False otherwise.
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
        pre_market_time = _get_pre_market_utc(token_time)
        return now_utc < pre_market_time

    def should_refresh_token(self, buffer_minutes: int = 30) -> bool:
        """Check if token should be refreshed before expiry.

        Args:
            buffer_minutes: Minutes before expiry to trigger refresh.

        Returns:
            True if token should be refreshed, False otherwise.
        """
        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
        if not token:
            return True
        timestamp_str = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TIMESTAMP_KEY)
        if not timestamp_str:
            return True
        try:
            token_time = datetime.fromisoformat(timestamp_str)
        except ValueError:
            _LOGGER.error("Invalid token timestamp in keyring")
            return True
        now_utc = datetime.now(UTC)
        expiry_time = _get_next_expiry_utc(token_time)
        time_until_expiry = expiry_time - now_utc
        return time_until_expiry <= timedelta(minutes=buffer_minutes)

    def auto_refresh_token(self) -> str | None:
        """Automatically refresh token using TOTP if available.

        This method checks if the token needs refresh and attempts to
        refresh it using the stored TOTP secret.

        Returns:
            New access token if refresh successful, None otherwise.

        Raises:
            ValueError: If TOTP secret not configured or refresh fails.
        """
        if not self.should_refresh_token():
            _LOGGER.debug("Token does not need refresh")
            return None

        if not self._totp_secret:
            msg = "TOTP secret not configured for auto-refresh"
            _LOGGER.warning(msg)
            raise ValueError(msg)

        _LOGGER.info("Attempting automatic token refresh with TOTP")

        try:
            self._generate_totp()
            _LOGGER.debug("Generated TOTP code for auto-refresh")

            request_token = self.resolve_saved_request_token()
            if not request_token:
                msg = "No saved request token available for auto-refresh"
                _LOGGER.warning(msg)
                raise ValueError(msg)

            new_access_token = self.exchange_request_token(request_token)
            self.store_access_token(new_access_token)
            _LOGGER.info("Token auto-refresh successful")

            return new_access_token
        except Exception as exc:
            _LOGGER.error("Token auto-refresh failed: %s", exc)
            raise

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
            ValueError: If API call fails.
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

        Raises:
            ValueError: If TOTP secret not configured.
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

        Raises:
            ValueError: If TOTP secret not configured.
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

    def resolve_saved_access_token(self) -> str | None:
        """Resolve saved access token with day-scoped validity check.

        This method is used by scan pipelines to reuse tokens within the same
        UTC day. It checks both keyring and .env file storage.

        Returns:
            Access token if valid for current UTC day, None otherwise.
        """
        # First check keyring (production path)
        if self.is_token_fresh():
            token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
            if token:
                _LOGGER.debug("Retrieved fresh access token from keyring")
                return str(token)

        # Fall back to .env file (development/scan path)
        if self._token_store_path and self._token_store_path.exists():
            token = self._token_store_values.get(
                "ZERODHA_ACCESS_TOKEN"
            ) or self._token_store_values.get("KITE_ACCESS_TOKEN")
            if token:
                token_date = self._token_store_values.get("ZERODHA_ACCESS_TOKEN_DATE_UTC")
                if token_date and self._is_today(token_date):
                    _LOGGER.debug("Retrieved valid access token from .env file")
                    return str(token)

        return None

    def resolve_saved_request_token(self) -> str | None:
        """Resolve saved request token with day-scoped validity check.

        This method is used by scan pipelines to reuse request tokens within
        the same UTC day for OAuth flow continuation.

        Returns:
            Request token if valid for current UTC day, None otherwise.
        """
        # Check keyring first
        request_token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_REQUEST_TOKEN)
        if request_token:
            request_date = keyring.get_password(_KEYRING_SERVICE, _KEYRING_REQUEST_TOKEN_DATE)
            if request_date and self._is_today(request_date):
                _LOGGER.debug("Retrieved valid request token from keyring")
                return str(request_token)

        # Fall back to .env file
        if self._token_store_path and self._token_store_path.exists():
            token = self._token_store_values.get("ZERODHA_REQUEST_TOKEN")
            if token:
                token_date = self._token_store_values.get("ZERODHA_REQUEST_TOKEN_DATE_UTC")
                if token_date and self._is_today(token_date):
                    _LOGGER.debug("Retrieved valid request token from .env file")
                    return str(token)

        return None

    def persist_session_tokens(
        self,
        *,
        access_token: str,
        request_token: str | None = None,
    ) -> Path | None:
        """Persist session tokens to both keyring and .env file.

        This method stores tokens with UTC date stamps for day-scoped validity
        checking. Used by scan pipelines to enable token reuse.

        Args:
            access_token: The access token to persist.
            request_token: Optional request token to persist.

        Returns:
            Path to .env file if written, None if only keyring was used.

        Raises:
            ValueError: If env_path is not configured for .env persistence.
        """
        today = self._today_utc.isoformat()

        # Always store in keyring (production path)
        self.store_access_token(access_token)
        if request_token:
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_REQUEST_TOKEN, request_token)
            keyring.set_password(_KEYRING_SERVICE, _KEYRING_REQUEST_TOKEN_DATE, today)
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_BROKER_VERIFIED, "true")
        _LOGGER.info("Tokens persisted to keyring")

        # Also store in .env file if configured (scan pipeline path)
        if self._token_store_path:
            updates = {
                "ZERODHA_ACCESS_TOKEN": access_token,
                "ZERODHA_ACCESS_TOKEN_DATE_UTC": today,
                "BROKER_OAUTH_2FA_VERIFIED": "true",
            }
            if request_token:
                updates["ZERODHA_REQUEST_TOKEN"] = request_token
                updates["ZERODHA_REQUEST_TOKEN_DATE_UTC"] = today

            _persist_env_updates(self._token_store_path, updates)
            self._token_store_values.update(updates)
            _LOGGER.info("Tokens persisted to %s", self._token_store_path)
            return self._token_store_path

        return None

    def _is_today(self, date_text: str) -> bool:
        """Check if a date string matches today's UTC date.

        Args:
            date_text: Date string in ISO format.

        Returns:
            True if date matches today, False otherwise.
        """
        normalized = date_text.strip()
        if not normalized:
            return False
        try:
            return date.fromisoformat(normalized) == self._today_utc
        except ValueError:
            return False

    @staticmethod
    def _resolve_env_path(env_file: str = ".env") -> Path | None:
        """Resolve .env file path from current directory or project root.

        Args:
            env_file: Name of the environment file.

        Returns:
            Path to .env file if found, None otherwise.
        """
        # Check current directory
        current_path = Path.cwd() / env_file
        if current_path.exists():
            return current_path

        # Check common parent directories
        for parent in Path.cwd().parents:
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
        return _load_env_file(env_path)

    @staticmethod
    def _clear_env_token(env_path: Path) -> None:
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

    @staticmethod
    def _resolve_token_store_path(env_path: Path) -> Path:
        """Resolve the actual token store path.

        If the provided env_path is an .example file, the actual store
        will be the corresponding .env file.

        Args:
            env_path: Provided environment file path.

        Returns:
            Resolved token store path.
        """
        if env_path.name.endswith(".example"):
            return env_path.with_name(".env")
        return env_path


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


def _persist_env_updates(env_path: Path, updates: Mapping[str, str]) -> None:
    """Persist environment variable updates to a file.

    Args:
        env_path: Path to .env file.
        updates: Dictionary of key-value pairs to update.
    """
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
    """Get current UTC date.

    Returns:
        Current UTC date.
    """
    return datetime.now(UTC).date()


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


def _get_pre_market_utc(token_time: datetime) -> datetime:
    """Calculate next 9 AM IST pre-market time in UTC.

    Args:
        token_time: Token creation time.

    Returns:
        Next pre-market time in UTC.
    """
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    ist_tz = ZoneInfo("Asia/Kolkata")
    token_ist = token_time.astimezone(ist_tz)
    pre_market_hour = 9
    pre_market_minute = 0
    pre_market_ist = datetime.combine(
        token_ist.date(),
        time(hour=pre_market_hour, minute=pre_market_minute),
        tzinfo=ist_tz,
    )
    if token_ist < pre_market_ist:
        return pre_market_ist.astimezone(UTC)
    return (pre_market_ist + timedelta(days=1)).astimezone(UTC)


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
