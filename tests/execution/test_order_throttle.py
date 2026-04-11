"""Tests for order_throttle.py module."""

import random
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.execution.order_throttle import OrderThrottle

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_order_throttle_initialization_with_default() -> None:
    """Test OrderThrottle initializes with default max_ops."""
    throttle = OrderThrottle()
    assert throttle.current_count == 0


def test_order_throttle_initialization_with_custom_max() -> None:
    """Test OrderThrottle initializes with custom max_ops."""
    throttle = OrderThrottle(max_ops=5)
    assert throttle.current_count == 0


def test_order_throttle_rejects_non_positive_max_ops() -> None:
    """Test OrderThrottle raises ConfigError for non-positive max_ops."""
    with pytest.raises(ConfigError, match="max_ops must be positive"):
        OrderThrottle(max_ops=0)
    with pytest.raises(ConfigError, match="max_ops must be positive"):
        OrderThrottle(max_ops=-1)


def test_order_throttle_allows_orders_within_limit() -> None:
    """Test OrderThrottle allows orders within OPS limit."""
    throttle = OrderThrottle(max_ops=3)
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    assert throttle.check_and_record(now) is True
    assert throttle.current_count == 1
    assert throttle.check_and_record(now) is True
    assert throttle.current_count == 2
    assert throttle.check_and_record(now) is True
    assert throttle.current_count == 3


def test_order_throttle_rejects_orders_exceeding_limit() -> None:
    """Test OrderThrottle rejects orders exceeding OPS limit."""
    throttle = OrderThrottle(max_ops=2)
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    assert throttle.check_and_record(now) is True
    assert throttle.check_and_record(now) is True
    assert throttle.check_and_record(now) is False
    assert throttle.current_count == 3


def test_order_throttle_resets_on_new_second() -> None:
    """Test OrderThrottle resets count when second changes."""
    throttle = OrderThrottle(max_ops=2)
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    assert throttle.check_and_record(now) is True
    assert throttle.check_and_record(now) is True
    assert throttle.check_and_record(now) is False

    # Move to next second
    next_second = now + timedelta(seconds=1)
    assert throttle.check_and_record(next_second) is True
    assert throttle.current_count == 1


def test_order_throttle_requires_utc_time() -> None:
    """Test OrderThrottle raises ConfigError for non-UTC datetime."""
    throttle = OrderThrottle()
    # Intentionally create naive datetime for error testing
    now_naive = datetime(2026, 4, 7, 8, 0, 0)  # noqa: DTZ001

    with pytest.raises(ConfigError, match="now_utc must be UTC"):
        throttle.check_and_record(now_naive)


def test_order_throttle_handles_same_timestamp() -> None:
    """Test OrderThrottle correctly counts orders with same timestamp."""
    throttle = OrderThrottle(max_ops=1)
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    assert throttle.check_and_record(now) is True
    assert throttle.check_and_record(now) is False
    assert throttle.current_count == 2


def test_order_throttle_across_multiple_seconds() -> None:
    """Test OrderThrottle works correctly across multiple seconds."""
    throttle = OrderThrottle(max_ops=1)
    base_time = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    for i in range(5):
        current_time = base_time + timedelta(seconds=i)
        assert throttle.check_and_record(current_time) is True
        assert throttle.check_and_record(current_time) is False
        assert throttle.current_count == 2


def test_order_throttle_logs_warning_on_exceed(caplog: pytest.LogCaptureFixture) -> None:
    """Test OrderThrottle logs warning when OPS exceeded (lines 37-42)."""
    throttle = OrderThrottle(max_ops=2)
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)

    with caplog.at_level("WARNING"):
        throttle.check_and_record(now)  # 1st - allowed
        throttle.check_and_record(now)  # 2nd - allowed
        result = throttle.check_and_record(now)  # 3rd - rejected

    assert result is False
    assert len(caplog.records) == 1
    assert "OPS throttle" in caplog.records[0].message
    assert "3 orders in second" in caplog.records[0].message
    assert "max 2" in caplog.records[0].message
