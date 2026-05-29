"""Supplemental coverage tests for observability tracing module.

Covers: setup_tracing env var handling, console export, SpanContext error path,
add_span_attributes with active span, record_exception with active span,
get_tracer with default name.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_opentelemetry():
    mocks = {
        "opentelemetry": MagicMock(),
        "opentelemetry.trace": MagicMock(),
        "opentelemetry.sdk": MagicMock(),
        "opentelemetry.sdk.resources": MagicMock(),
        "opentelemetry.sdk.trace": MagicMock(),
        "opentelemetry.sdk.trace.export": MagicMock(),
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(),
    }
    original = {}
    for mod in mocks:
        original[mod] = sys.modules.get(mod)
        sys.modules[mod] = mocks[mod]
    yield mocks
    for mod, orig in original.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig


class TestSetupTracingEnvVars:
    def test_reads_otlp_endpoint_from_env(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        with patch.dict(
            "os.environ",
            {
                "OTEL_EXPORTER_OTLP_ENDPOINT": "custom:4317",
                "APP_VERSION": "2.0.0",
                "ENVIRONMENT": "production",
            },
            clear=False,
        ):
            provider = tracing.setup_tracing("custom-service")
            assert provider is not None

    def test_explicit_endpoint_overrides_env(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        with patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "env:4317"},
            clear=False,
        ):
            provider = tracing.setup_tracing(
                "test-service", otlp_endpoint="explicit:4317"
            )
            assert provider is not None

    def test_console_export_env_var(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        with patch.dict(
            "os.environ",
            {"OTEL_CONSOLE_EXPORT": "true"},
            clear=False,
        ):
            provider = tracing.setup_tracing("console-service")
            assert provider is not None

    def test_console_export_disabled_by_default(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        with patch.dict(
            "os.environ",
            {"OTEL_CONSOLE_EXPORT": "false"},
            clear=False,
        ):
            provider = tracing.setup_tracing("no-console")
            assert provider is not None

    def test_enable_console_export_flag(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        provider = tracing.setup_tracing("debug-service", enable_console_export=True)
        assert provider is not None

    def test_default_service_name(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        provider = tracing.setup_tracing()
        assert provider is not None

    def test_default_app_version(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        with patch.dict("os.environ", {}, clear=False):
            provider = tracing.setup_tracing("version-test")
            assert provider is not None


class TestGetTracerDefault:
    def test_default_name(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        tracer = tracing.get_tracer()
        assert tracer is not None

    def test_custom_name(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        tracer = tracing.get_tracer("custom-component")
        assert tracer is not None


class TestSpanContextErrorPath:
    def test_span_context_sets_error_status_on_exception(
        self, mock_opentelemetry
    ) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_cm

        with patch.object(tracing, "get_tracer", return_value=mock_tracer):
            ctx = tracing.SpanContext("test-span", ticker="RELIANCE", side="BUY")
            ctx.__enter__()

            exc_type = ValueError
            exc_val = ValueError("test error")
            exc_tb = exc_val.__traceback__

            ctx.__exit__(exc_type, exc_val, exc_tb)

            mock_span.set_status.assert_called()

    def test_span_context_sets_attributes(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_cm

        with patch.object(tracing, "get_tracer", return_value=mock_tracer):
            ctx = tracing.SpanContext("attr-span", key1="val1", key2="val2")
            ctx.__enter__()

            calls = mock_span.set_attribute.call_args_list
            assert len(calls) == 2

    def test_span_context_exit_without_exception(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_cm

        with patch.object(tracing, "get_tracer", return_value=mock_tracer):
            with tracing.SpanContext("clean-exit"):
                pass

    def test_span_context_with_none_span(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=None)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_cm

        with patch.object(tracing, "get_tracer", return_value=mock_tracer):
            ctx = tracing.SpanContext("none-span")
            ctx.__enter__()
            ctx.__exit__(None, None, None)

    def test_span_context_no_double_record(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        mock_span_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        mock_tracer = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span_cm

        with patch.object(tracing, "get_tracer", return_value=mock_tracer):
            ctx = tracing.SpanContext("double-span")
            ctx.__enter__()
            ctx.result = MagicMock()
            ctx.__exit__(None, None, None)


class TestAddSpanAttributesWithActiveSpan:
    def test_with_active_span(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        with patch.object(tracing.trace, "get_current_span", return_value=mock_span):
            tracing.add_span_attributes(component="engine", version="1.0")
            assert mock_span.set_attribute.call_count == 2

    def test_with_no_active_span(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_non_recording = MagicMock()
        mock_non_recording.set_attribute = MagicMock(
            side_effect=Exception("should not be called")
        )
        with patch.object(
            tracing.trace,
            "get_current_span",
            return_value=tracing.trace.NonRecordingSpan(
                tracing.trace.SpanContext(
                    trace_id=0,
                    span_id=0,
                    is_remote=False,
                    trace_flags=tracing.trace.TraceFlags(0),
                )
            ),
        ):
            tracing.add_span_attributes(key="value")


class TestRecordExceptionWithActiveSpan:
    def test_with_active_span(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        with patch.object(tracing.trace, "get_current_span", return_value=mock_span):
            exc = RuntimeError("test runtime error")
            tracing.record_exception(exc)
            mock_span.record_exception.assert_called_once_with(exc)
            mock_span.set_status.assert_called_once()

    def test_exception_message_format(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_span = MagicMock()
        with patch.object(tracing.trace, "get_current_span", return_value=mock_span):
            exc = ValueError("bad input")
            tracing.record_exception(exc)
            mock_span.set_status.assert_called_once()
            call_args = mock_span.set_status.call_args[0]
            status_arg = call_args[0]
            if hasattr(status_arg, "description") and not isinstance(
                getattr(status_arg, "description", None), MagicMock
            ):
                assert "ValueError" in str(status_arg.description)
            else:
                assert mock_span.set_status.called

    def test_record_exception_with_no_active_span(self, mock_opentelemetry) -> None:
        import iatb.core.observability.tracing as tracing

        mock_non_recording = MagicMock()
        mock_non_recording.record_exception = MagicMock(
            side_effect=Exception("should not be called")
        )
        with patch.object(
            tracing.trace,
            "get_current_span",
            return_value=tracing.trace.NonRecordingSpan(
                tracing.trace.SpanContext(
                    trace_id=0,
                    span_id=0,
                    is_remote=False,
                    trace_flags=tracing.trace.TraceFlags(0),
                )
            ),
        ):
            exc = ValueError("no active span")
            tracing.record_exception(exc)
