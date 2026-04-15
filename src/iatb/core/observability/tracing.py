"""OpenTelemetry tracing configuration for distributed tracing."""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_tracing(
    service_name: str = "iatb",
    otlp_endpoint: str | None = None,
    enable_console_export: bool = False,
) -> TracerProvider:
    """Configure OpenTelemetry tracing for the application.

    Args:
        service_name: Name of the service being traced.
        otlp_endpoint: OTLP endpoint for trace export (e.g., "localhost:4317").
                       If None, reads from OTEL_EXPORTER_OTLP_ENDPOINT env var.
        enable_console_export: If True, export spans to console (for debugging).

    Returns:
        Configured TracerProvider.
    """
    # Create resource with service information
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            "service.version": os.getenv("APP_VERSION", "0.1.0"),
            "environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint is configured
    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

    if endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Add console exporter if enabled (useful for local development)
    if enable_console_export or os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true":
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    return provider


def get_tracer(name: str = "iatb") -> trace.Tracer:
    """Get a tracer instance.

    Args:
        name: Name of the tracer component.

    Returns:
        Tracer instance.
    """
    return trace.get_tracer(name)


class SpanContext:
    """Context manager for creating named spans with automatic context propagation.

    Example:
        >>> with SpanContext("execute_trade", ticker="RELIANCE", side="BUY"):
        ...     # Trading logic here
        ...     pass
    """

    def __init__(self, name: str, **attributes: Any) -> None:
        """Initialize span context.

        Args:
            name: Span name.
            **attributes: Key-value pairs to add as span attributes.
        """
        self.name = name
        self.attributes = attributes
        self.tracer = get_tracer()
        self.span_cm: Any = None
        self.span: trace.Span | None = None

    def __enter__(self) -> SpanContext:
        """Enter context and create span."""
        self.span_cm = self.tracer.start_as_current_span(self.name)
        self.span = self.span_cm.__enter__()
        if self.span:
            for key, value in self.attributes.items():
                self.span.set_attribute(key, str(value))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and end span."""
        if self.span:
            if exc_type is not None:
                self.span.set_status(
                    trace.Status(
                        trace.StatusCode.ERROR,
                        f"{exc_type.__name__}: {exc_val}",
                    )
                )
        if self.span_cm:
            self.span_cm.__exit__(exc_type, exc_val, exc_tb)


def add_span_attributes(**attributes: Any) -> None:
    """Add attributes to the current active span.

    Args:
        **attributes: Key-value pairs to add as span attributes.
    """
    current_span = trace.get_current_span()
    if current_span:
        for key, value in attributes.items():
            current_span.set_attribute(key, str(value))


def record_exception(exception: Exception) -> None:
    """Record an exception on the current active span.

    Args:
        exception: The exception to record.
    """
    current_span = trace.get_current_span()
    if current_span:
        current_span.record_exception(exception)
        current_span.set_status(
            trace.Status(
                trace.StatusCode.ERROR,
                f"{exception.__class__.__name__}: {exception}",
            )
        )
