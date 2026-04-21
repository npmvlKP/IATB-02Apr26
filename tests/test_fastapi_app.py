"""
Tests for FastAPI application endpoints.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import the app
from iatb import fastapi_app


@pytest.fixture
def client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(fastapi_app.app)


@pytest.fixture
def mock_api() -> MagicMock:
    """Create mock API instance."""
    api = MagicMock()
    api.health_check.return_value = {
        "status": "healthy",
        "detail": "operational",
    }
    api.broker_status.return_value = {
        "status": "connected",
        "uid": "ABC123",
        "balance": 100000.0,
        "message": "Broker connection active.",
    }
    api.get_ohlcv.return_value = {
        "status": "success",
        "ticker": "RELIANCE",
        "data": [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "open": 2500,
                "high": 2550,
                "low": 2480,
                "close": 2530,
                "volume": 100000,
            }
        ],
        "count": 1,
    }
    return api


def test_health_check_with_api(client: TestClient, mock_api: MagicMock) -> None:
    """Test health check endpoint with API initialized."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["detail"] == "operational"
        mock_api.health_check.assert_called_once()


def test_health_check_degraded(client: TestClient) -> None:
    """Test health check endpoint when API not configured."""
    # Reset global _api to None
    fastapi_app._api = None

    with patch.dict("os.environ", {}, clear=True):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["detail"] == "api_not_initialized"
        assert "API not configured" in data["message"]


def test_broker_status_success(client: TestClient, mock_api: MagicMock) -> None:
    """Test broker status endpoint with valid connection."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/broker/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["uid"] == "ABC123"
        assert data["balance"] == 100000.0
        assert "Broker connection active" in data["message"]
        mock_api.broker_status.assert_called_once()


def test_broker_status_config_error(client: TestClient) -> None:
    """Test broker status endpoint with configuration error."""
    with patch.object(fastapi_app, "_api", None):
        with patch.dict("os.environ", {"KITE_API_KEY": "", "KITE_API_SECRET": ""}):
            response = client.get("/broker/status")
            assert response.status_code == 503
            data = response.json()
            assert "detail" in data


def test_ohlcv_chart_success(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with valid ticker."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/RELIANCE?interval=day")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["ticker"] == "RELIANCE"
        assert data["data"] is not None
        assert data["count"] == 1
        mock_api.get_ohlcv.assert_called_once_with(ticker="RELIANCE", interval="day")


def test_ohlcv_chart_invalid_ticker(client: TestClient) -> None:
    """Test OHLCV chart endpoint with empty ticker."""
    response = client.get("/charts/ohlcv/")
    assert response.status_code == 404  # Not found due to empty path


def test_ohlcv_chart_empty_ticker(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with whitespace ticker."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/  ")
        assert response.status_code == 400
        data = response.json()
        assert "Ticker symbol required" in data["detail"]


def test_ohlcv_chart_case_insensitive(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint converts ticker to uppercase."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/reliance")
        assert response.status_code == 200
        mock_api.get_ohlcv.assert_called_once_with(ticker="RELIANCE", interval="day")


def test_ohlcv_chart_custom_interval(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with custom interval."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/RELIANCE?interval=5minute")
        assert response.status_code == 200
        mock_api.get_ohlcv.assert_called_once_with(ticker="RELIANCE", interval="5minute")


def test_ohlcv_chart_error_not_found(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint when instrument not found."""
    mock_api.get_ohlcv.return_value = {
        "status": "error",
        "ticker": "INVALID",
        "data": None,
        "count": 0,
        "message": "Instrument not found",
    }
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/INVALID")
        assert response.status_code == 404


