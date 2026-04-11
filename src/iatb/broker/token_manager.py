"""Zerodha token lifecycle management with keyring persistence and freshness detection."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

import keyring
import pyotp
import pytz
from kiteconnect import KiteConnect

logger = logging.getLogger("iatb.broker.token_manager")

_IST = pytz.timezone("Asia/Kolkata")
_TOKEN_EXPIRY_TIME = time(6, 0, 0)  # 6 AM IST


class ZerodhaTokenManager:
    """Manages Zerodha access token lifecycle with freshness detection."""

    def __init__(self) -> None:
        """Initialize token manager."""
        self._api_key: str | None = None
        self._api_secret: str | None = None
        self._totp_secret: str | None = None

    def _load_credentials(self) -> None:
        """Load Zerodha credentials from keyring."""
        if self._api_key is None:
            self._api_key = keyring.get_password("iatb", "zerodha_api_key")
        if self._api_secret is None:
            self._api_secret = keyring.get_password("iatb", "zerodha_api_secret")
        if self._totp_secret is None:
            self._totp_secret = keyring.get_password("iatb", "zerodha_totp_secret")

    def is_token_fresh(self) -> bool:
        """Check if stored access token is fresh (not expired at 6 AM IST)."""
        self._load_credentials()
        if not self._api_key:
            logger.warning("API key not found in keyring")
            return False

        token = keyring.get_password("iatb", "zerodha_access_token")
        if not token:
            logger.debug("No access token found in keyring")
            return False

        timestamp_str = keyring.get_password("iatb", "zerodha_token_timestamp")
        if not timestamp_str:
            logger.warning("Token timestamp not found, treating as expired")
            return False

        try:
            stored_time = datetime.fromisoformat(timestamp_str)
        except ValueError as exc:
            logger.error("Invalid token timestamp format: %s", exc)
            return False

        return self._is_fresh(stored_time)

    def _is_fresh(self, stored_time: datetime) -> bool:
        """Check if token is still fresh based on 6 AM IST expiry."""
        if stored_time.tzinfo is None:
            stored_time = stored_time.replace(tzinfo=UTC)
        now_utc = datetime.now(UTC)

        now_ist = now_utc.astimezone(_IST)
        stored_ist = stored_time.astimezone(_IST)

        last_6am = _IST.localize(
            datetime.combine(now_ist.date(), _TOKEN_EXPIRY_TIME),
        )
        if now_ist.time() < _TOKEN_EXPIRY_TIME:
            last_6am = last_6am - timedelta(days=1)

        return stored_ist >= last_6am

    def get_login_url(self) -> str:
        """Return Zerodha OAuth login URL."""
        self._load_credentials()
        if not self._api_key:
            msg = "API key not found in keyring"
            raise RuntimeError(msg)
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={self._api_key}"

    def exchange_request_token(self, request_token: str) -> str:
        """Exchange request token for access token via KiteConnect API."""
        self._load_credentials()
        if not self._api_key or not self._api_secret:
            msg = "API credentials not found in keyring"
            raise RuntimeError(msg)

        kite = KiteConnect(api_key=self._api_key)
        try:
            data: dict[str, Any] = kite.generate_session(
                request_token=request_token,
                api_secret=self._api_secret,
            )
        except Exception as exc:
            logger.error("Failed to exchange request token: %s", exc)
            raise RuntimeError(f"Token exchange failed: {exc}") from exc

        access_token = data.get("access_token")
        if not access_token:
            msg = "No access_token in KiteConnect response"
            raise RuntimeError(msg)

        logger.info("Successfully exchanged request token for access token")
        return str(access_token)

    def store_access_token(self, token: str) -> None:
        """Persist access token to keyring with ISO timestamp."""
        timestamp = datetime.now(UTC).isoformat()
        keyring.set_password("iatb", "zerodha_access_token", token)
        keyring.set_password("iatb", "zerodha_token_timestamp", timestamp)
        logger.info("Access token stored in keyring with timestamp %s", timestamp)

    def generate_totp(self) -> str:
        """Generate TOTP code for display to user."""
        self._load_credentials()
        if not self._totp_secret:
            msg = "TOTP secret not found in keyring"
            raise RuntimeError(msg)

        totp = pyotp.TOTP(self._totp_secret)
        return totp.now()
