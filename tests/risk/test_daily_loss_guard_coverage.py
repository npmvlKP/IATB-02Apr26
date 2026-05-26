"""Comprehensive coverage tests for iatb.risk.daily_loss_guard."""

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


def _make_kill_switch() -> MagicMock:
    ks = MagicMock()
    ks.engage = MagicMock()
    ks.is_engaged = False
    return ks


def _now() -> datetime:
    return datetime(2024, 6, 1, 10, 0, tzinfo=UTC)


class TestDailyLossState:
    def test_properties(self) -> None:
        state = DailyLossState(
            cumulative_pnl=Decimal("-500"),
            limit=Decimal("2000"),
            breached=False,
            trade_count=3,
        )
        assert state.cumulative_pnl == Decimal("-500")
        assert state.limit == Decimal("2000")
        assert state.breached is False
        assert state.trade_count == 3

    def test_frozen(self) -> None:
        state = DailyLossState(
            cumulative_pnl=Decimal("0"),
            limit=Decimal("1000"),
            breached=False,
            trade_count=0,
        )
        with pytest.raises(AttributeError):
            state.cumulative_pnl = Decimal("100")  # type: ignore[misc]


class TestDailyLossStateStore:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        store.save("2024-06-01", Decimal("-100"), 5)
        result = store.load("2024-06-01")
        assert result is not None
        pnl, count = result
        assert pnl == Decimal("-100")
        assert count == 5

    def test_load_missing_date(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        result = store.load("2099-01-01")
        assert result is None

    def test_get_latest_date_empty(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        result = store.get_latest_date()
        assert result is None

    def test_get_latest_date_with_data(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        store.save("2024-06-01", Decimal("-50"), 2)
        store.save("2024-06-02", Decimal("-100"), 5)
        result = store.get_latest_date()
        assert result == "2024-06-02"

    def test_purge_before(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        store.save("2024-06-01", Decimal("-50"), 2)
        store.save("2024-06-02", Decimal("-100"), 5)
        purged = store.purge_before("2024-06-02")
        assert purged == 1
        assert store.load("2024-06-01") is None
        assert store.load("2024-06-02") is not None

    def test_save_upsert(self, tmp_path: Path) -> None:
        store = _DailyLossStateStore(tmp_path / "dl.db")
        store.save("2024-06-01", Decimal("-50"), 2)
        store.save("2024-06-01", Decimal("-200"), 10)
        result = store.load("2024-06-01")
        assert result is not None
        pnl, count = result
        assert pnl == Decimal("-200")
        assert count == 10


class TestDailyLossGuard:
    def test_initial_state_not_breached(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        assert guard.state.breached is False
        assert guard.state.cumulative_pnl == Decimal("0")
        assert guard.state.trade_count == 0

    def test_record_profit(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        state = guard.record_trade(Decimal("500"), _now())
        assert state.cumulative_pnl == Decimal("500")
        assert state.trade_count == 1
        assert state.breached is False
        ks.engage.assert_not_called()

    def test_record_loss_no_breach(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        state = guard.record_trade(Decimal("-1000"), _now())
        assert state.cumulative_pnl == Decimal("-1000")
        assert state.breached is False
        ks.engage.assert_not_called()

    def test_record_loss_breach_triggers_kill_switch(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        state = guard.record_trade(Decimal("-2001"), _now())
        assert state.breached is True
        ks.engage.assert_called_once()

    def test_exact_breach_at_limit(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        state = guard.record_trade(Decimal("-2000"), _now())
        assert state.breached is True
        ks.engage.assert_called_once()

    def test_cumulative_breach(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        guard.record_trade(Decimal("-1000"), _now())
        guard.record_trade(Decimal("-1001"), _now())
        assert guard.state.breached is True
        ks.engage.assert_called_once()

    def test_reset(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        guard.record_trade(Decimal("-500"), _now())
        guard.reset(Decimal("200000"), _now())
        assert guard.state.cumulative_pnl == Decimal("0")
        assert guard.state.trade_count == 0
        assert guard.state.limit == Decimal("4000")

    def test_reset_invalid_nav_raises(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            guard.reset(Decimal("0"), _now())

    def test_zero_max_pct_raises(self) -> None:
        ks = _make_kill_switch()
        with pytest.raises(ConfigError, match="max_daily_loss_pct must be in"):
            DailyLossGuard(Decimal("0"), Decimal("100000"), ks)

    def test_over_one_pct_raises(self) -> None:
        ks = _make_kill_switch()
        with pytest.raises(ConfigError, match="max_daily_loss_pct must be in"):
            DailyLossGuard(Decimal("1.5"), Decimal("100000"), ks)

    def test_zero_nav_raises(self) -> None:
        ks = _make_kill_switch()
        with pytest.raises(ConfigError, match="starting_nav must be positive"):
            DailyLossGuard(Decimal("0.02"), Decimal("0"), ks)

    def test_naive_datetime_raises(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        with pytest.raises(ConfigError, match="UTC"):
            guard.record_trade(Decimal("100"), datetime(2024, 1, 1))

    def test_naive_reset_raises(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        with pytest.raises(ConfigError, match="UTC"):
            guard.reset(Decimal("100000"), datetime(2024, 1, 1))

    def test_with_state_db(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "dl.db",
            now_utc=_now(),
        )
        guard.record_trade(Decimal("-500"), _now())
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "dl.db",
            now_utc=_now(),
        )
        assert guard2.state.cumulative_pnl == Decimal("-500")
        assert guard2.state.trade_count == 1

    def test_save_state(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "dl.db",
            now_utc=_now(),
        )
        guard.record_trade(Decimal("-300"), _now())
        guard.save_state(_now())

    def test_save_state_no_db(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        guard.save_state(_now())

    def test_load_state_no_db(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        result = guard.load_state(_now())
        assert result is False

    def test_load_state_with_db(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        db_path = tmp_path / "dl.db"
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=db_path,
            now_utc=_now(),
        )
        guard.record_trade(Decimal("-300"), _now())
        guard2 = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=db_path,
            now_utc=_now(),
        )
        loaded = guard2.load_state(_now())
        assert loaded is True

    def test_load_state_missing_date(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "dl.db",
            now_utc=_now(),
        )
        different_day = datetime(2099, 1, 1, 10, 0, tzinfo=UTC)
        result = guard.load_state(different_day)
        assert result is False

    def test_init_without_now_utc_no_db(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        assert guard.state.cumulative_pnl == Decimal("0")

    def test_naive_save_state_raises(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        with pytest.raises(ConfigError, match="UTC"):
            guard.save_state(datetime(2024, 1, 1))

    def test_naive_load_state_raises(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        with pytest.raises(ConfigError, match="UTC"):
            guard.load_state(datetime(2024, 1, 1))

    def test_max_pct_exactly_one(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("1"),
            starting_nav=Decimal("100"),
            kill_switch=ks,
        )
        assert guard.state.limit == Decimal("100")

    def test_persist_failure_does_not_crash(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "readonly" / "dl.db",
            now_utc=_now(),
        )
        guard.record_trade(Decimal("-100"), _now())

    def test_persist_state_exception_caught(self, tmp_path: Path) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
            state_db_path=tmp_path / "readonly" / "dl.db",
            now_utc=_now(),
        )
        guard._state_store = MagicMock()
        guard._state_store.save.side_effect = RuntimeError("DB locked")
        guard._persist_state(_now())

    def test_persist_state_no_store(self) -> None:
        ks = _make_kill_switch()
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        guard._state_store = None
        guard._persist_state(_now())
