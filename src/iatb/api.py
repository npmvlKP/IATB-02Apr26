"""
FastAPI application for IATB trading bot.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from iatb.broker.token_manager import ZerodhaTokenManager
from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)


class IATBApi:
    """Main API class for IATB trading bot."""

    def __init__(
        self,
        *,
        token_manager: ZerodhaTokenManager | None = None,
    ) -> None:
        """Initialize API.

        Args:
            token_manager: Zerodha token manager instance.
        """
        self._token_manager = token_manager
        self._kite_client: Any = None

    def _init_kite(self) -> dict[str, Any]:
        """Initialize KiteConnect client with token freshness check.

        Returns:
            Response dict with status and details.

        Raises:
            ConfigError: If initialization fails.
        """
        if not self._token_manager:
            msg = "Token manager not configured"
            raise ConfigError(msg)

        if not self._token_manager.is_token_fresh():
            _LOGGER.warning("Access token expired, re-login required")
            return {
                "status": "error",
                "detail": "relogin_required",
                "message": "Access token expired. Please re-authenticate.",
            }

        try:
            import keyring  # noqa: PLC0415

            token = keyring.get_password("iatb_zerodha", "access_token")
            if not token:
                msg = "No access token found in storage"
                raise ConfigError(msg)
            self._kite_client = self._create_kite_client(token)
            return {
                "status": "success",
                "detail": "kite_initialized",
                "message": "KiteConnect client initialized successfully.",
            }
        except ConfigError as exc:
            _LOGGER.error("Failed to initialize KiteConnect: %s", exc)
            return {
                "status": "error",
                "detail": "kite_init_failed",
                "message": str(exc),
            }

    def _create_kite_client(self, access_token: str) -> Any:
        """Create KiteConnect client instance.

        Args:
            access_token: Zerodha access token.

        Returns:
            KiteConnect client instance.
        """
        from kiteconnect import KiteConnect  # type: ignore  # noqa: PLC0415

        if not self._token_manager:
            msg = "Token manager not configured"
            raise ConfigError(msg)

        kite = KiteConnect(
            api_key=self._token_manager._api_key,
            access_token=access_token,
        )
        return kite

    def get_kite_client(self) -> Any:
        """Get initialized KiteConnect client.

        Returns:
            KiteConnect client instance.

        Raises:
            ConfigError: If client not initialized.
        """
        if not self._kite_client:
            msg = "KiteConnect client not initialized. Call _init_kite() first."
            raise ConfigError(msg)
        return self._kite_client

    def health_check(self) -> dict[str, Any]:
        """Perform health check on API.

        Returns:
            Health status dict.
        """
        init_result = self._init_kite()
        if init_result.get("status") != "success":
            return {
                "status": "unhealthy",
                "detail": init_result.get("detail", "unknown"),
                "message": init_result.get("message", "Unknown error"),
            }
        return {
            "status": "healthy",
            "detail": "operational",
            "message": "API is operational.",
        }

    def broker_status(self) -> dict[str, Any]:
        """Get broker connection status and account details.

        Returns:
            Broker status dict with uid, balance, and connection state.
        """
        init_result = self._init_kite()
        if init_result.get("status") != "success":
            return {
                "status": "relogin_required",
                "uid": None,
                "balance": None,
                "message": init_result.get("message", "Access token expired"),
            }

        try:
            kite = self.get_kite_client()
            profile = kite.profile()
            margins = kite.margins()
            balance = margins.get("equity", {}).get("net", 0) if margins else 0
            return {
                "status": "connected",
                "uid": profile.get("user_id"),
                "balance": balance,
                "message": "Broker connection active.",
            }
        except Exception as exc:
            _LOGGER.error("Failed to fetch broker status: %s", exc)
            return {
                "status": "error",
                "uid": None,
                "balance": None,
                "message": str(exc),
            }

    def get_ohlcv(
        self,
        ticker: str,
        instrument_token: str | None = None,
        interval: str = "day",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Get OHLCV data for a ticker.

        Args:
            ticker: Trading symbol (e.g., "RELIANCE").
            instrument_token: Kite instrument token (optional).
            interval: Candle interval (day, 5minute, 15minute, etc.).
            from_date: From date in YYYY-MM-DD format (optional).
            to_date: To date in YYYY-MM-DD format (optional).

        Returns:
            Dict with OHLCV data or error.
        """
        init_result = self._init_kite()
        if init_result.get("status") != "success":
            return {
                "status": "error",
                "ticker": ticker,
                "data": None,
                "message": init_result.get("message", "Access token expired"),
            }

        try:
            kite = self.get_kite_client()

            # Try to find instrument token if not provided
            if not instrument_token:
                instruments = kite.instruments("NSE")
                for inst in instruments:
                    if inst.get("tradingsymbol") == ticker:
                        instrument_token = inst.get("instrument_token")
                        break

            if not instrument_token:
                return {
                    "status": "error",
                    "ticker": ticker,
                    "data": None,
                    "message": f"Instrument {ticker} not found",
                }

            # Default to last 30 days if dates not provided
            if not from_date:
                from_date = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now(UTC).strftime("%Y-%m-%d")

            data = kite.historical_data(
                instrument_token=str(instrument_token),
                from_date=from_date,
                to_date=to_date,
                interval=interval,
            )

            return {
                "status": "success",
                "ticker": ticker,
                "data": data,
                "count": len(data) if data else 0,
            }
        except Exception as exc:
            _LOGGER.error("Failed to fetch OHLCV for %s: %s", ticker, exc)
            return {
                "status": "error",
                "ticker": ticker,
                "data": None,
                "message": str(exc),
            }


def create_api(
    api_key: str,
    api_secret: str,
    totp_secret: str | None = None,
) -> IATBApi:
    """Factory function to create IATB API instance.

    Args:
        api_key: Zerodha API key.
        api_secret: Zerodha API secret.
        totp_secret: TOTP secret for 2FA (optional).

    Returns:
        IATBApi instance.
    """
    token_manager = ZerodhaTokenManager(
        api_key=api_key,
        api_secret=api_secret,
        totp_secret=totp_secret,
    )
    return IATBApi(token_manager=token_manager)
