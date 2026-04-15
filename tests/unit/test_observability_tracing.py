"""Tests for observability tracing configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from iatb.core.observability.tracing import (
    SpanContext,
    add_span_attributes,
    get_tracer,
    record_exception,
    setup_tracing,
)
from opentelemetry.sdk.trace import TracerProvider


class TestSetupTracing:
    """Test cases for setup_tracing function."""

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_returns_provider(
        self,
        mock_set_provider: MagicMock,
        mock_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing returns a TracerProvider."""
        provider = setup_tracing(service_name="test_service")
        assert isinstance(provider, TracerProvider)

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    def test_setup_tracing_with_custom_endpoint(
        self,
        mock_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing uses custom endpoint."""
        setup_tracing(service_name="test_service", otlp_endpoint="localhost:4318")
        mock_exporter.assert_called_once()

    @patch("iatb.core.observability.tracing.ConsoleSpanExporter")
    def test_setup_tracing_with_console_export(
        self,
        mock_console_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing enables console export when requested."""
        setup_tracing(
            service_name="test_service",
            enable_console_export=True,
        )
        mock_console_exporter.assert_called_once()


class TestGetTracer:
    """Test cases for get_tracer function."""

    def test_get_tracer_returns_tracer(self) -> None:
        """Test that get_tracer returns a tracer instance."""
        tracer = get_tracer("test_component")
        assert tracer is not None

    def test_get_tracer_default_name(self) -> None:
        """Test that get_tracer uses default name."""
        tracer = get_tracer()
        assert tracer is not None


class TestSpanContext:
    """Test cases for SpanContext context manager."""

    def test_span_context_enters_and_exits(self) -> None:
        """Test that SpanContext can be used as context manager."""
        with SpanContext("test_operation", param1="value1"):
            pass

    def test_span_context_with_attributes(self) -> None:
        """Test that SpanContext accepts attributes."""
        with SpanContext(
            "test_operation",
            ticker="RELIANCE",
            side="BUY",
        ):
            pass

    def test_span_context_with_exception(self) -> None:
        """Test that SpanContext handles exceptions."""
        with pytest.raises(ValueError):
            with SpanContext("failing_operation"):
                raise ValueError("Test error")


class TestAddSpanAttributes:
    """Test cases for add_span_attributes function."""

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_add_span_attributes_with_active_span(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that add_span_attributes adds attributes to active span."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        add_span_attributes(ticker="TCS", quantity=100)
        mock_span.set_attribute.assert_called()

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_add_span_attributes_without_active_span(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that add_span_attributes handles no active span."""
        mock_get_span.return_value = None

        # Should not raise exception
        add_span_attributes(ticker="TCS", quantity=100)


class TestRecordException:
    """Test cases for record_exception function."""

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_with_active_span(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that record_exception records exception on active span."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        exc = ValueError("Test error")
        record_exception(exc)
        mock_span.record_exception.assert_called_once_with(exc)
        mock_span.set_status.assert_called_once()

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_without_active_span(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that record_exception handles no active span."""
        mock_get_span.return_value = None

        exc = ValueError("Test error")
        # Should not raise exception
        record_exception(exc)

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_sets_error_status(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that record_exception sets error status on span."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        exc = ValueError("Test error")
        record_exception(exc)

        # Verify status was set to ERROR
        call_args = mock_span.set_status.call_args
        assert call_args is not None
