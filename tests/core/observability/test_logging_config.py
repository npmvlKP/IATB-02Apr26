"""Tests for observability logging configuration."""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_imports():
    mocks = {
        "pythonjsonlogger": MagicMock(),
        "pythonjsonlogger.jsonlogger": MagicMock(),
        "pythonjsonlogger.jsonlogger.JsonFormatter": MagicMock,
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


class TestGetLogger:
    def test_returns_logger(self) -> None:
        import logging

        from iatb.core.observability.logging_config import get_logger

        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)


class TestLogContext:
    def test_context_adds_attributes(self) -> None:
        import logging

        from iatb.core.observability.logging_config import LogContext

        with LogContext(user_id="123", action="trade"):
            factory = logging.getLogRecordFactory()
            record = factory("test", logging.INFO, __file__, 1, "test", (), None)
            assert record.user_id == "123"
            assert record.action == "trade"


class TestSetupStructuredLogging:
    def test_returns_root_logger(self) -> None:
        import logging

        from iatb.core.observability.logging_config import setup_structured_logging

        logger = setup_structured_logging("DEBUG")
        assert isinstance(logger, logging.Logger)
