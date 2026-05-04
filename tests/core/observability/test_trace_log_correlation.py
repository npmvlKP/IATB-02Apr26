"""Tests for trace ↔ log correlation."""

import json
import logging
from unittest.mock import patch

import pytest
from iatb.core.observability.logging_config import JsonFormatter, setup_structured_logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


class TestTraceLogCorrelation:
    """Test trace ↔ log correlation functionality."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Setup observability for tests."""
        setup_structured_logging("DEBUG")
        # Set up tracing with test service name and disable exporters
        provider = TracerProvider(resource=Resource.create({"service.name": "iatb-test"}))
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    def test_trace_log_correlation_within_span(self) -> None:
        """Test that logs within a span contain trace context."""
        logger = logging.getLogger(__name__)

        # Capture log records
        class ListStream:
            def __init__(self) -> None:
                self.records: list[str] = []

            def write(self, record: str) -> None:
                self.records.append(record)

            def flush(self) -> None:
                pass

        log_stream = ListStream()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        tracer = trace.get_tracer(__name__)
        mock_config = type("Config", (), {"service": {"name": "iatb-test"}})
        with patch("iatb.core.config.get_config", return_value=mock_config):
            with tracer.start_as_current_span("test-span") as span:
                logger.info("Test log message")

        # Cleanup
        logger.removeHandler(handler)

        # Verify log record contains trace_id and span_id
        assert len(log_stream.records) == 1
        log_data = json.loads(log_stream.records[0])

        # Check trace_id and span_id exist
        assert "trace_id" in log_data
        assert "span_id" in log_data
        assert "service.name" in log_data

        # Verify they are valid hex strings
        assert isinstance(log_data["trace_id"], str)
        assert len(log_data["trace_id"]) == 32
        assert isinstance(log_data["span_id"], str)
        assert len(log_data["span_id"]) == 16
        assert log_data["service.name"] == "iatb-test"

        # Verify they match the span context
        span_context = span.get_span_context()
        assert log_data["trace_id"] == format(span_context.trace_id, "032x")
        assert log_data["span_id"] == format(span_context.span_id, "016x")

    def test_trace_log_correlation_outside_span(self) -> None:
        """Test that logs outside a span do not contain trace context."""
        logger = logging.getLogger(__name__)

        # Capture log records
        class ListStream:
            def __init__(self) -> None:
                self.records: list[str] = []

            def write(self, record: str) -> None:
                self.records.append(record)

            def flush(self) -> None:
                pass

        log_stream = ListStream()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Log outside any span
        logger.info("Test log message without span")

        # Cleanup
        logger.removeHandler(handler)

        # Verify log record does not contain trace_id or span_id
        assert len(log_stream.records) == 1
        log_data = json.loads(log_stream.records[0])

        # Check trace_id and span_id do not exist
        assert "trace_id" not in log_data
        assert "span_id" not in log_data
        assert "service.name" in log_data
        assert log_data["service.name"] == "iatb-test"
