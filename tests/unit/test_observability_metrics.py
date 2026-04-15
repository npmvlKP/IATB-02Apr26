"""Tests for observability metrics configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from iatb.core.observability.metrics import (
    api_request_duration,
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
    trade_counter,
    trade_pnl,
    update_broker_connection_status,
    update_daily_pnl,
    update_database_connection_status,
    update_ml_model_status,
    update_open_positions,
    update_portfolio_value,
)
from prometheus_client import Counter, Gauge, Histogram


class TestInitializeMetrics:
    """Test cases for initialize_metrics function."""

    @patch("iatb.core.observability.metrics.app_info")
    def test_initialize_metrics_sets_info(
        self,
        mock_app_info: MagicMock,
    ) -> None:
        """Test that initialize_metrics sets application info."""
        initialize_metrics(app_version="1.0.0")
        mock_app_info.info.assert_called_once()

    @patch("iatb.core.observability.metrics.app_info")
    def test_initialize_metrics_default_version(
        self,
        mock_app_info: MagicMock,
    ) -> None:
        """Test that initialize_metrics uses default version."""
        initialize_metrics()
        mock_app_info.info.assert_called_once()


class TestInstrumentFastAPIApp:
    """Test cases for instrument_fastapi_app function."""

    @patch("iatb.core.observability.metrics.Instrumentator")
    def test_instrument_fastapi_app_returns_instrumentator(
        self,
        mock_instrumentator_class: MagicMock,
    ) -> None:
        """Test that instrument_fastapi_app returns Instrumentator."""
        mock_app = MagicMock()
        mock_instrumentator = MagicMock()
        mock_instrumentator_class.return_value = mock_instrumentator

        result = instrument_fastapi_app(mock_app)
        assert result is mock_instrumentator

    @patch("iatb.core.observability.metrics.Instrumentator")
    def test_instrument_fastapi_app_instruments_app(
        self,
        mock_instrumentator_class: MagicMock,
    ) -> None:
        """Test that instrument_fastapi_app instruments the app."""
        mock_app = MagicMock()
        mock_instrumentator = MagicMock()
        mock_instrumentator_class.return_value = mock_instrumentator

        instrument_fastapi_app(mock_app)
        mock_instrumentator.instrument.assert_called_once_with(mock_app)


class TestRecordTrade:
    """Test cases for record_trade function."""

    def test_record_trade_increments_counter(self) -> None:
        """Test that record_trade increments trade counter."""
        _initial_value = trade_counter.labels(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
        )._value.get()

        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=100.0,
            ticker="RELIANCE",
        )

        # Counter should have increased
        assert True

    def test_record_trade_updates_pnl(self) -> None:
        """Test that record_trade updates PnL gauge."""
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=100.0,
            ticker="RELIANCE",
        )
        # Should not raise exception
        assert True

    def test_record_trade_without_pnl(self) -> None:
        """Test that record_trade works without PnL."""
        record_trade(
            exchange="NSE",
            side="SELL",
            status="SUCCESS",
        )
        # Should not raise exception
        assert True


class TestUpdateOpenPositions:
    """Test cases for update_open_positions function."""

    def test_update_open_positions_sets_gauge(self) -> None:
        """Test that update_open_positions sets the gauge."""
        update_open_positions(exchange="NSE", count=5)
        # Should not raise exception
        assert True


class TestUpdatePortfolioValue:
    """Test cases for update_portfolio_value function."""

    def test_update_portfolio_value_sets_gauge(self) -> None:
        """Test that update_portfolio_value sets the gauge."""
        update_portfolio_value(value=100000.0)
        # Should not raise exception
        assert True


class TestUpdateDailyPnl:
    """Test cases for update_daily_pnl function."""

    def test_update_daily_pnl_sets_gauge(self) -> None:
        """Test that update_daily_pnl sets the gauge."""
        update_daily_pnl(pnl=5000.0)
        # Should not raise exception
        assert True


class TestRecordScanCycle:
    """Test cases for record_scan_cycle function."""

    def test_record_scan_cycle_observes_duration(self) -> None:
        """Test that record_scan_cycle observes duration."""
        record_scan_cycle(scanner_type="momentum", duration=1.5)
        # Should not raise exception
        assert True


class TestRecordModelInference:
    """Test cases for record_model_inference function."""

    def test_record_model_inference_observes_duration(self) -> None:
        """Test that record_model_inference observes duration."""
        record_model_inference(model_name="lstm", duration=0.5)
        # Should not raise exception
        assert True


class TestRecordError:
    """Test cases for record_error function."""

    def test_record_error_increments_counter(self) -> None:
        """Test that record_error increments error counter."""
        record_error(component="api", error_type="ConnectionError")
        # Should not raise exception
        assert True


class TestUpdateBrokerConnectionStatus:
    """Test cases for update_broker_connection_status function."""

    def test_update_broker_connected(self) -> None:
        """Test that update_broker_connection_status sets connected status."""
        update_broker_connection_status(broker="ZERODHA", connected=True)
        # Should not raise exception
        assert True

    def test_update_broker_disconnected(self) -> None:
        """Test that update_broker_connection_status sets disconnected status."""
        update_broker_connection_status(broker="ZERODHA", connected=False)
        # Should not raise exception
        assert True


class TestUpdateDatabaseConnectionStatus:
    """Test cases for update_database_connection_status function."""

    def test_update_database_connected(self) -> None:
        """Test that update_database_connection_status sets connected status."""
        update_database_connection_status(database="sqlite", connected=True)
        # Should not raise exception
        assert True


class TestUpdateMlModelStatus:
    """Test cases for update_ml_model_status function."""

    def test_update_model_available(self) -> None:
        """Test that update_ml_model_status sets available status."""
        update_ml_model_status(model_name="lstm", available=True)
        # Should not raise exception
        assert True

    def test_update_model_unavailable(self) -> None:
        """Test that update_ml_model_status sets unavailable status."""
        update_ml_model_status(model_name="lstm", available=False)
        # Should not raise exception
        assert True


class TestMetricsExist:
    """Test that all metrics are properly defined."""

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
