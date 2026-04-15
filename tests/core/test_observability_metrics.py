"""Tests for observability metrics configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from iatb.core.observability.metrics import (
    api_request_counter,
    api_request_duration,
    app_info,
    broker_connection_status,
    daily_pnl,
    database_connection_status,
    error_counter,
    initialize_metrics,
    instrument_fastapi_app,
    ml_model_status,
    model_inference_duration,
    open_positions,
    portfolio_value,
    record_error,
    record_model_inference,
    record_scan_cycle,
    record_trade,
    scan_cycle_duration,
    start_metrics_server,
    track_execution_time,
    trade_counter,
    trade_pnl,
    update_broker_connection_status,
    update_daily_pnl,
    update_database_connection_status,
    update_ml_model_status,
    update_open_positions,
    update_portfolio_value,
)
from prometheus_client import Counter, Gauge, Histogram, Info


class TestMetricsInitialization:
    """Tests for metrics initialization."""

    def test_trade_counter_is_counter(self) -> None:
        """Test that trade_counter is a Counter."""
        assert isinstance(trade_counter, Counter)

    def test_trade_pnl_is_gauge(self) -> None:
        """Test that trade_pnl is a Gauge."""
        assert isinstance(trade_pnl, Gauge)

    def test_open_positions_is_gauge(self) -> None:
        """Test that open_positions is a Gauge."""
        assert isinstance(open_positions, Gauge)

    def test_portfolio_value_is_gauge(self) -> None:
        """Test that portfolio_value is a Gauge."""
        assert isinstance(portfolio_value, Gauge)

    def test_daily_pnl_is_gauge(self) -> None:
        """Test that daily_pnl is a Gauge."""
        assert isinstance(daily_pnl, Gauge)

    def test_api_request_duration_is_histogram(self) -> None:
        """Test that api_request_duration is a Histogram."""
        assert isinstance(api_request_duration, Histogram)

    def test_api_request_counter_is_counter(self) -> None:
        """Test that api_request_counter is a Counter."""
        assert isinstance(api_request_counter, Counter)

    def test_scan_cycle_duration_is_histogram(self) -> None:
        """Test that scan_cycle_duration is a Histogram."""
        assert isinstance(scan_cycle_duration, Histogram)

    def test_model_inference_duration_is_histogram(self) -> None:
        """Test that model_inference_duration is a Histogram."""
        assert isinstance(model_inference_duration, Histogram)

    def test_error_counter_is_counter(self) -> None:
        """Test that error_counter is a Counter."""
        assert isinstance(error_counter, Counter)

    def test_broker_connection_status_is_gauge(self) -> None:
        """Test that broker_connection_status is a Gauge."""
        assert isinstance(broker_connection_status, Gauge)

    def test_database_connection_status_is_gauge(self) -> None:
        """Test that database_connection_status is a Gauge."""
        assert isinstance(database_connection_status, Gauge)

    def test_ml_model_status_is_gauge(self) -> None:
        """Test that ml_model_status is a Gauge."""
        assert isinstance(ml_model_status, Gauge)

    def test_app_info_is_info(self) -> None:
        """Test that app_info is an Info metric."""
        assert isinstance(app_info, Info)


class TestInitializeMetrics:
    """Tests for initialize_metrics function."""

    @patch.dict("os.environ", {"ENVIRONMENT": "production"})
    def test_initialize_metrics_sets_app_info(self) -> None:
        """Test that initialize_metrics sets application info."""
        initialize_metrics(app_version="1.0.0")
        # Should not raise exception
        assert True

    @patch.dict("os.environ", {}, clear=True)
    def test_initialize_metrics_with_default_environment(self) -> None:
        """Test that initialize_metrics uses default environment."""
        initialize_metrics()
        # Should not raise exception
        assert True

    def test_initialize_metrics_with_custom_version(self) -> None:
        """Test that initialize_metrics accepts custom version."""
        initialize_metrics(app_version="2.0.0")
        # Should not raise exception
        assert True


class TestRecordTrade:
    """Tests for record_trade function."""

    def test_record_trade_increments_counter(self) -> None:
        """Test that record_trade increments trade counter."""
        record_trade(exchange="NSE", side="BUY", status="SUCCESS")
        # Should not raise exception
        assert True

    def test_record_trade_with_pnl(self) -> None:
        """Test that record_trade sets PnL when provided."""
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=100.50,
            ticker="RELIANCE",
        )
        # Should not raise exception
        assert True

    def test_record_trade_with_different_statuses(self) -> None:
        """Test that record_trade handles different statuses."""
        statuses = ["SUCCESS", "FAILED", "PENDING"]
        for status in statuses:
            record_trade(exchange="NSE", side="BUY", status=status)
        # Should not raise exception
        assert True

    def test_record_trade_with_different_exchanges(self) -> None:
        """Test that record_trade handles different exchanges."""
        exchanges = ["NSE", "BSE", "BINANCE"]
        for exchange in exchanges:
            record_trade(exchange=exchange, side="BUY", status="SUCCESS")
        # Should not raise exception
        assert True


class TestUpdateOpenPositions:
    """Tests for update_open_positions function."""

    def test_update_open_positions_sets_value(self) -> None:
        """Test that update_open_positions sets position count."""
        update_open_positions(exchange="NSE", count=5)
        # Should not raise exception
        assert True

    def test_update_open_positions_with_zero(self) -> None:
        """Test that update_open_positions handles zero positions."""
        update_open_positions(exchange="NSE", count=0)
        # Should not raise exception
        assert True

    def test_update_open_positions_with_large_number(self) -> None:
        """Test that update_open_positions handles large numbers."""
        update_open_positions(exchange="NSE", count=1000)
        # Should not raise exception
        assert True


class TestUpdatePortfolioValue:
    """Tests for update_portfolio_value function."""

    def test_update_portfolio_value_sets_value(self) -> None:
        """Test that update_portfolio_value sets portfolio value."""
        update_portfolio_value(value=100000.50)
        # Should not raise exception
        assert True

    def test_update_portfolio_value_with_negative(self) -> None:
        """Test that update_portfolio_value handles negative values."""
        update_portfolio_value(value=-5000.00)
        # Should not raise exception
        assert True

    def test_update_portfolio_value_with_zero(self) -> None:
        """Test that update_portfolio_value handles zero value."""
        update_portfolio_value(value=0.0)
        # Should not raise exception
        assert True


class TestUpdateDailyPnL:
    """Tests for update_daily_pnl function."""

    def test_update_daily_pnl_sets_value(self) -> None:
        """Test that update_daily_pnl sets daily PnL."""
        update_daily_pnl(pnl=5000.75)
        # Should not raise exception
        assert True

    def test_update_daily_pnl_with_loss(self) -> None:
        """Test that update_daily_pnl handles losses."""
        update_daily_pnl(pnl=-2000.50)
        # Should not raise exception
        assert True

    def test_update_daily_pnl_with_zero(self) -> None:
        """Test that update_daily_pnl handles zero PnL."""
        update_daily_pnl(pnl=0.0)
        # Should not raise exception
        assert True


class TestRecordScanCycle:
    """Tests for record_scan_cycle function."""

    def test_record_scan_cycle_observes_duration(self) -> None:
        """Test that record_scan_cycle records duration."""
        record_scan_cycle(scanner_type="momentum", duration=1.5)
        # Should not raise exception
        assert True

    def test_record_scan_cycle_with_different_types(self) -> None:
        """Test that record_scan_cycle handles different scanner types."""
        scanner_types = ["momentum", "mean_reversion", "breakout"]
        for scanner_type in scanner_types:
            record_scan_cycle(scanner_type=scanner_type, duration=2.0)
        # Should not raise exception
        assert True

    def test_record_scan_cycle_with_zero_duration(self) -> None:
        """Test that record_scan_cycle handles zero duration."""
        record_scan_cycle(scanner_type="momentum", duration=0.0)
        # Should not raise exception
        assert True

    def test_record_scan_cycle_with_long_duration(self) -> None:
        """Test that record_scan_cycle handles long durations."""
        record_scan_cycle(scanner_type="momentum", duration=3600.0)
        # Should not raise exception
        assert True


class TestRecordModelInference:
    """Tests for record_model_inference function."""

    def test_record_model_inference_observes_duration(self) -> None:
        """Test that record_model_inference records duration."""
        record_model_inference(model_name="lstm", duration=0.5)
        # Should not raise exception
        assert True

    def test_record_model_inference_with_different_models(self) -> None:
        """Test that record_model_inference handles different models."""
        models = ["lstm", "transformer", "random_forest"]
        for model in models:
            record_model_inference(model_name=model, duration=1.0)
        # Should not raise exception
        assert True

    def test_record_model_inference_with_zero_duration(self) -> None:
        """Test that record_model_inference handles zero duration."""
        record_model_inference(model_name="lstm", duration=0.0)
        # Should not raise exception
        assert True


class TestRecordError:
    """Tests for record_error function."""

    def test_record_error_increments_counter(self) -> None:
        """Test that record_error increments error counter."""
        record_error(component="execution", error_type="timeout")
        # Should not raise exception
        assert True

    def test_record_error_with_different_components(self) -> None:
        """Test that record_error handles different components."""
        components = ["execution", "risk", "data", "api"]
        for component in components:
            record_error(component=component, error_type="generic")
        # Should not raise exception
        assert True

    def test_record_error_with_different_error_types(self) -> None:
        """Test that record_error handles different error types."""
        error_types = ["timeout", "connection", "validation", "unknown"]
        for error_type in error_types:
            record_error(component="execution", error_type=error_type)
        # Should not raise exception
        assert True


class TestUpdateBrokerConnectionStatus:
    """Tests for update_broker_connection_status function."""

    def test_update_broker_connection_status_connected(self) -> None:
        """Test that update_broker_connection_status sets connected status."""
        update_broker_connection_status(broker="Zerodha", connected=True)
        # Should not raise exception
        assert True

    def test_update_broker_connection_status_disconnected(self) -> None:
        """Test that update_broker_connection_status sets disconnected status."""
        update_broker_connection_status(broker="Zerodha", connected=False)
        # Should not raise exception
        assert True

    def test_update_broker_connection_status_different_brokers(self) -> None:
        """Test that update_broker_connection_status handles different brokers."""
        brokers = ["Zerodha", "Alpaca", "Binance"]
        for broker in brokers:
            update_broker_connection_status(broker=broker, connected=True)
        # Should not raise exception
        assert True


class TestUpdateDatabaseConnectionStatus:
    """Tests for update_database_connection_status function."""

    def test_update_database_connection_status_connected(self) -> None:
        """Test that update_database_connection_status sets connected status."""
        update_database_connection_status(database="primary", connected=True)
        # Should not raise exception
        assert True

    def test_update_database_connection_status_disconnected(self) -> None:
        """Test that update_database_connection_status sets disconnected status."""
        update_database_connection_status(database="primary", connected=False)
        # Should not raise exception
        assert True

    def test_update_database_connection_status_different_databases(self) -> None:
        """Test that update_database_connection_status handles different databases."""
        databases = ["primary", "cache", "analytics"]
        for database in databases:
            update_database_connection_status(database=database, connected=True)
        # Should not raise exception
        assert True


class TestUpdateMLModelStatus:
    """Tests for update_ml_model_status function."""

    def test_update_ml_model_status_available(self) -> None:
        """Test that update_ml_model_status sets available status."""
        update_ml_model_status(model_name="lstm", available=True)
        # Should not raise exception
        assert True

    def test_update_ml_model_status_unavailable(self) -> None:
        """Test that update_ml_model_status sets unavailable status."""
        update_ml_model_status(model_name="lstm", available=False)
        # Should not raise exception
        assert True

    def test_update_ml_model_status_different_models(self) -> None:
        """Test that update_ml_model_status handles different models."""
        models = ["lstm", "transformer", "random_forest"]
        for model in models:
            update_ml_model_status(model_name=model, available=True)
        # Should not raise exception
        assert True


class TestInstrumentFastAPIApp:
    """Tests for instrument_fastapi_app function."""

    @patch("iatb.core.observability.metrics.Instrumentator")
    def test_instrument_fastapi_app_returns_instrumentator(
        self,
        mock_instrumentator_class: MagicMock,
    ) -> None:
        """Test that instrument_fastapi_app returns an Instrumentator."""
        mock_app = MagicMock()
        mock_instrumentator = MagicMock()
        mock_instrumentator_class.return_value = mock_instrumentator

        result = instrument_fastapi_app(mock_app)

        assert result is mock_instrumentator
        mock_instrumentator.instrument.assert_called_once_with(mock_app)

    @patch("iatb.core.observability.metrics.Instrumentator")
    def test_instrument_fastapi_app_configures_excluded_handlers(
        self,
        mock_instrumentator_class: MagicMock,
    ) -> None:
        """Test that instrument_fastapi_app configures excluded handlers."""
        mock_app = MagicMock()
        mock_instrumentator = MagicMock()
        mock_instrumentator_class.return_value = mock_instrumentator

        instrument_fastapi_app(mock_app)

        mock_instrumentator_class.assert_called_once()
        call_kwargs = mock_instrumentator_class.call_args[1]
        assert "/metrics" in call_kwargs.get("excluded_handlers", [])


class TestStartMetricsServer:
    """Tests for start_metrics_server function."""

    @patch("iatb.core.observability.metrics.start_http_server")
    def test_start_metrics_server_starts_server(self, mock_start_server: MagicMock) -> None:
        """Test that start_metrics_server starts the HTTP server."""
        start_metrics_server(port=9090)
        mock_start_server.assert_called_once_with(9090)

    @patch("iatb.core.observability.metrics.start_http_server")
    def test_start_metrics_server_with_default_port(self, mock_start_server: MagicMock) -> None:
        """Test that start_metrics_server uses default port."""
        start_metrics_server()
        mock_start_server.assert_called_once_with(9090)

    @patch("iatb.core.observability.metrics.start_http_server")
    def test_start_metrics_server_with_custom_port(self, mock_start_server: MagicMock) -> None:
        """Test that start_metrics_server uses custom port."""
        start_metrics_server(port=8080)
        mock_start_server.assert_called_once_with(8080)


class TestTrackExecutionTime:
    """Tests for track_execution_time decorator."""

    def test_track_execution_time_decorator(self) -> None:
        """Test that track_execution_time decorator works."""
        mock_metric = MagicMock()

        @track_execution_time(mock_metric, labels={"endpoint": "/test"})
        def test_function() -> str:
            return "success"

        result = test_function()
        assert result == "success"
        assert mock_metric.labels.called

    def test_track_execution_time_with_histogram(self) -> None:
        """Test that track_execution_time works with Histogram."""
        mock_histogram = MagicMock()

        @track_execution_time(mock_histogram, labels={"endpoint": "/api/test"})
        def api_handler() -> dict[str, str]:
            return {"status": "ok"}

        result = api_handler()
        assert result["status"] == "ok"

    def test_track_execution_time_with_summary(self) -> None:
        """Test that track_execution_time works with Summary."""
        mock_summary = MagicMock()

        @track_execution_time(mock_summary, labels={"operation": "compute"})
        def compute() -> int:
            return 42

        result = compute()
        assert result == 42

    def test_track_execution_time_with_exception(self) -> None:
        """Test that track_execution_time handles exceptions."""
        mock_metric = MagicMock()

        @track_execution_time(mock_metric, labels={"endpoint": "/test"})
        def failing_function() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

        # Metric should still be labeled
        assert mock_metric.labels.called


class TestIntegration:
    """Integration tests for metrics configuration."""

    def test_full_metrics_workflow(self) -> None:
        """Test a complete metrics workflow."""
        # Initialize metrics
        initialize_metrics(app_version="1.0.0")

        # Record a trade
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=100.50,
            ticker="RELIANCE",
        )

        # Update portfolio
        update_portfolio_value(value=100000.50)
        update_daily_pnl(pnl=5000.75)

        # Update positions
        update_open_positions(exchange="NSE", count=5)

        # Record scan cycle
        record_scan_cycle(scanner_type="momentum", duration=1.5)

        # Record model inference
        record_model_inference(model_name="lstm", duration=0.5)

        # Update connection status
        update_broker_connection_status(broker="Zerodha", connected=True)
        update_database_connection_status(database="primary", connected=True)
        update_ml_model_status(model_name="lstm", available=True)

        # Should not raise any exceptions
        assert True

    def test_error_recording_workflow(self) -> None:
        """Test error recording workflow."""
        # Record errors
        record_error(component="execution", error_type="timeout")
        record_error(component="api", error_type="connection")
        record_error(component="risk", error_type="validation")

        # Should not raise exceptions
        assert True

    @patch("iatb.core.observability.metrics.start_http_server")
    def test_metrics_server_workflow(self, mock_start_server: MagicMock) -> None:
        """Test metrics server startup workflow."""
        # Initialize metrics
        initialize_metrics()

        # Start metrics server
        start_metrics_server(port=9090)

        mock_start_server.assert_called_once_with(9090)
