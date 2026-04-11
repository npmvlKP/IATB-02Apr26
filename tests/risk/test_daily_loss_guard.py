"""Tests for daily loss guard with automatic kill-switch engagement."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.daily_loss_guard import DailyLossGuard, DailyLossState
from iatb.risk.kill_switch import KillSwitch


@pytest.fixture
def mock_executor():
    """Create a mock executor for testing."""
    executor = MagicMock()
    executor.cancel_all.return_value = 0
    return executor


@pytest.fixture
def mock_kill_switch(mock_executor):
    """Create a mock kill switch for testing."""
    ks = KillSwitch(executor=mock_executor)
    ks.disengage(datetime.now(UTC))  # Start disengaged
    return ks


@pytest.fixture
def daily_loss_guard(mock_kill_switch):
    """Create a daily loss guard with default configuration."""
    return DailyLossGuard(
        max_daily_loss_pct=Decimal("0.05"),
        starting_nav=Decimal("100000"),
        kill_switch=mock_kill_switch,
    )


class TestDailyLossGuardInit:
    """Test initialization of DailyLossGuard."""

    def test_initializes_with_valid_config(self, mock_kill_switch):
        """Test successful initialization with valid parameters."""
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
        )
        assert guard.state == DailyLossState(
            cumulative_pnl=Decimal("0"),
            limit=Decimal("5000"),
            breached=False,
            trade_count=0,
        )

    def test_rejects_zero_max_daily_loss_pct(self, mock_kill_switch):
        """Test that zero max_daily_loss_pct raises error."""
        with pytest.raises(ConfigError, match="max_daily_loss_pct must be in"):
            DailyLossGuard(
                max_daily_loss_pct=Decimal("0"),
                starting_nav=Decimal("100000"),
                kill_switch=mock_kill_switch,
            )

    def test_rejects_negative_max_daily_loss_pct(self, mock_kill_switch):
        """Test that negative max_daily_loss_pct raises error."""
        with pytest.raises(ConfigError, match="max_daily_loss_pct must be in"):
            DailyLossGuard(
                max_daily_loss_pct=Decimal("-0.05"),
                starting_nav=Decimal("100000"),
                kill_switch=mock_kill_switch,
            )

    def test_rejects_max_daily_loss_pct_over_one(self, mock_kill_switch):
        """Test that max_daily_loss_pct > 1 raises error."""
        with pytest.raises(ConfigError, match="max_daily_loss_pct must be in"):
            DailyLossGuard(
                max_daily_loss_pct=Decimal("1.5"),
                starting_nav=Decimal("100000"),
                kill_switch=mock_kill_switch,
            )

    def test_rejects_zero_starting_nav(self, mock_kill_switch):
        """Test that zero starting_nav raises error."""
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            DailyLossGuard(
                max_daily_loss_pct=Decimal("0.05"),
                starting_nav=Decimal("0"),
                kill_switch=mock_kill_switch,
            )

    def test_rejects_negative_starting_nav(self, mock_kill_switch):
        """Test that negative starting_nav raises error."""
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            DailyLossGuard(
                max_daily_loss_pct=Decimal("0.05"),
                starting_nav=Decimal("-1000"),
                kill_switch=mock_kill_switch,
            )


class TestRecordTrade:
    """Test trade recording functionality."""

    def test_records_profitable_trade(self, daily_loss_guard):
        """Test recording a profitable trade updates state correctly."""
        now = datetime.now(UTC)
        result = daily_loss_guard.record_trade(Decimal("1000"), now)
        assert result.cumulative_pnl == Decimal("1000")
        assert result.trade_count == 1
        assert not result.breached
        assert not daily_loss_guard._kill_switch.is_engaged

    def test_records_losing_trade(self, daily_loss_guard):
        """Test recording a losing trade updates state correctly."""
        now = datetime.now(UTC)
        result = daily_loss_guard.record_trade(Decimal("-1000"), now)
        assert result.cumulative_pnl == Decimal("-1000")
        assert result.trade_count == 1
        assert not result.breached

    def test_records_multiple_trades(self, daily_loss_guard):
        """Test recording multiple trades accumulates PnL."""
        now = datetime.now(UTC)
        daily_loss_guard.record_trade(Decimal("1000"), now)
        daily_loss_guard.record_trade(Decimal("-500"), now)
        result = daily_loss_guard.record_trade(Decimal("2000"), now)
        assert result.cumulative_pnl == Decimal("2500")
        assert result.trade_count == 3

    def test_engages_kill_switch_on_breach(self, daily_loss_guard):
        """Test that breach engages kill switch."""
        now = datetime.now(UTC)
        # Record loss that exceeds limit (limit is 5000)
        daily_loss_guard.record_trade(Decimal("-4000"), now)
        result = daily_loss_guard.record_trade(Decimal("-2000"), now)
        assert result.cumulative_pnl == Decimal("-6000")
        assert result.breached
        assert daily_loss_guard._kill_switch.is_engaged

    def test_engages_kill_switch_exactly_at_limit(self, daily_loss_guard):
        """Test that exact limit breach engages kill switch."""
        now = datetime.now(UTC)
        result = daily_loss_guard.record_trade(Decimal("-5000"), now)
        assert result.cumulative_pnl == Decimal("-5000")
        assert result.breached
        assert daily_loss_guard._kill_switch.is_engaged

    def test_rejects_naive_datetime(self, daily_loss_guard):
        """Test that naive datetime raises error."""
        naive_now = datetime.now()  # noqa: DTZ005
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            daily_loss_guard.record_trade(Decimal("1000"), naive_now)

    def test_rejects_non_utc_timezone(self, daily_loss_guard):
        """Test that non-UTC timezone raises error."""
        from datetime import timedelta, timezone

        tz = timezone(timedelta(hours=5, minutes=30))
        non_utc = datetime.now(tz)
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            daily_loss_guard.record_trade(Decimal("1000"), non_utc)


class TestReset:
    """Test reset functionality."""

    def test_resets_state(self, daily_loss_guard):
        """Test that reset clears accumulated state."""
        now = datetime.now(UTC)
        daily_loss_guard.record_trade(Decimal("-4000"), now)
        daily_loss_guard.reset(Decimal("100000"), now)
        assert daily_loss_guard.state == DailyLossState(
            cumulative_pnl=Decimal("0"),
            limit=Decimal("5000"),
            breached=False,
            trade_count=0,
        )

    def test_updates_limit_on_new_nav(self, daily_loss_guard):
        """Test that reset with new NAV updates limit."""
        now = datetime.now(UTC)
        daily_loss_guard.reset(Decimal("200000"), now)
        assert daily_loss_guard.state.limit == Decimal("10000")

    def test_rejects_zero_starting_nav_on_reset(self, daily_loss_guard):
        """Test that reset with zero NAV raises error (covers lines 75-76)."""
        now = datetime.now(UTC)
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            daily_loss_guard.reset(Decimal("0"), now)

    def test_rejects_negative_starting_nav_on_reset(self, daily_loss_guard):
        """Test that reset with negative NAV raises error."""
        now = datetime.now(UTC)
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            daily_loss_guard.reset(Decimal("-1000"), now)

    def test_rejects_naive_datetime_on_reset(self, daily_loss_guard):
        """Test that reset with naive datetime raises error."""
        naive_now = datetime.now()  # noqa: DTZ005
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            daily_loss_guard.reset(Decimal("100000"), naive_now)

    def test_rejects_non_utc_timezone_on_reset(self, daily_loss_guard):
        """Test that reset with non-UTC timezone raises error."""
        from datetime import timedelta, timezone

        tz = timezone(timedelta(hours=5, minutes=30))
        non_utc = datetime.now(tz)
        with pytest.raises(ConfigError, match="datetime must be UTC"):
            daily_loss_guard.reset(Decimal("100000"), non_utc)


class TestDailyLossState:
    """Test DailyLossState dataclass."""

    def test_state_property_returns_current_state(self, daily_loss_guard):
        """Test that state property returns accurate current state."""
        now = datetime.now(UTC)
        daily_loss_guard.record_trade(Decimal("1000"), now)
        daily_loss_guard.record_trade(Decimal("-500"), now)
        state = daily_loss_guard.state
        assert state.cumulative_pnl == Decimal("500")
        assert state.limit == Decimal("5000")
        assert not state.breached  # noqa: W292
        assert state.trade_count == 2

    def test_breached_flag_true_on_limit_breach(self, daily_loss_guard):
        """Test that breached flag is true when limit is breached."""
        now = datetime.now(UTC)
        daily_loss_guard.record_trade(Decimal("-5000"), now)
        state = daily_loss_guard.state
        assert state.breached

    def test_breached_flag_false_within_limit(self, daily_loss_guard):
        """Test that breached flag is false within limit."""
        now = datetime.now(UTC)
        daily_loss_guard.record_trade(Decimal("-4999"), now)
        state = daily_loss_guard.state
        assert not state.breached
