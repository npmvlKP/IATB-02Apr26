"""
FastAPI application for IATB trading bot with REST endpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from iatb.api import IATBApi, create_api
from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="IATB API",
    description="Indian Automated Trading Bot API",
    version="0.1.0",
)

# Initialize API client
_api: IATBApi | None = None


def get_api() -> IATBApi:
    """Get or create API instance.

    Returns:
        IATBApi instance.

    Raises:
        HTTPException: If API cannot be initialized.
    """
    global _api
    if _api is None:
        try:
            api_key = os.environ.get("KITE_API_KEY", "")
            api_secret = os.environ.get("KITE_API_SECRET", "")
            totp_secret = os.environ.get("KITE_TOTP_SECRET")

            if not api_key or not api_secret:
                raise ConfigError("KITE_API_KEY and KITE_API_SECRET must be set")

            _api = create_api(api_key, api_secret, totp_secret)
        except Exception as exc:
            _LOGGER.error("Failed to initialize API: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"API initialization failed: {exc}",
            ) from exc
    return _api


class BrokerStatusResponse(BaseModel):
    """Broker status response model."""

    status: str
    uid: str | None
    balance: float | None
    message: str


class OHLCVResponse(BaseModel):
    """OHLCV chart data response model."""

    status: str
    ticker: str
    data: list[dict[str, Any]] | None
    count: int
    message: str | None = None


@app.get("/health")
def health_check() -> dict[str, Any]:
    """Health check endpoint.

    Returns:
        Health status dict.
    """
    try:
        api = get_api()
        result = api.health_check()
        return result
    except HTTPException:
        return {
            "status": "degraded",
            "detail": "api_not_initialized",
            "message": "API not configured. Set KITE_API_KEY and KITE_API_SECRET.",
        }


@app.get("/broker/status", response_model=BrokerStatusResponse)
def broker_status_endpoint() -> dict[str, Any]:
    """Get broker connection status and account details.

    Returns broker connectivity, user ID, and balance when token
    is valid. Returns relogin_required when token has expired.

    Returns:
        Broker status dict with uid, balance, and connection state.
    """
    try:
        api = get_api()
        result = api.broker_status()
        return result
    except ConfigError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {exc}",
        ) from exc


@app.get("/charts/ohlcv/{ticker}", response_model=OHLCVResponse)
def ohlcv_chart_endpoint(ticker: str, interval: str = "day") -> dict[str, Any]:
    """Return OHLCV data for a given ticker symbol.

    Args:
        ticker: Stock symbol (e.g., RELIANCE, TCS, INFY).
        interval: Candle interval (day, 5minute, 15minute, etc.).

    Returns:
        OHLCV candlestick data for chart rendering.

    Raises:
        HTTPException: If ticker is invalid or data fetch fails.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(
            status_code=400,
            detail="Ticker symbol required",
        )

    try:
        api = get_api()
        result = api.get_ohlcv(ticker=ticker, interval=interval)

        if result.get("status") == "error":
            status_code = 404 if "not found" in result.get("message", "").lower() else 502
            raise HTTPException(
                status_code=status_code,
                detail=result.get("message", "Failed to fetch OHLCV data"),
            )

        return result
    except HTTPException:
        raise
    except Exception as exc:
        _LOGGER.error("Failed to fetch OHLCV for %s: %s", ticker, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch market data for {ticker}: {exc}",
        ) from exc


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize API on startup."""
    try:
        get_api()
        _LOGGER.info("IATB FastAPI app started")
    except ConfigError as exc:
        _LOGGER.warning("API not configured: %s", exc)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    _LOGGER.info("IATB FastAPI app shutting down")
