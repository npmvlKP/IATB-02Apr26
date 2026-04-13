#!/usr/bin/env python
"""
iATB Automated Token Refresh Service — Background daemon for Zerodha token management.

This service runs in the background and:
  1. Checks token freshness every 5 minutes
  2. Triggers re-authentication when token expires (after 6 AM IST)
  3. Provides TOTP codes for assisted login
  4. Logs all token lifecycle events

Run:  poetry run python scripts/token_refresh_service.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# ── Logging Setup ──

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "token_refresh.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
_LOGGER = logging.getLogger("token_refresh")


# ── Token Management ──


class TokenRefreshService:
    """Background service for automated Zerodha token refresh."""

    def __init__(
        self,
        *,
        check_interval_seconds: int = 300,  # 5 minutes
        api_key: str | None = None,
        api_secret: str | None = None,
        totp_secret: str | None = None,
    ) -> None:
        """Initialize token refresh service.

        Args:
            check_interval_seconds: How often to check token freshness.
            api_key: Zerodha API key (from env if not provided).
            api_secret: Zerodha API secret (from env if not provided).
            totp_secret: TOTP secret for 2FA (from env if not provided).
        """
        self._check_interval = check_interval_seconds
        self._api_key = api_key or os.environ.get("KITE_API_KEY")
        self._api_secret = api_secret or os.environ.get("KITE_API_SECRET")
        self._totp_secret = totp_secret or os.environ.get("KITE_TOTP_SECRET")
        self._running = False
        self._token_manager = None

        if not self._api_key or not self._api_secret:
            _LOGGER.error("KITE_API_KEY and KITE_API_SECRET must be set in environment")
            raise ValueError("Missing API credentials")

        self._initialize_token_manager()

    def _initialize_token_manager(self) -> None:
        """Initialize token manager instance."""
        from iatb.broker.token_manager import ZerodhaTokenManager

        self._token_manager = ZerodhaTokenManager(
            api_key=self._api_key,
            api_secret=self._api_secret,
            totp_secret=self._totp_secret,
        )
        _LOGGER.info("Token manager initialized")

    def is_token_fresh(self) -> bool:
        """Check if current token is fresh.

        Returns:
            True if token is valid and not expired.
        """
        return self._token_manager.is_token_fresh()

    def get_totp(self) -> str:
        """Get current TOTP code.

        Returns:
            6-digit TOTP code.
        """
        return self._token_manager.get_totp()

    def get_login_url(self) -> str:
        """Get Zerodha login URL.

        Returns:
            OAuth login URL.
        """
        return self._token_manager.get_login_url()

    def store_token(self, access_token: str) -> None:
        """Store access token from manual login.

        Args:
            access_token: Access token from Zerodha.
        """
        self._token_manager.store_access_token(access_token)
        _LOGGER.info("Access token stored successfully")

    async def run_once(self) -> dict[str, bool]:
        """Run a single token freshness check.

        Returns:
            Dict with check results.
        """
        result = {
            "token_fresh": False,
            "needs_refresh": False,
            "totp_available": self._totp_secret is not None,
        }

        try:
            is_fresh = self.is_token_fresh()
            result["token_fresh"] = is_fresh
            result["needs_refresh"] = not is_fresh

            if is_fresh:
                _LOGGER.info("✓ Token is fresh and valid")
            else:
                _LOGGER.warning("✗ Token has expired or is missing")
                _LOGGER.warning("  Login URL: %s", self.get_login_url())
                if self._totp_secret:
                    totp = self.get_totp()
                    _LOGGER.warning("  Current TOTP: %s", totp)

        except Exception as exc:
            _LOGGER.exception("Error checking token freshness: %s", exc)

        return result

    async def start(self) -> None:
        """Start background token refresh loop."""
        self._running = True
        _LOGGER.info("=" * 70)
        _LOGGER.info("Token Refresh Service Started")
        _LOGGER.info("  Check interval: %d seconds", self._check_interval)
        _LOGGER.info("  TOTP configured: %s", self._totp_secret is not None)
        _LOGGER.info("=" * 70)

        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            _LOGGER.info("Token refresh service cancelled")
        finally:
            _LOGGER.info("Token refresh service stopped")

    def stop(self) -> None:
        """Stop the token refresh service."""
        self._running = False
        _LOGGER.info("Stop signal received")


# ── Main Entry Point ──


async def main_async() -> int:
    """Main async entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    service = TokenRefreshService()

    try:
        await service.start()
        return 0
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down gracefully...")
        service.stop()
        return 0
    except Exception as exc:
        _LOGGER.exception("Fatal error: %s", exc)
        return 1


def main() -> None:
    """Synchronous main entry point."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
