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


# Data provider metrics
data_source_switches = Counter(
    "iatb_data_source_switches_total",
    "Total number of data source switches",
    ["from_provider", "to_provider", "method_name"],
)

data_source_latency = Histogram(
    "iatb_data_source_latency_seconds",
    "Data provider request latency",
    ["provider_name", "method_name"],
)


def record_data_source_switch(
    from_provider: str,
    to_provider: str,
    method_name: str,
) -> None:
    """Record a data source switch event.

    Args:
        from_provider: Name of the provider that failed.
        to_provider: Name of the provider being switched to.
        method_name: Name of the method being called.
    """
    data_source_switches.labels(
        from_provider=from_provider,
        to_provider=to_provider,
        method_name=method_name,
    ).inc()


def record_data_source_latency(
    provider_name: str,
    method_name: str,
    latency_seconds: float,
) -> None:
    """Record data provider request latency.

    Args:
        provider_name: Name of the provider.
        method_name: Name of the method called.
        latency_seconds: Latency in seconds.
    """
    data_source_latency.labels(
        provider_name=provider_name,
        method_name=method_name,
    ).observe(latency_seconds)


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


# Data source observability metrics
data_source_requests_total = Counter(
    "iatb_data_source_requests_total",
    "Total number of data source requests",
    ["source", "status"],
)

data_source_simple_latency = Histogram(
    "iatb_data_source_simple_latency_seconds",
    "Data source request latency in seconds (simple)",
    ["source"],
)

data_source_fallback_total = Counter(
    "iatb_data_source_fallback_total",
    "Total number of data source fallbacks",
    ["from_source", "to_source"],
)

data_freshness_seconds = Gauge(
    "iatb_data_freshness_seconds",
    "Data freshness in seconds since last update",
    ["source"],
)

kite_token_freshness = Gauge(
    "iatb_kite_token_freshness",
    "Kite token freshness (1=fresh, 0=expired)",
)


def record_data_source_request(source: str, status: str) -> None:
    """Record a data source request.

    Args:
        source: Data source name (e.g., "kite", "yfinance", "polygon").
        status: Request status (e.g., "success", "error", "timeout").
    """
    data_source_requests_total.labels(source=source, status=status).inc()


def record_data_source_request_latency(source: str, latency_seconds: float) -> None:
    """Record data source request latency.

    Args:
        source: Data source name.
        latency_seconds: Latency in seconds.
    """
    data_source_simple_latency.labels(source=source).observe(latency_seconds)


def record_data_source_fallback(from_source: str, to_source: str) -> None:
    """Record a data source fallback event.

    Args:
        from_source: Source that failed.
        to_source: Fallback source being used.
    """
    data_source_fallback_total.labels(from_source=from_source, to_source=to_source).inc()


def update_data_freshness(source: str, freshness_seconds: float) -> None:
    """Update data freshness for a source.

    Args:
        source: Data source name.
        freshness_seconds: Seconds since last data update.
    """
    data_freshness_seconds.labels(source=source).set(freshness_seconds)


def update_kite_token_freshness(is_fresh: bool) -> None:
    """Update Kite token freshness status.

    Args:
        is_fresh: True if token is fresh, False if expired.
    """
    kite_token_freshness.set(1 if is_fresh else 0)
