"""Tests for observability logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

# Module-level fixture to mock pythonjsonlogger before importing logging_config


class TestGetLogger:
    def test_returns_logger(self) -> None:
        from iatb.core.observability.logging_config import get_logger

        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test"


class TestLogContext:
    def test_context_adds_attributes(self) -> None:
        from iatb.core.observability.logging_config import LogContext

        with LogContext(user_id="123", action="trade"):
            factory = logging.getLogRecordFactory()
            record = factory("test", logging.INFO, __file__, 1, "test", (), None)
            assert record.user_id == "123"
            assert record.action == "trade"


class TestCreateFileHandler:
    @patch("iatb.core.observability.logging_config.get_config")
    def test_returns_none_when_file_logging_disabled(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _create_file_handler

        mock_config = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.logging.file = MagicMock()
        mock_config.logging.file.enabled = False
        mock_get_config.return_value = mock_config

        result = _create_file_handler()
        assert result is None

    @patch("iatb.core.observability.logging_config.get_config")
    def test_returns_none_when_no_logging_config(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _create_file_handler

        mock_config = MagicMock()
        mock_config.logging = None
        mock_get_config.return_value = mock_config

        result = _create_file_handler()
        assert result is None

    @patch("iatb.core.observability.logging_config.get_config")
    def test_returns_none_when_no_file_config(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _create_file_handler

        mock_config = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.logging.file = None
        mock_get_config.return_value = mock_config

        result = _create_file_handler()
        assert result is None

    @patch("iatb.core.observability.logging_config.get_config")
    @patch("logging.handlers.RotatingFileHandler")
    def test_creates_rotating_file_handler(
        self, mock_handler_class: MagicMock, mock_get_config: MagicMock, tmp_path: Path
    ) -> None:
        from iatb.core.observability.logging_config import _create_file_handler

        log_file = tmp_path / "test.json"
        mock_config = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.logging.file = MagicMock()
        mock_config.logging.file.enabled = True
        mock_config.logging.file.path = str(log_file)
        mock_config.logging.file.max_bytes = 10485760
        mock_config.logging.file.backup_count = 5
        mock_get_config.return_value = mock_config

        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        result = _create_file_handler()
        assert result is not None
        mock_handler_class.assert_called_once_with(
            str(log_file),
            maxBytes=10485760,
            backupCount=5,
            encoding="utf-8",
        )


class TestConfigureModuleLevels:
    @patch("iatb.core.observability.logging_config.get_config")
    def test_sets_module_levels(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _configure_module_levels

        mock_config = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.logging.modules = {
            "iatb.data": "INFO",
            "iatb.execution": "DEBUG",
            "iatb.risk": "WARNING",
        }
        mock_get_config.return_value = mock_config

        # Clear any pre-existing loggers for a clean test
        for name in ["iatb.data", "iatb.execution", "iatb.risk"]:
            logger = logging.getLogger(name)
            logger.setLevel(logging.NOTSET)

        _configure_module_levels()

        assert logging.getLogger("iatb.data").level == logging.INFO
        assert logging.getLogger("iatb.execution").level == logging.DEBUG
        assert logging.getLogger("iatb.risk").level == logging.WARNING

    @patch("iatb.core.observability.logging_config.get_config")
    def test_skips_when_no_modules_config(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _configure_module_levels

        mock_config = MagicMock()
        mock_config.logging = MagicMock()
        mock_config.logging.modules = None
        mock_get_config.return_value = mock_config

        _configure_module_levels()
        # Should not raise or change anything
        assert True

    @patch("iatb.core.observability.logging_config.get_config")
    def test_skips_when_no_logging_config(self, mock_get_config: MagicMock) -> None:
        from iatb.core.observability.logging_config import _configure_module_levels

        mock_config = MagicMock()
        mock_config.logging = None
        mock_get_config.return_value = mock_config

        _configure_module_levels()
        assert True


class TestSetupStructuredLogging:
    def test_returns_root_logger(self) -> None:
        from iatb.core.observability.logging_config import setup_structured_logging

        # Patch the helper functions to avoid side effects
        with (
            patch("iatb.core.observability.logging_config._create_console_handler") as mock_console,
            patch("iatb.core.observability.logging_config._create_file_handler") as mock_file,
            patch("iatb.core.observability.logging_config._configure_logging_format") as mock_fmt,
            patch("iatb.core.observability.logging_config._configure_module_levels") as mock_mod,
        ):
            mock_console.return_value = MagicMock()
            mock_file.return_value = None
            mock_fmt.return_value = None
            mock_mod.return_value = None

            logger = setup_structured_logging("DEBUG")
            assert isinstance(logger, logging.Logger)

    def test_adds_file_handler_when_enabled(self) -> None:
        from iatb.core.observability.logging_config import setup_structured_logging

        mock_file_handler = MagicMock()
        with (
            patch("iatb.core.observability.logging_config._create_console_handler") as mock_console,
            patch("iatb.core.observability.logging_config._create_file_handler") as mock_file,
            patch("iatb.core.observability.logging_config._configure_logging_format") as mock_fmt,
            patch("iatb.core.observability.logging_config._configure_module_levels") as mock_mod,
        ):
            mock_console.return_value = MagicMock()
            mock_file.return_value = mock_file_handler
            mock_fmt.return_value = None
            mock_mod.return_value = None

            root_logger = logging.getLogger()
            original_handlers = root_logger.handlers[:]
            root_logger.handlers.clear()

            setup_structured_logging("INFO")

            # Should have added both console and file handlers
            handlers = root_logger.handlers
            assert len(handlers) == 2
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
