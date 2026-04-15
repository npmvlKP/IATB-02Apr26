# Optimization 9: Observability Stack Implementation

## Overview

This optimization implements a production-ready observability stack for the IATB (Interactive Algorithmic Trading Bot) system, providing comprehensive monitoring, tracing, metrics, and alerting capabilities.

## Components Implemented

### 1. JSON Structured Logging
**Location:** `src/iatb/core/observability/logging_config.py`

Features:
- JSON-formatted logs with `python-json-logger`
- UTC timestamps for all log entries
- Structured context support via `LogContext` context manager
- Automatic exception formatting
- Configurable log levels and formats

Usage:
```python
from iatb.core.observability import get_logger, LogContext

_LOGGER = get_logger(__name__)

# Basic logging
_LOGGER.info("Processing trade", extra={"ticker": "RELIANCE"})

# With context
with LogContext(user_id="123", action="trade"):
    _LOGGER.info("Executing trade")
```

### 2. OpenTelemetry Distributed Tracing
**Location:** `src/iatb/core/observability/tracing.py`

Features:
- OpenTelemetry SDK integration
- OTLP exporter for trace data
- Console exporter for local development
- Span context management
- Automatic exception recording

Usage:
```python
from iatb.core.observability import SpanContext, add_span_attributes

# Create a span
with SpanContext("execute_trade", ticker="RELIANCE", side="BUY"):
    # Trading logic here
    add_span_attributes(quantity=100, price=2500.0)
```

Configuration:
```bash
# Environment variables
export OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"
export OTEL_CONSOLE_EXPORT="true"  # For local development
```

### 3. Prometheus Metrics
**Location:** `src/iatb/core/observability/metrics.py`

Metrics Implemented:
- **Business Metrics:**
  - `iatb_trades_total` - Trade execution counter
  - `iatb_trade_pnl` - Trade PnL gauge
  - `iatb_open_positions` - Open positions count
  - `iatb_portfolio_value` - Portfolio value
  - `iatb_daily_pnl` - Daily PnL

- **System Metrics:**
  - `iatb_api_request_duration_seconds` - API request duration histogram
  - `iatb_api_requests_total` - API request counter
  - `iatb_scan_cycle_duration_seconds` - Scan cycle duration
  - `iatb_model_inference_duration_seconds` - Model inference duration

- **Error Metrics:**
  - `iatb_errors_total` - Error counter

- **Health Metrics:**
  - `iatb_broker_connection_status` - Broker connection status
  - `iatb_database_connection_status` - Database connection status
  - `iatb_ml_model_status` - ML model status

Usage:
```python
from iatb.core.observability import (
    record_trade,
    update_portfolio_value,
    record_error,
    update_broker_connection_status
)

# Record a trade
record_trade(
    exchange="NSE",
    side="BUY",
    status="SUCCESS",
    pnl=100.0,
    ticker="RELIANCE"
)

# Update portfolio value
update_portfolio_value(100000.0)

# Record error
record_error(component="api", error_type="ConnectionError")

# Update broker status
update_broker_connection_status("ZERODHA", connected=True)
```

**Endpoint:** `GET /metrics` - Prometheus metrics endpoint

### 4. Telegram Alerting
**Location:** `src/iatb/core/observability/alerting.py`

Features:
- Trade execution alerts
- Error alerts
- Health status alerts
- PnL alerts
- ML model status alerts
- Actionable alerts with buttons
- Markdown formatting
- Graceful error handling

Usage:
```python
from iatb.core.observability import get_alerter, TelegramAlertLevel

alerter = get_alerter()

# Send trade alert
alerter.send_trade_alert(
    ticker="RELIANCE",
    side="BUY",
    quantity=100,
    price=2500.0
)

# Send error alert
alerter.send_error_alert(
    component="api",
    error_message="Connection failed",
    exc_type="ConnectionError"
)

# Send health alert
alerter.send_health_alert(
    service="broker",
    status="DOWN",
    details="Connection lost"
)
```

Configuration:
```bash
# Environment variables (optional)
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

## Integration with FastAPI

The observability stack is automatically initialized on FastAPI startup:

```python
# src/iatb/fastapi_app.py
@app.on_event("startup")
async def startup_event() -> None:
    """Initialize API and observability on startup."""
    # Initialize observability
    initialize_metrics(app_version="0.1.0")
    instrument_fastapi_app(app)
    _LOGGER.info("Observability stack initialized")
    
    # Initialize API
    get_api()
    _LOGGER.info("IATB FastAPI app started")
