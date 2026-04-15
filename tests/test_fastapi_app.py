"""
Tests for FastAPI application endpoints.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


def test_startup_event_success(mock_api: MagicMock) -> None:
    """Test startup event initializes API successfully."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict(
        "os.environ",
        {"KITE_API_KEY": "test_key", "KITE_API_SECRET": "test_secret"},
    ):
        with patch("iatb.fastapi_app.create_api", return_value=mock_api), patch(
            "iatb.fastapi_app.initialize_metrics"
        ), patch("iatb.fastapi_app.instrument_fastapi_app"):
            import asyncio

            asyncio.run(fastapi_app.startup_event())
            # API should be initialized by get_api() call in startup_event
            assert fastapi_app._api is not None


def test_startup_event_config_error() -> None:
    """Test startup event handles configuration error."""
    # Reset global _api
    fastapi_app._api = None

    with patch.dict("os.environ", {}, clear=True), patch(
        "iatb.fastapi_app.initialize_metrics"
    ), patch("iatb.fastapi_app.instrument_fastapi_app"):
        import asyncio

        from fastapi import HTTPException

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(fastapi_app.startup_event())

        assert exc_info.value.status_code == 503
        assert "API initialization failed" in exc_info.value.detail


def test_shutdown_event() -> None:
    """Test shutdown event."""
    import asyncio

    # Should not raise
    asyncio.run(fastapi_app.shutdown_event())


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


def test_ohlvarious_intervals(client: TestClient, mock_api: MagicMock) -> None:
    """Test OHLCV chart endpoint with various intervals."""
    intervals = ["day", "5minute", "15minute", "30minute", "60minute"]

    with patch.object(fastapi_app, "_api", mock_api):
        for interval in intervals:
            response = client.get(f"/charts/ohlcv/RELIANCE?interval={interval}")
            assert response.status_code == 200
            mock_api.get_ohlcv.assert_called_with(ticker="RELIANCE", interval=interval)
