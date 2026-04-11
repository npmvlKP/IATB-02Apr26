"""
Tests for exception hierarchy.
"""

import random

import numpy as np
import pytest
import torch
from iatb.core.exceptions import (
    ClockError,
    ConfigError,
    EventBusError,
    IATBError,
    ValidationError,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestIATBError:
    """Test IATBError base exception."""

    def test_inheritance(self) -> None:
        """Test that IATBError inherits from Exception."""
        error = IATBError("Test error")
        assert isinstance(error, Exception)

    def test_message_stored(self) -> None:
        """Test that message is stored."""
        error = IATBError("Test error message")
        assert error.message == "Test error message"

    def test_string_representation(self) -> None:
        """Test string representation."""
        error = IATBError("Test error message")
        assert str(error) == "Test error message"

    def test_message_only_required(self) -> None:
        """Test that only message is required."""
        error = IATBError("Test")
        assert error.message == "Test"

    def test_with_additional_args(self) -> None:
        """Test exception with additional args."""
        error = IATBError("Test", "arg1", "arg2")
        assert error.message == "Test"
        assert error.args == ("Test", "arg1", "arg2")


class TestValidationError:
    """Test ValidationError."""

    def test_inheritance(self) -> None:
        """Test that ValidationError inherits from IATBError."""
        error = ValidationError("Validation failed")
        assert isinstance(error, IATBError)
        assert isinstance(error, Exception)

    def test_message(self) -> None:
        """Test message storage."""
        error = ValidationError("Invalid input")
        assert error.message == "Invalid input"


class TestConfigError:
    """Test ConfigError."""

    def test_inheritance(self) -> None:
        """Test that ConfigError inherits from IATBError."""
        error = ConfigError("Config failed")
        assert isinstance(error, IATBError)
        assert isinstance(error, Exception)

    def test_message(self) -> None:
        """Test message storage."""
        error = ConfigError("Missing required field")
        assert error.message == "Missing required field"


class TestEventBusError:
    """Test EventBusError."""

    def test_inheritance(self) -> None:
        """Test that EventBusError inherits from IATBError."""
        error = EventBusError("Event bus failed")
        assert isinstance(error, IATBError)
        assert isinstance(error, Exception)

    def test_message(self) -> None:
        """Test message storage."""
        error = EventBusError("Publish failed")
        assert error.message == "Publish failed"


class TestClockError:
    """Test ClockError."""

    def test_inheritance(self) -> None:
        """Test that ClockError inherits from IATBError."""
        error = ClockError("Clock failed")
        assert isinstance(error, IATBError)
        assert isinstance(error, Exception)

    def test_message(self) -> None:
        """Test message storage."""
        error = ClockError("Invalid timezone")
        assert error.message == "Invalid timezone"


class TestExceptionHierarchy:
    """Test exception hierarchy relationships."""

    def test_all_errors_inherit_from_iatb_error(self) -> None:
        """Test that all custom errors inherit from IATBError."""
        errors = [
            ValidationError("test"),
            ConfigError("test"),
            EventBusError("test"),
            ClockError("test"),
        ]
        for error in errors:
            assert isinstance(error, IATBError)

    def test_can_catch_specific_errors(self) -> None:
        """Test catching specific errors."""
        try:
            raise ConfigError("Test")
        except IATBError as e:
            assert isinstance(e, ConfigError)
        except Exception:
            pytest.fail("Should have caught IATBError")

    def test_can_catch_all_with_iatb_error(self) -> None:
        """Test catching all errors with IATBError."""
        errors_to_test = [
            ValidationError("test"),
            ConfigError("test"),
            EventBusError("test"),
            ClockError("test"),
        ]

        for error in errors_to_test:
            caught = False
            try:
                raise error
            except IATBError:
                caught = True
            assert caught, f"Failed to catch {type(error).__name__} as IATBError"
