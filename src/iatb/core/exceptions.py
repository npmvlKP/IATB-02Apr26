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

    pass


class ConfigError(IATBError):
    """Exception raised for configuration errors."""

    pass


class EventBusError(IATBError):
    """Exception raised for event bus errors."""

    pass


class ClockError(IATBError):
    """Exception raised for clock/time-related errors."""

    pass


class EngineError(IATBError):
    """Exception raised for engine/lifecycle errors."""

    pass


class InstrumentResolutionError(IATBError):
    """Exception raised when instrument resolution fails."""

    pass
