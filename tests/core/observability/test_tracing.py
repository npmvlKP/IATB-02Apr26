"""Tests for observability tracing configuration."""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_opentelemetry():
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
    yield
    for mod, orig in original.items():
        if orig is None:
            sys.modules.pop(mod, None)
        else:
            sys.modules[mod] = orig


class TestGetTracer:
    def test_returns_tracer(self) -> _mock_opentelemetry:
        from iatb.core.observability.tracing import get_tracer

        tracer = get_tracer("test")
        assert tracer is not None


class TestAddSpanAttributes:
    def test_no_active_span(self) -> _mock_opentelemetry:
        from iatb.core.observability.tracing import add_span_attributes

        add_span_attributes(key="value")


class TestRecordException:
    def test_no_active_span(self) -> _mock_opentelemetry:
        from iatb.core.observability.tracing import record_exception

        record_exception(ValueError("test"))
