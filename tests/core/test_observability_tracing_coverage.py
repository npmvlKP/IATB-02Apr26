"""Coverage tests for iatb.core.observability.tracing module.

Tests OTel tracing setup, SpanContext, add_span_attributes, record_exception.
All external OTel exporters are mocked. No network calls.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.observability.tracing import (
    SpanContext,
    add_span_attributes,
    get_tracer,
    record_exception,
    setup_tracing,
)


class TestSetupTracing:
    """Tests for setup_tracing function."""

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_defaults(
        self, mock_trace: MagicMock, mock_otlp: MagicMock
    ) -> None:
        provider = setup_tracing()
        assert provider is not None
        mock_trace.set_tracer_provider.assert_called_once()

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_custom_service_name(
        self, mock_trace: MagicMock, mock_otlp: MagicMock
    ) -> None:
        provider = setup_tracing(service_name="test-svc")
        assert provider is not None

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_with_otlp_endpoint(
        self, mock_trace: MagicMock, mock_otlp: MagicMock
    ) -> None:
        setup_tracing(otlp_endpoint="localhost:4317")
        mock_otlp.assert_called_once_with(endpoint="localhost:4317", insecure=True)

    @patch("iatb.core.observability.tracing.ConsoleSpanExporter")
    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_console_export(
        self,
        mock_trace: MagicMock,
        mock_otlp: MagicMock,
        mock_console: MagicMock,
    ) -> None:
        setup_tracing(enable_console_export=True)
        mock_console.assert_called_once()

    @patch("iatb.core.observability.tracing.ConsoleSpanExporter")
    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_console_export_from_env(
        self,
        mock_trace: MagicMock,
        mock_otlp: MagicMock,
        mock_console: MagicMock,
    ) -> None:
        with patch.dict(os.environ, {"OTEL_CONSOLE_EXPORT": "true"}):
            setup_tracing()
            mock_console.assert_called_once()

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace")
    def test_setup_tracing_env_version(
        self, mock_trace: MagicMock, mock_otlp: MagicMock
    ) -> None:
        with patch.dict(os.environ, {"APP_VERSION": "2.0.0"}):
            provider = setup_tracing()
            assert provider is not None


class TestGetTracer:
    """Tests for get_tracer function."""

    @patch("iatb.core.observability.tracing.trace")
    def test_get_tracer_default(self, mock_trace: MagicMock) -> None:
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer
        result = get_tracer()
        mock_trace.get_tracer.assert_called_once_with("iatb")
        assert result is mock_tracer

    @patch("iatb.core.observability.tracing.trace")
    def test_get_tracer_custom_name(self, mock_trace: MagicMock) -> None:
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer
        get_tracer("custom-component")
        mock_trace.get_tracer.assert_called_once_with("custom-component")


class TestSpanContext:
    """Tests for SpanContext context manager."""

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_enter_exit(self, mock_get_tracer: MagicMock) -> None:
        mock_span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test-span", ticker="RELIANCE", side="BUY") as ctx:
            assert ctx.span is mock_span
        mock_span.set_attribute.assert_any_call("ticker", "RELIANCE")
        mock_span.set_attribute.assert_any_call("side", "BUY")

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_with_exception(self, mock_get_tracer: MagicMock) -> None:
        mock_span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm
        mock_get_tracer.return_value = mock_tracer

        with pytest.raises(ValueError, match="test error"):
            with SpanContext("error-span"):
                raise ValueError("test error")
        assert mock_span.set_status.called

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_no_attributes(self, mock_get_tracer: MagicMock) -> None:
        mock_span = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("bare-span"):
            pass
        mock_span.set_attribute.assert_not_called()

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_none_span(self, mock_get_tracer: MagicMock) -> None:
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=None)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_cm
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("null-span") as ctx:
            assert ctx.span is None


class TestAddSpanAttributes:
    """Tests for add_span_attributes function."""

    @patch("iatb.core.observability.tracing.trace")
    def test_add_attributes_to_active_span(self, mock_trace: MagicMock) -> None:
        mock_span = MagicMock()
        mock_trace.get_current_span.return_value = mock_span
        add_span_attributes(ticker="INFY", price="100.50")
        mock_span.set_attribute.assert_any_call("ticker", "INFY")
        mock_span.set_attribute.assert_any_call("price", "100.50")

    @patch("iatb.core.observability.tracing.trace")
    def test_add_attributes_no_active_span(self, mock_trace: MagicMock) -> None:
        mock_trace.get_current_span.return_value = None
        add_span_attributes(key="value")


class TestRecordException:
    """Tests for record_exception function."""

    @patch("iatb.core.observability.tracing.trace")
    def test_record_exception_on_active_span(self, mock_trace: MagicMock) -> None:
        mock_span = MagicMock()
        mock_trace.get_current_span.return_value = mock_span
        exc = RuntimeError("test runtime error")
        record_exception(exc)
        mock_span.record_exception.assert_called_once_with(exc)
        assert mock_span.set_status.called

    @patch("iatb.core.observability.tracing.trace")
    def test_record_exception_no_active_span(self, mock_trace: MagicMock) -> None:
        mock_trace.get_current_span.return_value = None
        record_exception(ValueError("no span error"))

    @patch("iatb.core.observability.tracing.trace")
    def test_record_exception_sets_error_status(self, mock_trace: MagicMock) -> None:
        mock_span = MagicMock()
        mock_trace.get_current_span.return_value = mock_span
        record_exception(TypeError("type error"))
        mock_span.set_status.assert_called_once()
        # Verify set_status was called with a single argument
        args, _kwargs = mock_span.set_status.call_args
        assert len(args) == 1
