"""Tests for kill switch module."""

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.kill_switch import KillSwitch, KillSwitchState


@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.cancel_all.return_value = 3
    return executor


@pytest.fixture
def kill_switch(mock_executor):
    return KillSwitch(executor=mock_executor)


class TestKillSwitchInit:
    def test_initial_state_disengaged(self, kill_switch):
        assert not kill_switch.is_engaged
        state = kill_switch.state
        assert not state.engaged
        assert state.reason == ""
        assert state.triggered_utc is None

    def test_init_with_callback(self, mock_executor):
        cb = MagicMock()
        ks = KillSwitch(executor=mock_executor, on_engage=cb)
        assert ks._on_engage is cb

    def test_init_without_callback(self, mock_executor):
        ks = KillSwitch(executor=mock_executor)
        assert ks._on_engage is not None
        assert callable(ks._on_engage)


class TestEngage:
    def test_engage_sets_state(self, kill_switch, mock_executor):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        state = kill_switch.engage("test reason", now)
        assert kill_switch.is_engaged
        assert state.engaged
        assert state.reason == "test reason"
        assert state.triggered_utc == now

    def test_engage_cancels_all_orders(self, kill_switch, mock_executor):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test", now)
        mock_executor.cancel_all.assert_called_once()

    def test_engage_calls_callback(self, mock_executor):
        cb = MagicMock()
        ks = KillSwitch(executor=mock_executor, on_engage=cb)
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        ks.engage("test", now)
        cb.assert_called_once_with("test", now)

    def test_engage_without_callback_no_error(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test", now)
        assert kill_switch.is_engaged

    def test_engage_when_already_engaged_returns_current_state(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("first", now)
        state2 = kill_switch.engage("second", now)
        assert state2.reason == "first"

    def test_engage_empty_reason_raises_error(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="cannot be empty"):
            kill_switch.engage("", now)

    def test_engage_whitespace_reason_raises_error(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="cannot be empty"):
            kill_switch.engage("   ", now)

    def test_engage_naive_datetime_raises_error(self, kill_switch):
        naive = datetime(2026, 1, 5, 10, 0)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            kill_switch.engage("test", naive)

    def test_engage_non_utc_timezone_raises_error(self, kill_switch):
        tz = timezone(timedelta(hours=5, minutes=30))
        non_utc = datetime(2026, 1, 5, 10, 0, tzinfo=tz)
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            kill_switch.engage("test", non_utc)


class TestDisengage:
    def test_disengage_resets_state(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test", now)
        state = kill_switch.disengage(now)
        assert not kill_switch.is_engaged
        assert not state.engaged
        assert state.reason == ""
        assert state.triggered_utc is None

    def test_disengage_when_not_engaged_returns_current_state(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        state = kill_switch.disengage(now)
        assert not state.engaged

    def test_disengage_naive_datetime_raises_error(self, kill_switch):
        naive = datetime(2026, 1, 5, 10, 0)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            kill_switch.disengage(naive)

    def test_disengage_non_utc_timezone_raises_error(self, kill_switch):
        tz = timezone(timedelta(hours=5, minutes=30))
        non_utc = datetime(2026, 1, 5, 10, 0, tzinfo=tz)
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            kill_switch.disengage(non_utc)


class TestCheckOrderAllowed:
    def test_allowed_when_disengaged(self, kill_switch):
        assert kill_switch.check_order_allowed() is True

    def test_blocked_when_engaged(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test", now)
        assert kill_switch.check_order_allowed() is False

    def test_allowed_after_disengage(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test", now)
        kill_switch.disengage(now)
        assert kill_switch.check_order_allowed() is True


class TestStateProperty:
    def test_state_returns_current_state(self, kill_switch):
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        kill_switch.engage("test reason", now)
        state = kill_switch.state
        assert state == KillSwitchState(
            engaged=True,
            reason="test reason",
            triggered_utc=now,
        )


class TestDefaultEngageCallback:
    def test_default_callback_sends_alert(self, mock_executor):
        from unittest.mock import patch

        from iatb.risk.kill_switch import KillSwitch

        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

        with patch("iatb.risk.kill_switch.get_alerter") as mock_get_alerter:
            mock_alerter = MagicMock()
            mock_get_alerter.return_value = mock_alerter

            ks = KillSwitch(executor=mock_executor)
            ks.engage("test reason", now)

            mock_alerter.send_kill_switch_alert.assert_called_once_with("test reason", now)

    def test_default_callback_handles_errors(self, mock_executor):
        from unittest.mock import patch

        from iatb.risk.kill_switch import KillSwitch

        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

        with patch("iatb.risk.kill_switch.get_alerter") as mock_get_alerter:
            mock_alerter = MagicMock()
            mock_alerter.send_kill_switch_alert.side_effect = Exception("test error")
            mock_get_alerter.return_value = mock_alerter

            ks = KillSwitch(executor=mock_executor)
            state = ks.engage("test reason", now)

            assert state.engaged is True
            assert state.reason == "test reason"
