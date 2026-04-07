"""Tests for pre-paper-trading safety infrastructure."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.pre_trade_validator import PreTradeConfig, validate_order
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.daily_loss_guard import DailyLossGuard
from iatb.risk.kill_switch import KillSwitch

_NOW = datetime(2026, 4, 5, 10, 0, 0, tzinfo=UTC)


def _make_request(
    symbol: str = "NIFTY",
    quantity: str = "10",
    price: str = "100",
) -> OrderRequest:
    return OrderRequest(
        exchange=Exchange.NSE,
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
    )


# ── Kill Switch ──


class TestKillSwitch:
    def test_starts_disengaged(self) -> None:
        ks = KillSwitch(PaperExecutor())
        assert ks.is_engaged is False
        assert ks.check_order_allowed() is True

    def test_engage_blocks_orders(self) -> None:
        ks = KillSwitch(PaperExecutor())
        ks.engage("test halt", _NOW)
        assert ks.is_engaged is True
        assert ks.check_order_allowed() is False
        assert ks.state.reason == "test halt"

    def test_disengage_allows_orders(self) -> None:
        ks = KillSwitch(PaperExecutor())
        ks.engage("test halt", _NOW)
        ks.disengage(_NOW)
        assert ks.is_engaged is False
        assert ks.check_order_allowed() is True

    def test_engage_calls_cancel_all(self) -> None:
        executor = PaperExecutor()
        ks = KillSwitch(executor)
        state = ks.engage("emergency", _NOW)
        assert state.engaged is True

    def test_engage_fires_callback(self) -> None:
        fired: list[str] = []
        ks = KillSwitch(PaperExecutor(), on_engage=lambda r, t: fired.append(r))
        ks.engage("alert test", _NOW)
        assert fired == ["alert test"]

    def test_empty_reason_raises(self) -> None:
        ks = KillSwitch(PaperExecutor())
        with pytest.raises(ConfigError, match="reason cannot be empty"):
            ks.engage("", _NOW)

    def test_double_engage_is_idempotent(self) -> None:
        ks = KillSwitch(PaperExecutor())
        ks.engage("first", _NOW)
        state = ks.engage("second", _NOW)
        assert state.reason == "first"


# ── Daily Loss Guard ──


class TestDailyLossGuard:
    def _guard(self) -> tuple[DailyLossGuard, KillSwitch]:
        ks = KillSwitch(PaperExecutor())
        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("100000"),
            kill_switch=ks,
        )
        return guard, ks

    def test_no_breach_below_limit(self) -> None:
        guard, ks = self._guard()
        state = guard.record_trade(Decimal("-500"), _NOW)
        assert state.breached is False
        assert ks.is_engaged is False

    def test_breach_engages_kill_switch(self) -> None:
        guard, ks = self._guard()
        guard.record_trade(Decimal("-2100"), _NOW)
        assert ks.is_engaged is True

    def test_cumulative_tracking(self) -> None:
        guard, ks = self._guard()
        guard.record_trade(Decimal("-1000"), _NOW)
        guard.record_trade(Decimal("-1100"), _NOW)
        assert ks.is_engaged is True

    def test_reset_clears_state(self) -> None:
        guard, ks = self._guard()
        guard.record_trade(Decimal("-500"), _NOW)
        guard.reset(Decimal("100000"), _NOW)
        assert guard.state.cumulative_pnl == Decimal("0")
        assert guard.state.trade_count == 0

    def test_invalid_config_raises(self) -> None:
        ks = KillSwitch(PaperExecutor())
        with pytest.raises(ConfigError, match="max_daily_loss_pct"):
            DailyLossGuard(Decimal("0"), Decimal("100000"), ks)


# ── Pre-Trade Validator ──


def _default_config() -> PreTradeConfig:
    return PreTradeConfig(
        max_order_quantity=Decimal("100"),
        max_order_value=Decimal("500000"),
        max_price_deviation_pct=Decimal("0.05"),
        max_position_per_symbol=Decimal("200"),
        max_portfolio_exposure=Decimal("1000000"),
    )


class TestPreTradeValidator:
    def test_valid_order_passes(self) -> None:
        req = _make_request()
        result = validate_order(
            req,
            _default_config(),
            {"NIFTY": Decimal("100")},
            {},
            Decimal("0"),
        )
        assert result == req

    def test_fat_finger_rejects(self) -> None:
        req = _make_request(quantity="500")
        with pytest.raises(ConfigError, match="fat-finger"):
            validate_order(
                req,
                _default_config(),
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
            )

    def test_notional_rejects(self) -> None:
        req = _make_request(quantity="90", price="10000")
        with pytest.raises(ConfigError, match="notional"):
            validate_order(
                req,
                _default_config(),
                {"NIFTY": Decimal("10000")},
                {},
                Decimal("0"),
            )

    def test_price_deviation_rejects(self) -> None:
        req = _make_request(price="200")
        with pytest.raises(ConfigError, match="price deviation"):
            validate_order(
                req,
                _default_config(),
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
            )

    def test_position_limit_rejects(self) -> None:
        req = _make_request(quantity="50")
        with pytest.raises(ConfigError, match="position"):
            validate_order(
                req,
                _default_config(),
                {"NIFTY": Decimal("100")},
                {"NIFTY": Decimal("180")},
                Decimal("0"),
            )

    def test_exposure_rejects(self) -> None:
        req = _make_request(quantity="10", price="100")
        with pytest.raises(ConfigError, match="exposure"):
            validate_order(
                req,
                _default_config(),
                {"NIFTY": Decimal("100")},
                {},
                Decimal("999500"),
            )


# ── Trade Audit Logger ──


class TestTradeAuditLogger:
    def test_log_and_query(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        logger = TradeAuditLogger(db)
        req = _make_request()
        result = ExecutionResult(
            order_id="TEST-001",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("10"),
            average_price=Decimal("100.5"),
        )
        logger.log_order(req, result, "momentum", "ALGO-1")
        today = datetime.now(UTC).date()
        trades = logger.query_daily_trades(today)
        assert len(trades) == 1
        assert trades[0].order_id == "TEST-001"
        assert trades[0].symbol == "NIFTY"


# ── Pre-Flight Checks ──


class TestPreflightChecks:
    def test_all_pass(self, tmp_path: Path) -> None:
        from iatb.core.preflight import run_preflight_checks

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, data_dir, audit_path) is True

    def test_engaged_kill_switch_fails(self, tmp_path: Path) -> None:
        from iatb.core.preflight import run_preflight_checks

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        ks.engage("test", _NOW)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, data_dir, audit_path) is False

    def test_missing_data_dir_fails(self, tmp_path: Path) -> None:
        from iatb.core.preflight import run_preflight_checks

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        missing = tmp_path / "nonexistent"
        audit_path = tmp_path / "audit" / "trades.sqlite"
        assert run_preflight_checks(executor, ks, missing, audit_path) is False
