"""
Optimized pytest configuration with performance improvements and enhanced coverage.

This file provides:
1. Faster property-based testing with reduced examples
2. Efficient mock fixtures
3. Enhanced coverage for edge cases, errors, types, precision, timezone
4. Deterministic test behavior
"""

from __future__ import annotations

import random
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from hypothesis import settings

if TYPE_CHECKING:
    from collections.abc import Generator

# Fixed seed value for reproducibility across all tests
DETERMINISTIC_SEED: int = 42

# Optimized hypothesis settings for faster execution
HYPOTHESIS_FAST_SETTINGS = settings(
    max_examples=10,  # Reduced from 25-100 for faster execution
    deadline=None,  # No time deadline
    derandomize=True,  # Deterministic execution
)

HYPOTHESIS_MEDIUM_SETTINGS = settings(
    max_examples=20,  # Medium coverage
    deadline=None,
    derandomize=True,
)

HYPOTHESIS_SLOW_SETTINGS = settings(
    max_examples=30,  # Higher coverage for critical paths
    deadline=None,
    derandomize=True,
)


@pytest.fixture(autouse=True)
def set_deterministic_seeds() -> Generator[None, None, None]:
    """
    Fixture that sets deterministic seeds for all random number generators.

    This fixture runs automatically for all tests (autouse=True) to ensure
    reproducible test results across multiple runs.

    Sets seeds for:
    - Python's random module
    - NumPy's random module (if available)
    - PyTorch's random module (if available)
    """
    random.seed(DETERMINISTIC_SEED)

    try:
        np.random.seed(DETERMINISTIC_SEED)
    except ImportError:
        pass

    try:
        torch.manual_seed(DETERMINISTIC_SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(DETERMINISTIC_SEED)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass

    yield


@pytest.fixture
def mock_datetime_utc() -> MagicMock:
    """
    Mock datetime module that always returns UTC timestamps.

    Useful for testing timezone handling without relying on system time.
    """
    fixed_time = datetime(2026, 4, 8, 12, 0, 0, tzinfo=UTC)

    def _datetime_with_utc(*args, **kwargs) -> datetime:
        """Create datetime with UTC timezone if not specified."""
        if "tzinfo" not in kwargs:
            kwargs["tzinfo"] = UTC
        return datetime(  # noqa: DTZ001
            *args, **kwargs
        )

    with patch("iatb.core.clock.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_time
        mock_dt.side_effect = _datetime_with_utc
        yield mock_dt


@pytest.fixture
def mock_decimal_precision() -> MagicMock:
    """
    Mock Decimal operations to ensure consistent precision handling.

    Useful for testing financial calculations with exact decimal precision.
    """
    with patch("decimal.getcontext") as mock_context:
        mock_context.return_value.prec = 28
        yield mock_context


@pytest.fixture
def edge_case_prices() -> list[Decimal]:
    """
    Edge case prices for comprehensive testing.

    Returns:
        List of edge case prices including: zero, very small, very large,
        negative (invalid), and typical values.
    """
    return [
        Decimal("0"),  # Zero price
        Decimal("0.01"),  # Minimum tick size
        Decimal("0.05"),  # Small value
        Decimal("1"),  # One unit
        Decimal("100"),  # Typical value
        Decimal("1000.50"),  # With decimal
        Decimal("100000"),  # Large value
        Decimal("9999999.99"),  # Very large with decimal
    ]


@pytest.fixture
def edge_case_quantities() -> list[Decimal]:
    """
    Edge case quantities for comprehensive testing.

    Returns:
        List of edge case quantities including: zero, lot sizes, and large values.
    """
    return [
        Decimal("0"),  # Zero quantity
        Decimal("1"),  # One unit
        Decimal("75"),  # NSE lot size
        Decimal("100"),  # Typical lot size
        Decimal("1800"),  # MIS freeze limit
        Decimal("10000"),  # Large quantity
        Decimal("100000"),  # Very large quantity
    ]


@pytest.fixture
def timezone_aware_timestamps() -> list[datetime]:
    """
    Timezone-aware timestamps for testing timezone handling.

    Returns:
        List of UTC timestamps covering different scenarios:
        - Market open/close
        - Day rollover
        - DST boundaries
        - Microsecond precision
    """
    return [
        datetime(2026, 4, 8, 9, 15, 0, tzinfo=UTC),  # NSE open
        datetime(2026, 4, 8, 15, 30, 0, tzinfo=UTC),  # NSE close
        datetime(2026, 4, 8, 23, 59, 59, 999999, tzinfo=UTC),  # Day end
        datetime(2026, 4, 9, 0, 0, 0, tzinfo=UTC),  # Next day
        datetime(2026, 4, 8, 12, 30, 45, 123456, tzinfo=UTC),  # Microseconds
    ]


@pytest.fixture
def error_scenario_data() -> dict[str, list]:
    """
    Error scenario data for testing error paths.

    Returns:
        Dictionary with lists of invalid data for different scenarios.
    """
    return {
        "negative_prices": [Decimal("-1"), Decimal("-100.50"), Decimal("-0.01")],
        "negative_quantities": [Decimal("-1"), Decimal("-100"), Decimal("-0.01")],
        "zero_lot_sizes": [Decimal("0"), Decimal("0.00")],
        "empty_strings": ["", "   ", "\t\n"],
        "invalid_symbols": ["", "SYMBOL", "123", "SYMBOL123!", "A" * 100],
        "future_timestamps": [
            datetime(2100, 1, 1, tzinfo=UTC),
            datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        ],
        "past_timestamps": [
            datetime(2000, 1, 1, tzinfo=UTC),
            datetime(2020, 1, 1, tzinfo=UTC),
        ],
    }


@pytest.fixture
def type_validation_data() -> dict[str, list]:
    """
    Type validation data for testing type handling.

    Returns:
        Dictionary with invalid types for different fields.
    """
    return {
        "non_decimal_numbers": [1, 1.5, 100, 0.0],
        "non_int_lot_sizes": [1.5, "75", Decimal("75.5"), None],
        "non_string_symbols": [123, None, {}, []],
        "non_datetime_timestamps": ["2026-04-08", 1712563200, None],
        "non_bool_flags": ["true", 1, 0, None, []],
    }


@pytest.fixture
def precision_test_data() -> dict[str, list[tuple[Decimal, int]]]:
    """
    Precision test data for testing decimal precision handling.

    Returns:
        Dictionary with values and expected precision levels.
    """
    return {
        "price_precision": [
            (Decimal("100.00"), 2),
            (Decimal("100.5"), 1),
            (Decimal("100.50"), 2),
            (Decimal("100.05"), 2),
            (Decimal("100.005"), 3),
            (Decimal("100.000"), 3),
        ],
        "quantity_precision": [
            (Decimal("75"), 0),
            (Decimal("75.0"), 1),
            (Decimal("75.00"), 2),
            (Decimal("100"), 0),
            (Decimal("100.0"), 1),
        ],
    }


@pytest.fixture
def fast_property_settings() -> settings:
    """Fast hypothesis settings for quick feedback during development."""
    return HYPOTHESIS_FAST_SETTINGS


@pytest.fixture
def medium_property_settings() -> settings:
    """Medium hypothesis settings for balanced speed and coverage."""
    return HYPOTHESIS_MEDIUM_SETTINGS


@pytest.fixture
def slow_property_settings() -> settings:
    """Slow hypothesis settings for maximum coverage in CI."""
    return HYPOTHESIS_SLOW_SETTINGS


# Pytest hooks for test optimization
def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to optimize execution order.

    - Mark slow tests
    - Group property-based tests
    - Prioritize fast unit tests
    """
    for item in items:
        # Mark property-based tests as slow by default
        if "hypothesis" in getattr(item, "fixturenames", []):
            item.add_marker(pytest.mark.slow)

        # Mark tests that use large example counts
        if hasattr(item, "obj") and hasattr(item.obj, "hypothesis"):
            for decorator in getattr(item.obj, "hypothesis", []):
                if hasattr(decorator, "settings") and decorator.settings.max_examples > 20:
                    item.add_marker(pytest.mark.slow)


def pytest_configure(config):
    """
    Configure pytest with custom markers and settings.
    """
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "property: marks property-based tests")
    config.addinivalue_line("markers", "edge_case: marks edge case tests")
    config.addinivalue_line("markers", "error_path: marks error path tests")
    config.addinivalue_line("markers", "type_validation: marks type validation tests")
    config.addinivalue_line("markers", "precision: marks precision handling tests")
    config.addinivalue_line("markers", "timezone: marks timezone handling tests")
