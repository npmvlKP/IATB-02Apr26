"""Tests for daily loss guard with automatic kill-switch engagement."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.daily_loss_guard import (
    DailyLossGuard,
    DailyLossState,
    _DailyLossStateStore,
)
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


class TestStateStore:
    """Test _DailyLossStateStore SQLite persistence."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading state."""
        db = _DailyLossStateStore(tmp_path / "state.sqlite")
        db.save("2026-05-05", Decimal("-1234.56"), 7)
        loaded = db.load("2026-05-05")
        assert loaded is not None
        assert loaded[0] == Decimal("-1234.56")
        assert loaded[1] == 7

    def test_load_missing_returns_none(self, tmp_path):
        """Test loading a non-existent date returns None."""
        db = _DailyLossStateStore(tmp_path / "state.sqlite")
        loaded = db.load("2026-05-05")
        assert loaded is None

    def test_save_overwrites_existing(self, tmp_path):
        """Test saving twice for same date overwrites."""
        db = _DailyLossStateStore(tmp_path / "state.sqlite")
        db.save("2026-05-05", Decimal("-100"), 1)
        db.save("2026-05-05", Decimal("-200"), 2)
        loaded = db.load("2026-05-05")
        assert loaded == (Decimal("-200"), 2)

    def test_purge_before_removes_old(self, tmp_path):
        """Test purging old records."""
        db = _DailyLossStateStore(tmp_path / "state.sqlite")
        db.save("2026-05-01", Decimal("-100"), 1)
        db.save("2026-05-05", Decimal("-200"), 2)
        deleted = db.purge_before("2026-05-04")
        assert deleted == 1
        assert db.load("2026-05-01") is None
        assert db.load("2026-05-05") is not None


class TestPersistence:
    """Test integrated persistence in DailyLossGuard."""

    def test_persists_and_loads_state(self, tmp_path, mock_kill_switch):
        """Test full persist / reload cycle."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-1000"), now)
        # New instance with same DB
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        assert guard2.state.cumulative_pnl == Decimal("-1000")
        assert guard2.state.trade_count == 1

    def test_no_persistence_without_db_path(self, mock_kill_switch, tmp_path):
        """Test that without state_db_path nothing is persisted."""
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
        )
        guard.record_trade(Decimal("-1000"), now)
        # No state_db_path means no persistence
        assert not (tmp_path / "state.sqlite").exists()

    def test_load_state_explicit(self, tmp_path, mock_kill_switch):
        """Test explicit load_state method."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-2000"), now)
        # Create a new guard with no prior state
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        loaded = guard2.load_state(now)
        assert loaded is True
        assert guard2.state.cumulative_pnl == Decimal("-2000")
        assert guard2.state.trade_count == 1

    def test_load_state_without_db(self, mock_kill_switch):
        """Test load_state returns False if no DB configured."""
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
        )
        assert guard.load_state(now) is False

    def test_save_state_explicit(self, tmp_path, mock_kill_switch):
        """Test explicit save_state."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-3000"), now)
        guard.save_state(now)
        # Verify via new instance
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        assert guard2.state.cumulative_pnl == Decimal("-3000")

    def test_reset_clears_persisted_state(self, tmp_path, mock_kill_switch):
        """Test reset clears persisted state."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-4000"), now)
        guard.reset(Decimal("100000"), now)
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        assert guard2.state.cumulative_pnl == Decimal("0")
        assert guard2.state.trade_count == 0

    def test_persistence_survives_crash(self, tmp_path, mock_kill_switch):
        """Simulate crash and recovery: PnL continuity."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-1000"), now)
        guard.record_trade(Decimal("-2000"), now)
        # Simulate crash: create new instance
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        assert guard2.state.cumulative_pnl == Decimal("-3000")
        assert guard2.state.trade_count == 2
        # Continue trading after recovery
        guard2.record_trade(Decimal("-500"), now)
        assert guard2.state.cumulative_pnl == Decimal("-3500")
        assert guard2.state.trade_count == 3

    def test_persists_on_record_trade(self, tmp_path, mock_kill_switch):
        """Test that each record_trade call persists."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-500"), now)
        # Inspect DB directly
        store = _DailyLossStateStore(db_path)
        loaded = store.load("2026-05-05")
        assert loaded == (Decimal("-500"), 1)

    def test_different_dates_isolated(self, tmp_path, mock_kill_switch):
        """Test different dates have isolated state."""
        db_path = tmp_path / "state.sqlite"
        now1 = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        now2 = datetime(2026, 5, 6, 12, 0, 0, tzinfo=UTC)
        guard1 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
            now_utc=now1,
        )
        guard1.record_trade(Decimal("-1000"), now1)
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
            now_utc=now2,
        )
        guard2.record_trade(Decimal("-2000"), now2)
        store = _DailyLossStateStore(db_path)
        assert store.load("2026-05-05") == (Decimal("-1000"), 1)
        assert store.load("2026-05-06") == (Decimal("-2000"), 1)


class TestPersistenceFailureRecovery:
    """Test graceful degradation when persistence fails."""

    @staticmethod
    def _make_unwritable(path: Path) -> None:  # noqa: S103
        """Make a directory unwritable (Windows-only test helper)."""
        import stat

        path.chmod(stat.S_IREAD)  # nosec B103

    @staticmethod
    def _make_writable(path: Path) -> None:  # noqa: S103
        """Make a directory writable again (Windows-only test helper)."""
        import stat

        path.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)  # nosec B103

    def test_graceful_on_write_error(self, tmp_path, mock_kill_switch, caplog):
        """Test that write errors are logged and not raised."""
        db_path = tmp_path / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        self._make_unwritable(db_path.parent)
        guard.record_trade(Decimal("-1000"), now)
        # Should not raise; state remains in memory
        assert guard.state.cumulative_pnl == Decimal("-1000")
        # Cleanup
        self._make_writable(db_path.parent)


class TestPersistencePathHandling:
    """Test various path handling scenarios."""

    def test_nested_path_created(self, tmp_path, mock_kill_switch):
        """Test that nested DB paths are created."""
        db_path = tmp_path / "risk" / "state.sqlite"
        now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=UTC)
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=mock_kill_switch,
            state_db_path=db_path,
        )
        guard.record_trade(Decimal("-1000"), now)
        assert db_path.exists()
