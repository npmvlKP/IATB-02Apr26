"""
Exception hierarchy for IATB.

Provides typed exceptions for different error scenarios.
"""


class IATBError(Exception):
    """Base exception for all IATB errors."""

    def __init__(self, message: str, *args: object) -> None:
        """Initialize the base exception."""
        super().__init__(message, *args)
        self.message = message

    def __str__(self) -> str:
        """Return string representation."""
        return self.message


class ValidationError(IATBError):
    """Exception raised for validation errors."""


class ConfigError(IATBError):
    """Exception raised for configuration errors."""


class EventBusError(IATBError):
    """Exception raised for event bus errors."""


class ClockError(IATBError):
    """Exception raised for clock/time-related errors."""


class EngineError(IATBError):
    """Exception raised for engine/lifecycle errors."""


class InstrumentResolutionError(IATBError):
    """Exception raised when instrument resolution fails."""


class EngineNotRunningError(IATBError):
    """Exception raised when engine/runtime is not started."""


class ExecutionError(IATBError):
    """Exception raised for order execution errors."""


class ExchangeHaltError(IATBError):
    """Exception raised when exchange is halted."""
