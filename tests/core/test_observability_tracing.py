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
    """Tests for setup_tracing function."""

    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_creates_provider(self, mock_set_provider: MagicMock) -> None:
        """Test that setup_tracing creates a TracerProvider."""
        provider = setup_tracing()
        assert isinstance(provider, TracerProvider)

    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_sets_global_provider(self, mock_set_provider: MagicMock) -> None:
        """Test that setup_tracing sets global tracer provider."""
        provider = setup_tracing()
        mock_set_provider.assert_called_once_with(provider)

    @patch("iatb.core.observability.tracing.OTLPSpanExporter")
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_with_otlp_endpoint(
        self,
        mock_set_provider: MagicMock,
        mock_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing configures OTLP exporter."""
        setup_tracing(otlp_endpoint="localhost:4317")
        mock_exporter.assert_called_once()

    @patch("iatb.core.observability.tracing.ConsoleSpanExporter")
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_with_console_export(
        self,
        mock_set_provider: MagicMock,
        mock_console_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing can enable console export."""
        setup_tracing(enable_console_export=True)
        mock_console_exporter.assert_called_once()

    @patch.dict("os.environ", {"OTEL_CONSOLE_EXPORT": "true"})
    @patch("iatb.core.observability.tracing.ConsoleSpanExporter")
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_with_console_export_env_var(
        self,
        mock_set_provider: MagicMock,
        mock_console_exporter: MagicMock,
    ) -> None:
        """Test that setup_tracing respects console export env var."""
        setup_tracing()
        mock_console_exporter.assert_called_once()

    @patch.dict("os.environ", {"APP_VERSION": "1.0.0"})
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_with_custom_version(self, mock_set_provider: MagicMock) -> None:
        """Test that setup_tracing uses custom version from env."""
        provider = setup_tracing()
        # Provider should be created with version from env
        assert isinstance(provider, TracerProvider)

    @patch.dict("os.environ", {"ENVIRONMENT": "production"})
    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_setup_tracing_with_custom_environment(self, mock_set_provider: MagicMock) -> None:
        """Test that setup_tracing uses custom environment from env."""
        provider = setup_tracing()
        assert isinstance(provider, TracerProvider)


class TestGetTracer:
    """Tests for get_tracer function."""

    @patch("iatb.core.observability.tracing.trace.get_tracer")
    def test_get_tracer_returns_tracer(self, mock_get_tracer: MagicMock) -> None:
        """Test that get_tracer returns a tracer."""
        mock_tracer = MagicMock()
        mock_get_tracer.return_value = mock_tracer

        tracer = get_tracer("test_tracer")

        assert tracer is mock_tracer
        mock_get_tracer.assert_called_once_with("test_tracer")

    @patch("iatb.core.observability.tracing.trace.get_tracer")
    def test_get_tracer_with_default_name(self, mock_get_tracer: MagicMock) -> None:
        """Test that get_tracer uses default name when none provided."""
        mock_tracer = MagicMock()
        mock_get_tracer.return_value = mock_tracer

        tracer = get_tracer()

        assert tracer is mock_tracer
        mock_get_tracer.assert_called_once_with("iatb")


class TestSpanContext:
    """Tests for SpanContext context manager."""

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_creates_span(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext creates a span."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test_span"):
            pass

        mock_tracer.start_as_current_span.assert_called_once_with("test_span")

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_adds_attributes(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext adds attributes to span."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test_span", ticker="RELIANCE", side="BUY"):
            pass

        mock_span.set_attribute.assert_any_call("ticker", "RELIANCE")
        mock_span.set_attribute.assert_any_call("side", "BUY")

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_with_exception(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext handles exceptions correctly."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with patch("iatb.core.observability.tracing.trace.Status") as _mock_status:
            with pytest.raises(ValueError):
                with SpanContext("test_span"):
                    raise ValueError("Test exception")

            # Should set error status
            assert mock_span.set_status.called

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_exits_properly(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext exits span properly."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test_span"):
            pass

        mock_span_cm.__exit__.assert_called_once()

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_with_no_exception(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext doesn't set error status on success."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test_span"):
            pass

        # Should not set error status
        assert not mock_span.set_status.called

    @patch("iatb.core.observability.tracing.get_tracer")
    def test_span_context_with_empty_attributes(self, mock_get_tracer: MagicMock) -> None:
        """Test that SpanContext works with no attributes."""
        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)
        mock_get_tracer.return_value = mock_tracer

        with SpanContext("test_span"):
            pass

        # Should still create span
        mock_tracer.start_as_current_span.assert_called_once()


class TestAddSpanAttributes:
    """Tests for add_span_attributes function."""

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_add_span_attributes_with_active_span(self, mock_get_span: MagicMock) -> None:
        """Test that add_span_attributes adds attributes to current span."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        add_span_attributes(user_id="123", action="test")

        mock_span.set_attribute.assert_any_call("user_id", "123")
        mock_span.set_attribute.assert_any_call("action", "test")

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_add_span_attributes_with_no_active_span(self, mock_get_span: MagicMock) -> None:
        """Test that add_span_attributes handles no active span gracefully."""
        mock_get_span.return_value = None

        # Should not raise exception
        add_span_attributes(user_id="123", action="test")

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_add_span_attributes_with_multiple_attributes(self, mock_get_span: MagicMock) -> None:
        """Test that add_span_attributes adds multiple attributes."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        add_span_attributes(
            user_id="123",
            action="test",
            ticker="RELIANCE",
            side="BUY",
        )

        assert mock_span.set_attribute.call_count == 4


class TestRecordException:
    """Tests for record_exception function."""

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_with_active_span(self, mock_get_span: MagicMock) -> None:
        """Test that record_exception records exception on current span."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        exception = ValueError("Test exception")
        record_exception(exception)

        mock_span.record_exception.assert_called_once_with(exception)

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_sets_error_status(self, mock_get_span: MagicMock) -> None:
        """Test that record_exception sets error status."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        exception = ValueError("Test exception")
        record_exception(exception)

        assert mock_span.set_status.called

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_with_no_active_span(self, mock_get_span: MagicMock) -> None:
        """Test that record_exception handles no active span gracefully."""
        mock_get_span.return_value = None

        exception = ValueError("Test exception")
        # Should not raise exception
        record_exception(exception)

    @patch("iatb.core.observability.tracing.trace.get_current_span")
    def test_record_exception_with_different_exception_types(
        self,
        mock_get_span: MagicMock,
    ) -> None:
        """Test that record_exception works with different exception types."""
        mock_span = MagicMock()
        mock_get_span.return_value = mock_span

        exceptions = [
            ValueError("Value error"),
            TypeError("Type error"),
            RuntimeError("Runtime error"),
            KeyError("Key error"),
        ]

        for exc in exceptions:
            record_exception(exc)

        assert mock_span.record_exception.call_count == len(exceptions)


class TestIntegration:
    """Integration tests for tracing configuration."""

    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_tracing_end_to_end(self, mock_set_provider: MagicMock) -> None:
        """Test tracing setup and span creation end-to-end."""
        setup_tracing(service_name="test_service")

        tracer = get_tracer("test_tracer")
        assert tracer is not None

    @patch("iatb.core.observability.tracing.trace.set_tracer_provider")
    def test_nested_spans(self, mock_set_provider: MagicMock) -> None:
        """Test that nested spans work correctly."""
        setup_tracing()

        mock_tracer = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span = MagicMock(return_value=mock_span_cm)

        with patch("iatb.core.observability.tracing.get_tracer", return_value=mock_tracer):
            with SpanContext("outer_span"):
                with SpanContext("inner_span"):
                    pass

        assert mock_tracer.start_as_current_span.call_count == 2
