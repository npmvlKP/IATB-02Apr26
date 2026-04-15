"""
FastAPI application for IATB trading bot with REST endpoints.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from iatb.api import IATBApi, create_api
from iatb.core.config_manager import WatchlistConfig, get_config_manager
from iatb.core.exceptions import ConfigError
from iatb.core.observability import (
    initialize_metrics,
    instrument_fastapi_app,
)
from iatb.core.observability.logging_config import get_logger
from iatb.core.sse_broadcaster import get_broadcaster
from iatb.ml.model_registry import get_registry

_LOGGER = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown events.

    Manages application lifecycle including:
    - Initialization of observability stack
    - API client initialization
    - Cleanup of SSE broadcaster on shutdown

    Args:
        app: FastAPI application instance.

    Yields:
        None: Control is yielded to the application during its lifecycle.
    """
    try:
        # Startup: Initialize observability
        initialize_metrics(app_version="0.1.0")
        instrument_fastapi_app(app)
        _LOGGER.info("Observability stack initialized")

        # Startup: Initialize API
        get_api()
        _LOGGER.info("IATB FastAPI app started")
    except HTTPException:
        # Re-raise HTTPException from get_api() for proper error handling
        raise
    except ConfigError as exc:
        _LOGGER.warning("API not configured: %s", exc)
    except Exception as exc:
        _LOGGER.error("Failed to initialize observability: %s", exc)

    # Application is running
    yield

    # Shutdown: Cleanup
    _LOGGER.info("IATB FastAPI app shutting down")
    broadcaster = await get_broadcaster()
    await broadcaster.stop()


# Create FastAPI app with lifespan context manager
app = FastAPI(
    title="IATB API",
    description="Indian Automated Trading Bot API",
    version="0.1.0",
    lifespan=lifespan,
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


class MLStatusResponse(BaseModel):
    """ML model status response model."""

    timestamp: str
    total_models: int
    available_models: int
    degraded_models: int
    unavailable_models: int
    models: dict[str, dict[str, Any]]


class WatchlistUpdateRequest(BaseModel):
    """Request model for updating watchlist configuration."""

    nse: list[str] | None = None
    bse: list[str] | None = None
    mcx: list[str] | None = None
    cds: list[str] | None = None


class WatchlistResponse(BaseModel):
    """Response model for watchlist configuration."""

    nse: list[str]
    bse: list[str]
    mcx: list[str]
    cds: list[str]
    total_symbols: int
    config_path: str
    message: str


@app.get("/config/watchlist", response_model=WatchlistResponse)
def get_watchlist_config() -> dict[str, Any]:
    """Get current watchlist configuration.

    Returns the current watchlist for all exchanges with symbol counts
    and configuration file path.

    Returns:
        Watchlist configuration dict with symbols for each exchange.
    """
    try:
        config_manager = get_config_manager()
        config = config_manager.get_config()

        total_symbols = len(config.nse) + len(config.bse) + len(config.mcx) + len(config.cds)

        return {
            "nse": config.nse,
            "bse": config.bse,
            "mcx": config.mcx,
            "cds": config.cds,
            "total_symbols": total_symbols,
            "config_path": str(config_manager._config_path),
            "message": "Watchlist configuration retrieved successfully",
        }
    except Exception as exc:
        _LOGGER.error("Failed to get watchlist config: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to retrieve watchlist configuration: {exc}",
        ) from exc


def _build_watchlist_response(config: WatchlistConfig, config_path: Path) -> dict[str, Any]:
    """Build watchlist response from configuration.

    Args:
        config: Watchlist configuration.
        config_path: Path to config file.

    Returns:
        Response dictionary with watchlist data.
    """
    total_symbols = len(config.nse) + len(config.bse) + len(config.mcx) + len(config.cds)

    return {
        "nse": config.nse,
        "bse": config.bse,
        "mcx": config.mcx,
        "cds": config.cds,
        "total_symbols": total_symbols,
        "config_path": str(config_path),
        "message": "Watchlist configuration updated successfully",
    }


def _log_watchlist_update(config: WatchlistConfig) -> None:
    """Log watchlist update event.

    Args:
        config: Updated watchlist configuration.
    """
    _LOGGER.info(
        "Watchlist updated via API",
        extra={
            "nse_count": len(config.nse),
            "bse_count": len(config.bse),
            "mcx_count": len(config.mcx),
            "cds_count": len(config.cds),
        },
    )


@app.put("/config/watchlist", response_model=WatchlistResponse)
def update_watchlist_config(request: WatchlistUpdateRequest) -> dict[str, Any]:
    """Update watchlist configuration.

    Updates the watchlist for one or more exchanges and persists
    the changes to the configuration file. This allows dynamic
    watchlist updates without restarting the application.

    Args:
        request: WatchlistUpdateRequest with optional lists for each exchange.

    Returns:
        Updated watchlist configuration.

    Raises:
        HTTPException: If configuration cannot be updated.
    """
    try:
        config_manager = get_config_manager()
        config = config_manager.update_config(
            nse=request.nse,
            bse=request.bse,
            mcx=request.mcx,
            cds=request.cds,
        )

        _log_watchlist_update(config)

        return _build_watchlist_response(config, config_manager._config_path)
    except ConfigError as exc:
        _LOGGER.error("Failed to update watchlist config: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {exc}",
        ) from exc
    except Exception as exc:
        _LOGGER.error("Unexpected error updating watchlist: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update watchlist configuration: {exc}",
        ) from exc


@app.get("/ml/status", response_model=MLStatusResponse)
def ml_status_endpoint() -> dict[str, Any]:
    """Get ML model availability and health status.

    Returns detailed information about all ML models including:
    - Availability status (available, unavailable, degraded, error)
    - Last check timestamp
    - Load time metrics
    - Error messages if any
    - Fallback availability

    Returns:
        ML status dict with model health information.
    """
    try:
        registry = get_registry()
        status = registry.get_status()

        models = {}
        for model_name, health in status.model_health.items():
            models[model_name] = {
                "status": health.status.value,
                "last_check": health.last_check.isoformat(),
                "load_time_ms": str(health.load_time_ms) if health.load_time_ms else None,
                "dll_loaded": health.dll_loaded,
                "fallback_available": health.fallback_available,
                "error_message": health.error_message,
            }

        return {
            "timestamp": status.timestamp.isoformat(),
            "total_models": status.total_models,
            "available_models": status.available_models,
            "degraded_models": status.degraded_models,
            "unavailable_models": status.unavailable_models,
            "models": models,
        }
    except Exception as exc:
        _LOGGER.error("Failed to get ML status: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Failed to retrieve ML status: {exc}",
        ) from exc


@app.get("/metrics")
def metrics_endpoint() -> str:
    """Prometheus metrics endpoint.

    Returns:
        Prometheus metrics in text format.
    """
    from prometheus_client import generate_latest

    content: str = generate_latest().decode("utf-8")
    return content


@app.get("/events/stream")
async def events_stream() -> StreamingResponse:
    """Server-Sent Events endpoint for real-time dashboard updates.

    Provides a persistent SSE connection that pushes scan and PnL updates
    in real-time as they occur in the trading system.

    Returns:
        StreamingResponse with SSE-formatted events.

    Example:
        >>> import requests
        >>> response = requests.get(
        ...     "http://localhost:8000/events/stream",
        ...     stream=True
        ... )
        >>> for line in response.iter_lines():
        ...     if line:
        ...         _LOGGER.info("SSE line: %s", line.decode())
    """
    broadcaster = await get_broadcaster()

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events from the broadcaster."""
        async for message in broadcaster.subscribe():
            yield message

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
