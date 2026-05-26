"""Comprehensive coverage tests for iatb.execution.order_throttle."""

from datetime import UTC, datetime, timedelta

import pytest
from iatb.core.exceptions import ConfigError
from iatb.execution.order_throttle import OrderThrottle

_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestOrderThrottleInit:
    def test_default_max_ops(self) -> None:
        ot = OrderThrottle()
        assert ot._max_ops == 10

    def test_custom_max_ops(self) -> None:
        ot = OrderThrottle(max_ops=5)
        assert ot._max_ops == 5

    def test_zero_max_ops_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            OrderThrottle(max_ops=0)

    def test_negative_max_ops_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            OrderThrottle(max_ops=-1)


class TestCheckAndRecord:
    def test_allows_within_limit(self) -> None:
        ot = OrderThrottle(max_ops=5)
        for _ in range(5):
            assert ot.check_and_record(_NOW) is True

    def test_rejects_over_limit(self) -> None:
        ot = OrderThrottle(max_ops=3)
        for _ in range(3):
            ot.check_and_record(_NOW)
        assert ot.check_and_record(_NOW) is False

    def test_new_second_resets_counter(self) -> None:
        ot = OrderThrottle(max_ops=3)
        for _ in range(3):
            ot.check_and_record(_NOW)
        next_second = _NOW + timedelta(seconds=1)
        assert ot.check_and_record(next_second) is True

    def test_naive_datetime_raises(self) -> None:
        ot = OrderThrottle()
        with pytest.raises(ConfigError, match="UTC"):
            ot.check_and_record(datetime(2026, 5, 25, 10, 0))

    def test_exact_limit_allowed(self) -> None:
        ot = OrderThrottle(max_ops=1)
        assert ot.check_and_record(_NOW) is True

    def test_one_over_limit_rejected(self) -> None:
        ot = OrderThrottle(max_ops=1)
        ot.check_and_record(_NOW)
        assert ot.check_and_record(_NOW) is False


class TestCurrentCount:
    def test_initial_zero(self) -> None:
        ot = OrderThrottle()
        assert ot.current_count == 0

    def test_increments_after_check(self) -> None:
        ot = OrderThrottle(max_ops=5)
        ot.check_and_record(_NOW)
        assert ot.current_count == 1

    def test_resets_on_new_second(self) -> None:
        ot = OrderThrottle(max_ops=5)
        ot.check_and_record(_NOW)
        next_second = _NOW + timedelta(seconds=1)
        ot.check_and_record(next_second)
        assert ot.current_count == 1
