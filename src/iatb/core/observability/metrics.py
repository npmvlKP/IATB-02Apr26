"""Prometheus metrics configuration for monitoring trading bot performance."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    Summary,
    start_http_server,
)
from prometheus_fastapi_instrumentator import Instrumentator

# Business metrics
trade_counter = Counter(
    "iatb_trades_total",
    "Total number of trades executed",
    ["exchange", "side", "status"],
)

trade_pnl = Gauge(
    "iatb_trade_pnl",
    "Profit/loss of the last trade",
    ["exchange", "ticker"],
)

open_positions = Gauge(
    "iatb_open_positions",
    "Number of currently open positions",
    ["exchange"],
)

portfolio_value = Gauge(
    "iatb_portfolio_value",
    "Current portfolio value",
)

daily_pnl = Gauge(
    "iatb_daily_pnl",
    "Daily profit/loss",
)

# System metrics
api_request_duration = Histogram(
    "iatb_api_request_duration_seconds",
    "API request duration",
    ["endpoint", "method"],
)

api_request_counter = Counter(
    "iatb_api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"],
)

scan_cycle_duration = Histogram(
    "iatb_scan_cycle_duration_seconds",
    "Scan cycle duration",
    ["scanner_type"],
)

model_inference_duration = Histogram(
    "iatb_model_inference_duration_seconds",
    "Model inference duration",
    ["model_name"],
)

# Error metrics
error_counter = Counter(
    "iatb_errors_total",
    "Total number of errors",
    ["component", "error_type"],
)

# Health metrics
broker_connection_status = Gauge(
    "iatb_broker_connection_status",
    "Broker connection status (1=connected, 0=disconnected)",
    ["broker"],
)

database_connection_status = Gauge(
    "iatb_database_connection_status",
    "Database connection status (1=connected, 0=disconnected)",
    ["database"],
)

ml_model_status = Gauge(
    "iatb_ml_model_status",
    "ML model status (1=available, 0=unavailable)",
    ["model_name"],
)

# Info metrics
app_info = Info(
    "iatb_app_info",
    "Application information",
)


def initialize_metrics(app_version: str = "0.1.0") -> None:
    """Initialize application info metrics.

    Args:
        app_version: Application version string.
    """
    app_info.info(
        {
            "version": app_version,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "deployment_time": datetime.now(UTC).isoformat(),
        }
    )


def instrument_fastapi_app(app: Any) -> Instrumentator:
    """Instrument FastAPI application with Prometheus metrics.

    Args:
        app: FastAPI application instance.

    Returns:
        Configured Instrumentator instance.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_group_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="fastapi_inprogress",
        inprogress_labels=True,
    )

    instrumentator.instrument(app)

    return instrumentator


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server.

    Args:
        port: Port to serve metrics on.
    """
    start_http_server(port)


def record_trade(
    exchange: str,
    side: str,
    status: str,
    pnl: float | None = None,
    ticker: str | None = None,
) -> None:
    """Record a trade execution.

    Args:
        exchange: Exchange name.
        side: Trade side (BUY/SELL).
        status: Trade status (SUCCESS/FAILED).
        pnl: Profit/loss amount (if applicable).
        ticker: Ticker symbol (if applicable).
    """
    trade_counter.labels(exchange=exchange, side=side, status=status).inc()

    if pnl is not None and ticker is not None:
        trade_pnl.labels(exchange=exchange, ticker=ticker).set(pnl)


def update_open_positions(exchange: str, count: int) -> None:
    """Update open positions count.

    Args:
        exchange: Exchange name.
        count: Number of open positions.
    """
    open_positions.labels(exchange=exchange).set(count)


def update_portfolio_value(value: float) -> None:
    """Update portfolio value.

    Args:
        value: Current portfolio value.
    """
    portfolio_value.set(value)


def update_daily_pnl(pnl: float) -> None:
    """Update daily profit/loss.

    Args:
        pnl: Daily profit/loss amount.
    """
    daily_pnl.set(pnl)


def record_scan_cycle(scanner_type: str, duration: float) -> None:
    """Record scan cycle duration.

    Args:
        scanner_type: Type of scanner.
        duration: Duration in seconds.
    """
    scan_cycle_duration.labels(scanner_type=scanner_type).observe(duration)


def record_model_inference(model_name: str, duration: float) -> None:
    """Record model inference duration.

    Args:
        model_name: Name of the model.
        duration: Duration in seconds.
    """
    model_inference_duration.labels(model_name=model_name).observe(duration)


def record_error(component: str, error_type: str) -> None:
    """Record an error.

    Args:
        component: Component where error occurred.
        error_type: Type of error.
    """
    error_counter.labels(component=component, error_type=error_type).inc()


def update_broker_connection_status(broker: str, connected: bool) -> None:
    """Update broker connection status.

    Args:
        broker: Broker name.
        connected: Whether broker is connected.
    """
    broker_connection_status.labels(broker=broker).set(1 if connected else 0)


def update_database_connection_status(database: str, connected: bool) -> None:
    """Update database connection status.

    Args:
        database: Database name.
        connected: Whether database is connected.
    """
    database_connection_status.labels(database=database).set(1 if connected else 0)


def update_ml_model_status(model_name: str, available: bool) -> None:
    """Update ML model status.

    Args:
        model_name: Name of the ML model.
        available: Whether model is available.
    """
    ml_model_status.labels(model_name=model_name).set(1 if available else 0)


def track_execution_time(metric: Histogram | Summary, labels: dict[str, str]) -> Callable[..., Any]:
    """Decorator to track execution time of a function.

    Args:
        metric: Prometheus metric to update.
        labels: Labels to apply to the metric.

    Returns:
        Decorator function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with metric.labels(**labels).time():
                return func(*args, **kwargs)

        return wrapper

    return decorator