def test_ohlcv_chart_error_general(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with general error."""
    mock_api.get_ohlcv.return_value = {
        "status": "error",
        "ticker": "RELIANCE",
        "data": None,
        "count": 0,
        "message": "Network error",
    }
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/RELIANCE")
        assert response.status_code == 502


def test_ohlcv_chart_exception(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint when API raises exception."""
    mock_api.get_ohlcv.side_effect = Exception("Unexpected error")
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/RELIANCE")
        assert response.status_code == 502
        data = response.json()
        assert "Failed to fetch market data" in data["detail"]


def test_get_api_caches_instance(mock_api: MagicMock) -> None:
    """Test that get_api caches the API instance."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict(
        "os.environ",
        {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
    ):
        with patch("iatb.fastapi_app.create_api", return_value=mock_api):
            api1 = fastapi_app.get_api()
            api2 = fastapi_app.get_api()
            assert api1 is api2
            assert api1 == mock_api


def test_get_api_raises_config_error() -> None:
    """Test that get_api raises HTTPException when env vars missing."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict("os.environ", {}, clear=True):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            fastapi_app.get_api()
        assert exc_info.value.status_code == 503
        assert "API initialization failed" in exc_info.value.detail


def test_get_api_raises_on_create_failure(mock_api: MagicMock) -> None:
    """Test that get_api raises HTTPException when create_api fails."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict(
        "os.environ",
        {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
    ):
        with patch("iatb.fastapi_app.create_api", side_effect=Exception("Connection failed")):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                fastapi_app.get_api()
            assert exc_info.value.status_code == 503
            assert "Connection failed" in exc_info.value.detail


def test_lifespan_startup_success(mock_api: MagicMock) -> None:
    """Test lifespan context manager initializes API successfully on startup."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict(
        "os.environ",
        {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
    ):
        with patch("iatb.fastapi_app.create_api", return_value=mock_api), patch(
            "iatb.fastapi_app.initialize_metrics"
        ), patch("iatb.fastapi_app.instrument_fastapi_app"), patch(
            "iatb.fastapi_app.get_broadcaster"
        ):
            import asyncio

            async def run_lifespan() -> None:
                async with fastapi_app.lifespan(fastapi_app.app):
                    # API should be initialized by get_api() call in startup
                    assert fastapi_app._api is not None

            asyncio.run(run_lifespan())


def test_lifespan_startup_config_error() -> None:
    """Test lifespan context manager handles configuration error on startup."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict("os.environ", {}, clear=True), patch(
        "iatb.fastapi_app.initialize_metrics"
    ), patch("iatb.fastapi_app.instrument_fastapi_app"):
        import asyncio

        from fastapi import HTTPException

        async def run_lifespan() -> None:
            async with fastapi_app.lifespan(fastapi_app.app):
                pass

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(run_lifespan())

        assert exc_info.value.status_code == 503
        assert "API initialization failed" in exc_info.value.detail


def test_lifespan_shutdown() -> None:
    """Test lifespan context manager shutdown cleanup."""
    import asyncio

    async def run_lifespan() -> None:
        with patch.dict(
            "os.environ",
            {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
        ), patch("iatb.fastapi_app.create_api"), patch(
            "iatb.fastapi_app.initialize_metrics"
        ), patch("iatb.fastapi_app.instrument_fastapi_app"), patch(
            "iatb.fastapi_app.get_broadcaster"
        ) as mock_broadcaster:
            mock_broadcaster_instance = MagicMock()
            mock_broadcaster_instance.stop = AsyncMock(return_value=None)
            mock_broadcaster.return_value = mock_broadcaster_instance

            async with fastapi_app.lifespan(fastapi_app.app):
                # Application is running
                pass

            # After context exit, shutdown should have been called
            mock_broadcaster_instance.stop.assert_called_once()

    # Should not raise
    asyncio.run(run_lifespan())


def test_broker_status_response_model_validation() -> None:
    """Test BrokerStatusResponse model validation."""
    from iatb.fastapi_app import BrokerStatusResponse

    # Valid data
    response = BrokerStatusResponse(
        status="connected", uid="ABC123", balance=100000.0, message="OK"
    )
    assert response.status == "connected"
    assert response.uid == "ABC123"
    assert response.balance == 100000.0
    assert response.message == "OK"

    # Data with None values
    response2 = BrokerStatusResponse(
        status="relogin_required", uid=None, balance=None, message="Login required"
    )
    assert response2.status == "relogin_required"
    assert response2.uid is None
    assert response2.balance is None


def test_ohlcv_response_model_validation() -> None:
    """Test OHLCVResponse model validation."""
    from iatb.fastapi_app import OHLCVResponse

    # Valid data with data
    response = OHLCVResponse(
        status="success",
        ticker="RELIANCE",
        data=[{"timestamp": "2026-01-01", "open": 2500, "close": 2530}],
        count=1,
        message=None,
    )
    assert response.status == "success"
    assert response.ticker == "RELIANCE"
    assert response.data is not None
    assert response.count == 1
    assert response.message is None

    # Valid data without data (error case)
    response2 = OHLCVResponse(
        status="error",
        ticker="RELIANCE",
        data=None,
        count=0,
        message="Not found",
    )
    assert response2.status == "error"
    assert response2.data is None
    assert response2.message == "Not found"


def test_fastapi_app_metadata() -> None:
    """Test FastAPI app metadata."""
    assert fastapi_app.app.title == "IATB API"
    assert fastapi_app.app.description == "Indian Automated Trading Bot API"
    assert fastapi_app.app.version == "0.1.0"


def test_multiple_ticker_requests(client: TestClient, mock_api: MagicMock) -> None:
    """Test multiple requests for different tickers."""
    with patch.object(fastapi_app, "_api", mock_api):
        response1 = client.get("/charts/ohlcv/RELIANCE")
        response2 = client.get("/charts/ohlcv/TCS")
        response3 = client.get("/charts/ohlcv/INFY")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 200

        assert mock_api.get_ohlcv.call_count == 3


def test_ohlcv_with_ticker_whitespace_stripping(client: TestClient, mock_api: MagicMock) -> None:
    """Test that ticker whitespace is properly stripped."""
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/charts/ohlcv/  RELIANCE  ")
        assert response.status_code == 200
        mock_api.get_ohlcv.assert_called_once_with(ticker="RELIANCE", interval="day")


def test_api_global_state_persistence() -> None:
    """Test that API instance persists across calls."""
    # Reset global _api
    fastapi_app._api = None

    mock_api = MagicMock()
    mock_api.health_check.return_value = {"status": "healthy", "detail": "operational"}

    with patch.dict(
        "os.environ",
        {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
    ):
        with patch("iatb.fastapi_app.create_api", return_value=mock_api):
            # First call creates instance
            api1 = fastapi_app.get_api()
            # Second call returns cached instance
            api2 = fastapi_app.get_api()

            assert api1 is api2
            assert fastapi_app._api is api1


def test_health_check_with_unhealthy_api(client: TestClient, mock_api: MagicMock) -> None:
    """Test health check endpoint when API reports unhealthy."""
    mock_api.health_check.return_value = {
        "status": "unhealthy",
        "detail": "relogin_required",
    }
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["detail"] == "relogin_required"


def test_broker_status_with_relogin_required(client: TestClient, mock_api: MagicMock) -> None:
    """Test broker status endpoint when relogin is required."""
    mock_api.broker_status.return_value = {
        "status": "relogin_required",
        "uid": None,
        "balance": None,
        "message": "Access token expired. Please re-authenticate.",
    }
    with patch.object(fastapi_app, "_api", mock_api):
        response = client.get("/broker/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "relogin_required"
        assert data["uid"] is None
        assert data["balance"] is None


def test_ohlcv_various_intervals(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with various intervals."""
    intervals = ["day", "5minute", "15minute", "30minute", "60minute"]

    with patch.object(fastapi_app, "_api", mock_api):
        for interval in intervals:
            response = client.get(f"/charts/ohlcv/RELIANCE?interval={interval}")
            assert response.status_code == 200
            mock_api.get_ohlcv.assert_called_with(ticker="RELIANCE", interval=interval)


def test_get_watchlist_config_success(client: TestClient) -> None:
    """Test getting watchlist configuration."""
    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.nse = ["RELIANCE", "TCS"]
        mock_config.bse = ["SBIN"]
        mock_config.mcx = []
        mock_config.cds = []
        mock_manager.get_config.return_value = mock_config
        mock_manager._config_path = Path("config/watchlist.toml")
        mock_get_manager.return_value = mock_manager

        response = client.get("/config/watchlist")
        assert response.status_code == 200
        data = response.json()
        assert data["nse"] == ["RELIANCE", "TCS"]
        assert data["bse"] == ["SBIN"]
        assert data["mcx"] == []
        assert data["cds"] == []
        assert data["total_symbols"] == 3
        assert data["config_path"] == "config/watchlist.toml"


def test_get_watchlist_config_error(client: TestClient) -> None:
    """Test getting watchlist configuration with error."""
    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_get_manager.side_effect = Exception("Config error")

        response = client.get("/config/watchlist")
        assert response.status_code == 503
        data = response.json()
        assert "Failed to retrieve watchlist configuration" in data["detail"]


def test_update_watchlist_config_success(client: TestClient) -> None:
    """Test updating watchlist configuration."""
    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.nse = ["INFY", "WIPRO"]
        mock_config.bse = []
        mock_config.mcx = []
        mock_config.cds = []
        mock_manager.update_config.return_value = mock_config
        mock_manager._config_path = Path("config/watchlist.toml")
        mock_get_manager.return_value = mock_manager

        request_data = {"nse": ["INFY", "WIPRO"]}
        response = client.put("/config/watchlist", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["nse"] == ["INFY", "WIPRO"]
        mock_manager.update_config.assert_called_once_with(
            nse=["INFY", "WIPRO"], bse=None, mcx=None, cds=None
        )


def test_update_watchlist_config_multiple_exchanges(client: TestClient) -> None:
    """Test updating watchlist configuration for multiple exchanges."""
    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.nse = ["RELIANCE"]
        mock_config.bse = ["TCS"]
        mock_config.mcx = ["GOLD"]
        mock_config.cds = ["USDINR"]
        mock_manager.update_config.return_value = mock_config
        mock_manager._config_path = Path("config/watchlist.toml")
        mock_get_manager.return_value = mock_manager

        request_data = {
            "nse": ["RELIANCE"],
            "bse": ["TCS"],
            "mcx": ["GOLD"],
            "cds": ["USDINR"],
        }
        response = client.put("/config/watchlist", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["nse"] == ["RELIANCE"]
        assert data["bse"] == ["TCS"]
        assert data["mcx"] == ["GOLD"]
        assert data["cds"] == ["USDINR"]


def test_update_watchlist_config_config_error(client: TestClient) -> None:
    """Test updating watchlist configuration with ConfigError."""
    from iatb.core.exceptions import ConfigError

    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.update_config.side_effect = ConfigError("Write failed")
        mock_get_manager.return_value = mock_manager

        request_data = {"nse": ["RELIANCE"]}
        response = client.put("/config/watchlist", json=request_data)
        assert response.status_code == 500
        data = response.json()
        assert "Configuration error" in data["detail"]


def test_update_watchlist_config_general_error(client: TestClient) -> None:
    """Test updating watchlist configuration with general error."""
    with patch("iatb.fastapi_app.get_config_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.update_config.side_effect = Exception("Unexpected error")
        mock_get_manager.return_value = mock_manager

        request_data = {"nse": ["RELIANCE"]}
        response = client.put("/config/watchlist", json=request_data)
        assert response.status_code == 500
        data = response.json()
        assert "Failed to update watchlist configuration" in data["detail"]


def test_ml_status_endpoint_success(client: TestClient) -> None:
    """Test ML status endpoint with successful response."""
    from datetime import UTC, datetime

    from iatb.ml.model_registry import ModelStatus

    with patch("iatb.fastapi_app.get_registry") as mock_get_registry:
        mock_registry = MagicMock()
        mock_health = MagicMock()
        mock_health.status = ModelStatus.AVAILABLE
        mock_health.last_check = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_health.load_time_ms = 100
        mock_health.dll_loaded = True
        mock_health.fallback_available = True
        mock_health.error_message = None

        mock_status = MagicMock()
        mock_status.timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_status.total_models = 3
        mock_status.available_models = 2
        mock_status.degraded_models = 1
        mock_status.unavailable_models = 0
        mock_status.model_health = {
            "lstm": mock_health,
            "transformer": mock_health,
        }

        mock_registry.get_status.return_value = mock_status
        mock_get_registry.return_value = mock_registry

        response = client.get("/ml/status")
        assert response.status_code == 200
        data = response.json()
        assert data["total_models"] == 3
        assert data["available_models"] == 2
        assert data["degraded_models"] == 1
        assert data["unavailable_models"] == 0
        assert "lstm" in data["models"]
        assert "transformer" in data["models"]
        assert data["models"]["lstm"]["status"] == "available"


def test_ml_status_endpoint_error(client: TestClient) -> None:
    """Test ML status endpoint with error."""
    with patch("iatb.fastapi_app.get_registry") as mock_get_registry:
        mock_get_registry.side_effect = Exception("Registry error")

        response = client.get("/ml/status")
        assert response.status_code == 503
        data = response.json()
        assert "Failed to retrieve ML status" in data["detail"]


def test_metrics_endpoint(client: TestClient) -> None:
    """Test Prometheus metrics endpoint."""
    with patch("iatb.fastapi_app.generate_latest") as mock_generate:
        mock_metrics = b"# HELP test_metric Test metric\n"
        mock_generate.return_value = mock_metrics

        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        mock_generate.assert_called_once()


def test_events_stream_endpoint(client: TestClient) -> None:
    """Test SSE events stream endpoint."""
    with patch("iatb.fastapi_app.get_broadcaster") as mock_get_broadcaster:

        async def mock_subscribe():
            yield 'data: {"type": "test", "data": {}}\n\n'

        mock_broadcaster = MagicMock()
        mock_broadcaster.subscribe = mock_subscribe
        mock_get_broadcaster.return_value = mock_broadcaster

        response = client.get("/events/stream")
        assert response.status_code == 200
        assert response.headers["media-type"] == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"


def test_watchlist_response_model_validation() -> None:
    """Test WatchlistResponse model validation."""
    from iatb.fastapi_app import WatchlistResponse

    response = WatchlistResponse(
        nse=["RELIANCE", "TCS"],
        bse=["SBIN"],
        mcx=[],
        cds=["USDINR"],
        total_symbols=4,
        config_path="config/watchlist.toml",
        message="Success",
    )
    assert response.nse == ["RELIANCE", "TCS"]
    assert response.total_symbols == 4
    assert response.config_path == "config/watchlist.toml"


def test_watchlist_update_request_model_validation() -> None:
    """Test WatchlistUpdateRequest model validation."""
    from iatb.fastapi_app import WatchlistUpdateRequest

    # All fields None (valid)
    request1 = WatchlistUpdateRequest()
    assert request1.nse is None
    assert request1.bse is None

    # Some fields provided
    request2 = WatchlistUpdateRequest(nse=["RELIANCE"])
    assert request2.nse == ["RELIANCE"]
    assert request2.bse is None

    # All fields provided
    request3 = WatchlistUpdateRequest(
        nse=["RELIANCE"],
        bse=["TCS"],
        mcx=["GOLD"],
        cds=["USDINR"],
    )
    assert len(request3.nse) == 1
    assert len(request3.bse) == 1
    assert len(request3.mcx) == 1
    assert len(request3.cds) == 1


def test_ml_status_response_model_validation() -> None:
    """Test MLStatusResponse model validation."""
    from iatb.fastapi_app import MLStatusResponse

    response = MLStatusResponse(
        timestamp="2026-01-01T12:00:00",
        total_models=5,
        available_models=3,
        degraded_models=1,
        unavailable_models=1,
        models={"lstm": {"status": "available", "load_time_ms": "100"}},
    )
    assert response.total_models == 5
    assert response.available_models == 3
    assert "lstm" in response.models
