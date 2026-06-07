"""Tests for production paper trading scripts.

Covers:
- paper_trading_deploy.py: deploy script functions
- paper_trading_monitor.py: monitor script functions
- validate_paper_prerequisites.py: validator script functions
"""

from __future__ import annotations

import importlib
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest


def _import_script(module_name: str, script_path: str):
    """Import a script as a module without running its main()."""
    import sys

    script = Path(script_path)
    if not script.exists():
        pytest.skip(f"Script not found: {script_path}")
    spec = importlib.util.spec_from_file_location(module_name, str(script))
    if spec is None or spec.loader is None:
        pytest.skip(f"Cannot create spec for {script_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fresh_audit_db(name: str) -> Path:
    """Create a fresh audit DB path and delete any existing file."""
    db = Path(f"data/audit/{name}.sqlite")
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    return db


# ── paper_trading_deploy.py tests ──


class TestPaperTradingDeploy:
    """Tests for scripts/paper_trading_deploy.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "paper_trading_deploy", "scripts/paper_trading_deploy.py"
        )

    def test_load_env_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ZERODHA_API_KEY=deploykey\n" "ZERODHA_API_SECRET=deploysecret\n",
            encoding="utf-8",
        )
        values = self.mod._load_env_values(env_file)
        assert values["ZERODHA_API_KEY"] == "deploykey"

    def test_pass_fail_utility(self) -> None:
        assert self.mod._pass_fail(True) == "PASS"
        assert self.mod._pass_fail(False) == "FAIL"

    def test_step_5_create_directories(self) -> None:
        result = self.mod.step_5_create_directories()
        assert result is True

    def test_step_3_validate_credentials_missing_env(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            result = self.mod.step_3_validate_credentials()
            assert result is False

    def test_step_3_validate_credentials_present(self) -> None:
        with patch.object(
            self.mod,
            "_load_env_values",
            return_value={
                "ZERODHA_API_KEY": "valid_key",
                "ZERODHA_API_SECRET": "valid_secret",
                "ZERODHA_ACCESS_TOKEN": "valid_token",
            },
        ):
            with patch.object(Path, "exists", return_value=True):
                result = self.mod.step_3_validate_credentials()
                assert result is True

    def test_step_13_kill_switch_drill(self) -> None:
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        components: dict[str, object] = {"kill_switch": ks}
        result = self.mod.step_13_kill_switch_drill(components)
        assert result is True
        assert not ks.is_engaged

    def test_step_12_sample_trades(self) -> None:
        """Test sample trade execution with fresh audit DB."""
        from iatb.execution.order_manager import OrderManager
        from iatb.execution.order_throttle import OrderThrottle
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.execution.pre_trade_validator import PreTradeConfig
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        kill_switch = KillSwitch(executor)
        pre_trade_config = PreTradeConfig(
            max_order_quantity=Decimal("100"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        daily_guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=kill_switch,
        )
        db_path = _fresh_audit_db("test_deploy_step12")
        audit = TradeAuditLogger(db_path)
        throttle = OrderThrottle(max_ops=10)
        mgr = OrderManager(
            executor=executor,
            kill_switch=kill_switch,
            pre_trade_config=pre_trade_config,
            daily_loss_guard=daily_guard,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="TEST-DEPLOY-001",
        )
        mgr.update_market_data(
            last_prices={"NIFTY": Decimal("22500")},
            positions={},
            total_exposure=Decimal("0"),
        )
        components: dict[str, object] = {
            "kill_switch": kill_switch,
            "order_manager": mgr,
            "daily_guard": daily_guard,
        }
        pnl_data = self.mod.step_12_sample_trades(components)
        assert "total_pnl" in pnl_data
        assert "filled" in pnl_data
        assert "errors" in pnl_data


# ── paper_trading_monitor.py tests ──


class TestPaperTradingMonitor:
    """Tests for scripts/paper_trading_monitor.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "paper_trading_monitor", "scripts/paper_trading_monitor.py"
        )

    def test_pass_fail_utility(self) -> None:
        assert self.mod._pass_fail(True) == "PASS"
        assert self.mod._pass_fail(False) == "FAIL"

    def test_load_env_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=monitor_value\n", encoding="utf-8")
        values = self.mod._load_env_values(env_file)
        assert values["KEY"] == "monitor_value"

    def test_check_kill_switch_state(self) -> None:
        state = self.mod.check_kill_switch_state()
        if "error" not in state:
            assert "engaged" in state

    def test_check_database_files(self) -> None:
        result = self.mod.check_database_files()
        assert "audit_db" in result
        assert "duckdb" in result

    def test_check_daily_loss_guard(self) -> None:
        state = self.mod.check_daily_loss_guard()
        if "error" not in state:
            assert "cumulative_pnl" in state

    def test_check_positions(self) -> None:
        result = self.mod.check_positions()
        assert "position_count" in result

    def test_check_session_pnl(self) -> None:
        summary = self.mod.check_session_pnl()
        assert "total_trades" in summary

    def test_assess_overall_health_healthy(self) -> None:
        health = self.mod.assess_overall_health({"check_a": True, "check_b": True})
        assert health["status"] == "HEALTHY"

    def test_assess_overall_health_unhealthy(self) -> None:
        health = self.mod.assess_overall_health({"check_a": True, "check_b": False})
        assert health["status"] == "UNHEALTHY"

    def test_assess_overall_health_degraded(self) -> None:
        health = self.mod.assess_overall_health(
            {"a": True, "b": True, "c": True, "d": True, "e": False}
        )
        assert health["status"] == "DEGRADED"


# ── validate_paper_prerequisites.py tests ──


class TestValidatePaperPrerequisites:
    """Tests for scripts/validate_paper_prerequisites.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "validate_paper_prerequisites",
            "scripts/validate_paper_prerequisites.py",
        )

    def test_pass_fail_utility(self) -> None:
        assert self.mod._pass_fail(True) == "PASS"
        assert self.mod._pass_fail(False) == "FAIL"

    def test_gate_1_python_version(self) -> None:
        result = self.mod.gate_1_python_version()
        assert result is True

    def test_gate_4_env_credentials_missing(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            result = self.mod.gate_4_env_credentials()
            assert result is False

    def test_gate_6_directories(self) -> None:
        result = self.mod.gate_6_directories()
        assert result is True

    def test_gate_8_paper_executor(self) -> None:
        result = self.mod.gate_8_paper_executor()
        assert result is True

    def test_gate_9_kill_switch(self) -> None:
        result = self.mod.gate_9_kill_switch()
        assert result is True

    def test_load_env_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ZERODHA_API_KEY=prereqkey\n" "ZERODHA_API_SECRET=prereqsecret\n",
            encoding="utf-8",
        )
        values = self.mod._load_env_values(env_file)
        assert values["ZERODHA_API_KEY"] == "prereqkey"
