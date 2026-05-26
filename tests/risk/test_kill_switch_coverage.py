"""Comprehensive coverage tests for iatb.risk.kill_switch."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult
from iatb.risk.kill_switch import KillSwitch, KillSwitchState, _validate_utc


def _make_executor() -> MagicMock:
    executor = MagicMock()
    executor.cancel_all.return_value = 3
    executor.execute_order.return_value = ExecutionResult(
        "DUMMY", OrderStatus.FILLED, Decimal("10"), Decimal("100")
    )
    executor.close_order.return_value = False
    return executor


_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestKillSwitchState:
    def test_fields(self) -> None:
        state = KillSwitchState(engaged=True, reason="test", triggered_utc=_NOW)
        assert state.engaged is True
        assert state.reason == "test"
        assert state.triggered_utc == _NOW

    def test_frozen(self) -> None:
        state = KillSwitchState(engaged=False, reason="", triggered_utc=None)
        with pytest.raises(AttributeError):
            state.engaged = True


class TestKillSwitchInit:
    def test_default_init(self) -> None:
        ks = KillSwitch(_make_executor())
        assert not ks.is_engaged
        assert ks.check_order_allowed()

    def test_custom_callback(self) -> None:
        callback = MagicMock()
        ks = KillSwitch(_make_executor(), on_engage=callback)
        assert ks._on_engage is callback


class TestKillSwitchEngage:
    def test_engage_sets_engaged(self) -> None:
        ks = KillSwitch(_make_executor())
        state = ks.engage("daily loss breach", _NOW)
        assert state.engaged is True
        assert ks.is_engaged is True

    def test_engage_cancels_all(self) -> None:
        executor = _make_executor()
        ks = KillSwitch(executor)
        ks.engage("test reason", _NOW)
        executor.cancel_all.assert_called_once()

    def test_engage_calls_callback(self) -> None:
        callback = MagicMock()
        ks = KillSwitch(_make_executor(), on_engage=callback)
        ks.engage("test reason", _NOW)
        callback.assert_called_once_with("test reason", _NOW)

    def test_engage_returns_state(self) -> None:
        ks = KillSwitch(_make_executor())
        state = ks.engage("test reason", _NOW)
        assert isinstance(state, KillSwitchState)
        assert state.reason == "test reason"
        assert state.triggered_utc == _NOW

    def test_engage_idempotent(self) -> None:
        executor = _make_executor()
        ks = KillSwitch(executor)
        ks.engage("first", _NOW)
        executor.cancel_all.reset_mock()
        ks.engage("second", _NOW)
        executor.cancel_all.assert_not_called()

    def test_engage_blocks_orders(self) -> None:
        ks = KillSwitch(_make_executor())
        ks.engage("test", _NOW)
        assert not ks.check_order_allowed()

    def test_empty_reason_raises(self) -> None:
        ks = KillSwitch(_make_executor())
        with pytest.raises(ConfigError, match="reason"):
            ks.engage("  ", _NOW)

    def test_naive_datetime_raises(self) -> None:
        ks = KillSwitch(_make_executor())
        with pytest.raises(ConfigError, match="UTC"):
            ks.engage("test", datetime(2026, 5, 25, 10, 0))


class TestKillSwitchDisengage:
    def test_disengage_resets(self) -> None:
        ks = KillSwitch(_make_executor())
        ks.engage("test", _NOW)
        state = ks.disengage(_NOW)
        assert state.engaged is False
        assert not ks.is_engaged
        assert ks.check_order_allowed()

    def test_disengage_when_not_engaged(self) -> None:
        ks = KillSwitch(_make_executor())
        state = ks.disengage(_NOW)
        assert state.engaged is False

    def test_disengage_naive_raises(self) -> None:
        ks = KillSwitch(_make_executor())
        with pytest.raises(ConfigError, match="UTC"):
            ks.disengage(datetime(2026, 5, 25, 10, 0))


class TestKillSwitchStateProperty:
    def test_state_before_engage(self) -> None:
        ks = KillSwitch(_make_executor())
        state = ks.state
        assert state.engaged is False
        assert state.reason == ""
        assert state.triggered_utc is None

    def test_state_after_engage(self) -> None:
        ks = KillSwitch(_make_executor())
        ks.engage("test", _NOW)
        state = ks.state
        assert state.engaged is True
        assert state.reason == "test"
        assert state.triggered_utc == _NOW


class TestValidateUtc:
    def test_utc_passes(self) -> None:
        _validate_utc(_NOW)

    def test_naive_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 5, 25, 10, 0))

    def test_non_utc_raises(self) -> None:
        ist = timezone(timedelta(hours=5, minutes=30))
        with pytest.raises(ConfigError, match="UTC"):
            _validate_utc(datetime(2026, 5, 25, 10, 0, tzinfo=ist))


class TestDefaultEngageCallback:
    def test_default_callback_handles_alerter_error(self) -> None:
        ks = KillSwitch(_make_executor())
        ks.engage("test reason", _NOW)

    def test_engage_with_explicit_callback(self) -> None:
        callback = MagicMock()
        ks = KillSwitch(_make_executor(), on_engage=callback)
        ks.engage("explicit test", _NOW)
        callback.assert_called_once_with("explicit test", _NOW)