```

All FastAPI endpoints are automatically instrumented with:
- Request duration metrics
- Request count metrics
- Structured logging
- Distributed tracing (if configured)

## Test Coverage

Comprehensive test suite covering all observability components:

- **Logging Tests:** `tests/unit/test_observability_logging.py`
  - JSON formatter functionality
  - Logger configuration
  - Context manager behavior

- **Tracing Tests:** `tests/unit/test_observability_tracing.py`
  - Tracer provider setup
  - Span creation and management
  - Exception recording

- **Metrics Tests:** `tests/unit/test_observability_metrics.py`
  - Metric initialization
  - Recording functions
  - Gauge/Counter/Histogram operations

- **Alerting Tests:** `tests/unit/test_observability_alerting.py`
  - Telegram bot initialization
  - Alert sending
  - Error handling
  - Message formatting

## Dependencies Added

```toml
[tool.poetry.dependencies]
opentelemetry-api = "^1.28.0"
opentelemetry-sdk = "^1.28.0"
opentelemetry-instrumentation-fastapi = "^0.49b0"
opentelemetry-instrumentation-logging = "^0.49b0"
opentelemetry-exporter-otlp = "^1.28.0"
opentelemetry-exporter-prometheus = "^0.49b0"
prometheus-client = "^0.21.0"
prometheus-fastapi-instrumentator = "^7.0.0"
python-json-logger = "^3.2.1"
```

## Deployment

### Local Development

1. Install dependencies:
```bash
poetry install
```

2. Configure environment variables (optional):
```bash
# For tracing
export OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"
export OTEL_CONSOLE_EXPORT="true"

# For alerting
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

3. Run the application:
```bash
poetry run uvicorn iatb.fastapi_app:app --reload
```

4. Access metrics:
```bash
curl http://localhost:8000/metrics
```

### Production Deployment

1. Set up Prometheus server:
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'iatb'
    static_configs:
      - targets: ['iatb-app:8000']
```

2. Set up OTLP collector (optional):
```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
  
  logging:
    loglevel: debug

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [logging]
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

3. Configure Grafana dashboards for visualization

## Monitoring Dashboard

Key metrics to monitor:

### Business Metrics
- Trade execution rate and success rate
- Portfolio value trends
- Daily PnL
- Open positions count

### System Metrics
- API request latency (p50, p95, p99)
- API error rate
- Scan cycle duration
- Model inference time

### Health Metrics
- Broker connection status
- Database connection status
- ML model availability

## Alerting Rules

Recommended Prometheus alerting rules:

```yaml
groups:
  - name: iatb_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(iatb_api_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        annotations:
          summary: "High error rate detected"
      
      - alert: BrokerDisconnected
        expr: iatb_broker_connection_status == 0
        for: 2m
        annotations:
          summary: "Broker connection lost"
      
      - alert: DailyPnLThreshold
        expr: abs(iatb_daily_pnl) > 10000
        annotations:
          summary: "Daily PnL exceeds threshold"
```

## Troubleshooting

### Metrics not appearing
1. Check `/metrics` endpoint is accessible
2. Verify Prometheus is scraping the endpoint
3. Check application logs for initialization errors

### Tracing not working
1. Verify OTLP endpoint is configured
2. Check OTLP collector is running
3. Enable console export for debugging

### Telegram alerts not sending
1. Verify bot token and chat ID are set
2. Check bot has permission to send messages
3. Verify network connectivity to Telegram API

## Security Considerations

1. **Telegram Credentials:** Store `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in secure secrets manager
2. **OTLP Endpoint:** Use TLS for production deployments
3. **Metrics Access:** Restrict `/metrics` endpoint to internal networks
4. **Log Data:** Avoid logging sensitive information (API keys, secrets)

## Performance Impact

- **Logging:** JSON formatting adds minimal overhead (~5-10%)
- **Metrics:** Prometheus client is lightweight (<1% overhead)
- **Tracing:** OpenTelemetry adds ~5-15% overhead (configurable)
- **Alerting:** Telegram calls are asynchronous and non-blocking

## Future Enhancements

1. Add Grafana dashboard templates
2. Implement custom metric collectors
3. Add alert routing based on severity
4. Implement log aggregation (ELK stack)
5. Add distributed tracing visualization (Jaeger)
6. Implement anomaly detection on metrics

## Related Documentation

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)
- [IATB Configuration Guide](config/README.md)

## Support

For issues or questions:
1. Check application logs
2. Review test cases for usage examples
3. Consult this documentation
4. Open an issue in the repository