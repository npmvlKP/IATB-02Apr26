"""Structured logging configuration with JSON formatting."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from pythonjsonlogger import jsonlogger

from iatb.core.config import get_config


class JsonFormatter(jsonlogger.JsonFormatter):  # type: ignore[misc,name-defined]
    """Custom JSON formatter with UTC timestamps and additional context."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to log record.

        Args:
            log_record: The log record to modify.
            record: The original log record.
            message_dict: Additional message context.
        """
        super().add_fields(log_record, record, message_dict)

        # Ensure UTC timestamp
        if "timestamp" not in log_record:
            log_record["timestamp"] = datetime.now(UTC).isoformat()

        # Add standard fields
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["thread"] = record.thread
        log_record["process"] = record.process

        # Add trace and span IDs from OpenTelemetry context
        span = trace.get_current_span()
        if span.is_recording():
            ctx = span.get_span_context()
            log_record["trace_id"] = format(ctx.trace_id, "032x")
            log_record["span_id"] = format(ctx.span_id, "016x")

        # Add service.name resource attribute
        provider = trace.get_tracer_provider()
        resource = getattr(provider, "resource", None)
        if resource and "service.name" in resource.attributes:
            log_record["service.name"] = resource.attributes["service.name"]
        else:
            try:
                config = get_config()
                log_record["service.name"] = getattr(config, "service", {}).get("name", "iatb")
            except Exception:
                log_record["service.name"] = "iatb"

        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)


def _create_console_handler() -> logging.StreamHandler[Any]:
    """Create console handler with JSON formatter.

    Returns:
        Configured console handler.
    """
    console_handler = logging.StreamHandler[Any](sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    formatter = JsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s",
        timestamp=True,
    )
    console_handler.setFormatter(formatter)

    return console_handler


def _create_file_handler() -> logging.Handler | None:
    """Create file handler with JSON formatter and rotation.

    Returns:
        Configured file handler or None if file logging is disabled.
    """
    try:
        config = get_config()
        logging_config = getattr(config, "logging", None)
        if not logging_config:
            return None

        file_config = getattr(logging_config, "file", None)
        if not file_config or not getattr(file_config, "enabled", False):
            return None

        # Get file configuration with defaults
        log_path = getattr(file_config, "path", "logs/iatb.json")
        max_bytes = getattr(file_config, "max_bytes", 10485760)  # 10MB
        backup_count = getattr(file_config, "backup_count", 5)

        # Ensure log directory exists
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)

        # Use JSON formatter
        formatter = JsonFormatter(
            "%(timestamp)s %(level)s %(logger)s %(message)s",
            timestamp=True,
        )
        file_handler.setFormatter(formatter)

        return file_handler
    except Exception as exc:
        # If config fails to load, log warning and return None
        logging.getLogger(__name__).warning(
            "Failed to load file logging config: %s",
            exc,
        )
        return None


def _configure_logging_format(
    console_handler: logging.StreamHandler[Any],
) -> None:
    """Configure logging format based on config file.

    Args:
        console_handler: Console handler to configure.
    """
    try:
        config = get_config()
        logging_config = getattr(config, "logging", None)

        if logging_config and hasattr(logging_config, "format"):
            if logging_config.format.lower() == "json":
                # JSON format is already set
                pass
            else:
                # Use standard text format
                console_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
    except Exception as exc:
        # If config fails to load, continue with JSON format
        logging.getLogger(__name__).warning(
            "Failed to load logging config: %s",
            exc,
        )


def _configure_module_levels() -> None:
    """Configure per-module log levels from config file."""
    try:
        config = get_config()
        logging_config = getattr(config, "logging", None)
        if not logging_config:
            return

        modules_config = getattr(logging_config, "modules", None)
        if not modules_config:
            return

        # Set level for each module
        for module_name, level_str in modules_config.items():
            level = getattr(logging, level_str.upper(), logging.INFO)
            logger = logging.getLogger(module_name)
            logger.setLevel(level)
    except Exception as exc:
        # If config fails to load, continue without module-specific levels
        logging.getLogger(__name__).warning(
            "Failed to load module logging config: %s",
            exc,
        )


def setup_structured_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured JSON logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Configured root logger.
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler with JSON formatter
    console_handler = _create_console_handler()

    # Create file handler if enabled
    file_handler = _create_file_handler()

    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    if file_handler is not None:
        root_logger.addHandler(file_handler)

    # Configure logging from config file if exists
    _configure_logging_format(console_handler)

    # Configure per-module log levels
    _configure_module_levels()

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with structured logging configured.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding structured context to logs.

    Example:
        >>> with LogContext(user_id="123", action="trade"):
        ...     _LOGGER.info("Executing trade")
    """

    def __init__(self, **context: Any) -> None:
        """Initialize log context.

        Args:
            **context: Key-value pairs to add to log context.
        """
        self.context: dict[str, Any] = context
        self.logger = logging.getLogger()
        self.old_factory: Any = None

    def __enter__(self) -> LogContext:
        """Enter context and modify log record factory."""
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(
            name: str,
            level: int,
            fn: str,
            lno: int,
            msg: str,
            args: tuple[Any, ...],
            exc_info: Any,
            func: str | None = None,
            sinfo: str | None = None,
        ) -> logging.LogRecord:
            """Custom record factory with context."""
            record = self.old_factory(name, level, fn, lno, msg, args, exc_info, func, sinfo)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record  # type: ignore[no-any-return]

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context and restore original record factory."""
        logging.setLogRecordFactory(self.old_factory)


# Initialize structured logging on module import
setup_structured_logging()
