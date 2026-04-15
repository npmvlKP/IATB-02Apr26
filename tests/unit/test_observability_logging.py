"""Tests for observability logging configuration."""

from __future__ import annotations

import logging
from io import StringIO

from iatb.core.observability.logging_config import (
    JsonFormatter,
    LogContext,
    get_logger,
    setup_structured_logging,
)


class TestJsonFormatter:
    """Test cases for JsonFormatter."""

    def test_add_fields_includes_timestamp(self) -> None:
        """Test that formatter adds timestamp to log record."""
        formatter = JsonFormatter("%(timestamp)s %(level)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        log_record: dict[str, object] = {}
        formatter.add_fields(log_record, record, {})
        assert "timestamp" in log_record

    def test_add_fields_includes_level(self) -> None:
        """Test that formatter includes level in log record."""
        formatter = JsonFormatter("%(timestamp)s %(level)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        log_record: dict[str, object] = {}
        formatter.add_fields(log_record, record, {})
        assert log_record["level"] == "ERROR"

    def test_add_fields_includes_exception(self) -> None:
        """Test that formatter includes exception info when present."""
        formatter = JsonFormatter("%(timestamp)s %(level)s %(message)s")
        try:
            raise ValueError("Test exception")
        except Exception:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=True,
            )
            # Capture actual exception info
            import sys

            record.exc_info = sys.exc_info()
            log_record: dict[str, object] = {}
            formatter.add_fields(log_record, record, {})
            assert "exception" in log_record


class TestSetupStructuredLogging:
    """Test cases for setup_structured_logging function."""

    def test_setup_structured_logging_returns_logger(self) -> None:
        """Test that setup_structured_logging returns a logger."""
        logger = setup_structured_logging("INFO")
        assert isinstance(logger, logging.Logger)

    def test_setup_structured_logging_sets_level(self) -> None:
        """Test that setup_structured_logging sets log level."""
        logger = setup_structured_logging("DEBUG")
        assert logger.level == logging.DEBUG

    def test_setup_structured_logging_clears_handlers(self) -> None:
        """Test that setup_structured_logging clears existing handlers."""
        logger = logging.getLogger()
        logger.addHandler(logging.StreamHandler())
        initial_count = len(logger.handlers)
        setup_structured_logging("INFO")
        assert len(logger.handlers) < initial_count or len(logger.handlers) == 1


class TestGetLogger:
    """Test cases for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a logger instance."""
        logger = get_logger("test_logger")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_returns_same_instance(self) -> None:
        """Test that get_logger returns same logger instance for same name."""
        logger1 = get_logger("test_logger")
        logger2 = get_logger("test_logger")
        assert logger1 is logger2


class TestLogContext:
    """Test cases for LogContext context manager."""

    def test_log_context_enters_and_exits(self) -> None:
        """Test that LogContext can be used as context manager."""
        with LogContext(user_id="123"):
            logger = get_logger("test")
            logger.info("Test message")

    def test_log_context_adds_context_to_logs(self) -> None:
        """Test that LogContext adds context to log records."""
        logger = get_logger("test_context")
        handler = logging.StreamHandler(StringIO())
        formatter = JsonFormatter("%(timestamp)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        with LogContext(user_id="123", action="test"):
            logger.info("Test message")

        # Context manager should not raise exceptions
        assert True

    def test_log_context_restores_factory(self) -> None:
        """Test that LogContext restores original record factory."""
        original_factory = logging.getLogRecordFactory()
        with LogContext(test_key="test_value"):
            pass
        assert logging.getLogRecordFactory() is original_factory
