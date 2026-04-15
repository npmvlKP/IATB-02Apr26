"""Tests for observability logging configuration."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

from iatb.core.observability.logging_config import (
    JsonFormatter,
    LogContext,
    get_logger,
    setup_structured_logging,
)


class TestJsonFormatter:
    """Tests for JsonFormatter class."""

    def test_add_fields_includes_timestamp(self) -> None:
        """Test that formatter includes UTC timestamp."""
        formatter = JsonFormatter("%(message)s")
        log_record = {}
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        message_dict = {}

        formatter.add_fields(log_record, record, message_dict)

        # The formatter adds timestamp to the log_record dict
        assert "timestamp" in log_record

    def test_add_fields_includes_level(self) -> None:
        """Test that formatter includes log level."""
        formatter = JsonFormatter("%(level)s %(message)s")
        log_record = {}
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        message_dict = {}

        formatter.add_fields(log_record, record, message_dict)

        assert log_record["level"] == "ERROR"

    def test_add_fields_includes_logger_name(self) -> None:
        """Test that formatter includes logger name."""
        formatter = JsonFormatter("%(logger)s %(message)s")
        log_record = {}
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        message_dict = {}

        formatter.add_fields(log_record, record, message_dict)

        assert log_record["logger"] == "test.logger"

    def test_add_fields_includes_thread_and_process(self) -> None:
        """Test that formatter includes thread and process IDs."""
        formatter = JsonFormatter("%(thread)s %(process)s %(message)s")
        log_record = {}
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        message_dict = {}

        formatter.add_fields(log_record, record, message_dict)

        assert "thread" in log_record
        assert "process" in log_record
        assert isinstance(log_record["thread"], int)
        assert isinstance(log_record["process"], int)

    def test_add_fields_includes_exception(self) -> None:
        """Test that formatter includes exception info when present."""
        formatter = JsonFormatter("%(exception)s %(message)s")
        log_record = {}

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="test message",
                args=(),
                exc_info=exc_info,
            )

        message_dict = {}

        formatter.add_fields(log_record, record, message_dict)

        assert "exception" in log_record
        assert "ValueError" in log_record["exception"]


class TestSetupStructuredLogging:
    """Tests for setup_structured_logging function."""

    def test_setup_returns_logger(self) -> None:
        """Test that setup_structured_logging returns a logger."""
        logger = setup_structured_logging("INFO")
        assert isinstance(logger, logging.Logger)

    def test_setup_clears_existing_handlers(self) -> None:
        """Test that setup_structured_logging clears existing handlers."""
        root_logger = logging.getLogger()
        # Add a dummy handler
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)

        setup_structured_logging("INFO")

        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)

    def test_setup_sets_log_level(self) -> None:
        """Test that setup_structured_logging sets correct log level."""
        root_logger = setup_structured_logging("DEBUG")
        assert root_logger.level == logging.DEBUG

        root_logger = setup_structured_logging("ERROR")
        assert root_logger.level == logging.ERROR

    def test_setup_with_invalid_level_defaults_to_info(self) -> None:
        """Test that invalid log level defaults to INFO."""
        root_logger = setup_structured_logging("INVALID")
        assert root_logger.level == logging.INFO

    def test_setup_uses_json_formatter_by_default(self) -> None:
        """Test that JSON formatter is used by default."""
        root_logger = setup_structured_logging("INFO")
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    @patch("iatb.core.observability.logging_config.get_config")
    def test_setup_uses_text_format_when_configured(self, mock_get_config: MagicMock) -> None:
        """Test that text format is used when configured."""
        mock_config = MagicMock()
        mock_config.logging.format = "text"
        mock_get_config.return_value = mock_config

        root_logger = setup_structured_logging("INFO")
        handler = root_logger.handlers[0]
        assert not isinstance(handler.formatter, JsonFormatter)
        assert isinstance(handler.formatter, logging.Formatter)

    @patch("iatb.core.observability.logging_config.get_config")
    def test_setup_handles_config_failure_gracefully(self, mock_get_config: MagicMock) -> None:
        """Test that config failure doesn't break setup."""
        mock_get_config.side_effect = Exception("Config error")

        # Should not raise exception
        root_logger = setup_structured_logging("INFO")
        assert isinstance(root_logger, logging.Logger)


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a logger instance."""
        logger = get_logger("test.logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.logger"

    def test_get_logger_with_module_name(self) -> None:
        """Test that get_logger works with __name__."""
        logger = get_logger(__name__)
        assert isinstance(logger, logging.Logger)
        assert logger.name == __name__


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_log_context_adds_attributes_to_records(self) -> None:
        """Test that LogContext adds attributes to log records."""
        logger = logging.getLogger("test.context")

        with LogContext(user_id="123", action="test"):
            record = logger.makeRecord(
                name="test.context",
                level=logging.INFO,
                fn="test.py",
                lno=1,
                msg="test message",
                args=(),
                exc_info=None,
            )

            assert hasattr(record, "user_id")
            assert record.user_id == "123"
            assert hasattr(record, "action")
            assert record.action == "test"

    def test_log_context_restores_original_factory(self) -> None:
        """Test that LogContext restores original record factory."""
        original_factory = logging.getLogRecordFactory()

        with LogContext(test_key="test_value"):
            pass

        # After context, factory should be restored
        assert logging.getLogRecordFactory() is original_factory

    def test_log_context_with_nested_contexts(self) -> None:
        """Test that nested LogContext instances work correctly."""
        logger = logging.getLogger("test.nested")

        with LogContext(level1="value1"):
            with LogContext(level2="value2"):
                record = logger.makeRecord(
                    name="test.nested",
                    level=logging.INFO,
                    fn="test.py",
                    lno=1,
                    msg="test message",
                    args=(),
                    exc_info=None,
                )

                # Inner context should override
                assert hasattr(record, "level2")
                assert record.level2 == "value2"

    def test_log_context_with_exception(self) -> None:
        """Test that LogContext restores factory even on exception."""
        original_factory = logging.getLogRecordFactory()

        try:
            with LogContext(test_key="test_value"):
                raise ValueError("Test exception")
        except ValueError:
            pass

        assert logging.getLogRecordFactory() is original_factory

    def test_log_context_with_empty_context(self) -> None:
        """Test that LogContext works with empty context."""
        logger = logging.getLogger("test.empty")

        with LogContext():
            record = logger.makeRecord(
                name="test.empty",
                level=logging.INFO,
                fn="test.py",
                lno=1,
                msg="test message",
                args=(),
                exc_info=None,
            )

            # Record should still be created
            assert record is not None


class TestIntegration:
    """Integration tests for logging configuration."""

    def test_json_logging_setup_does_not_crash(self) -> None:
        """Test that JSON logging setup completes without errors."""
        logger = setup_structured_logging("INFO")
        assert isinstance(logger, logging.Logger)

        # Test logging at different levels
        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")

        # Should not raise any exceptions
        assert True

    def test_logging_with_exception_info(self) -> None:
        """Test logging with exception information."""
        setup_structured_logging("INFO")
        logger = get_logger("test.exception")

        try:
            raise ValueError("Test exception")
        except ValueError:
            # Should not raise exception
            logger.exception("An error occurred")
            assert True

    def test_logging_with_context(self) -> None:
        """Test logging with LogContext."""
        setup_structured_logging("INFO")
        logger = get_logger("test.with_context")

        with LogContext(user_id="123", action="login"):
            logger.info("User logged in")

        # Should not raise any exceptions
        assert True
