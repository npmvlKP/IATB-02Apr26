"""Tests for paper trading launch scripts.

Covers:
- validate_paper_setup.py: _load_env_values, step functions
- launch_paper_trading.py: _load_env_values, step functions
- observe_paper_trading.py: check functions
- Integration: PaperExecutor + full 7-step safety pipeline
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
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


# ── validate_paper_setup.py tests ──


class TestValidatePaperSetup:
    """Tests for scripts/validate_paper_setup.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "validate_paper_setup", "scripts/validate_paper_setup.py"
        )

    def test_load_env_values_existing_file(self, tmp_path: Path) -> None:
        """Test _load_env_values with a valid .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ZERODHA_API_KEY=testkey123\n"
            "ZERODHA_API_SECRET=testsecret456\n"
            "ZERODHA_ACCESS_TOKEN=token789\n"
            "# Comment line\n\nEMPTY_VALUE=\n",
            encoding="utf-8",
        )
        values = self.mod._load_env_values(env_file)
        assert values["ZERODHA_API_KEY"] == "testkey123"
        assert values["ZERODHA_API_SECRET"] == "testsecret456"

    def test_load_env_values_missing_file(self, tmp_path: Path) -> None:
        values = self.mod._load_env_values(tmp_path / "nonexistent.env")
        assert values == {}

    def test_load_env_values_quoted_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            'KEY1="value_with_quotes"\n' "KEY2='single_quotes'\n",
            encoding="utf-8",
        )
        values = self.mod._load_env_values(env_file)
        assert values["KEY1"] == "value_with_quotes"
        assert values["KEY2"] == "single_quotes"

    def test_step_1_validate_env_file_missing(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            result = self.mod.step_1_validate_env_file()
            assert result is False

    def test_step_3_validate_directories(self, tmp_path: Path) -> None:
        with patch.object(self.mod, "_REQUIRED_DIRS", [tmp_path / "test_dir"]):
            result = self.mod.step_3_validate_directories()
            assert result is True

    def test_step_8_validate_no_live_conflict_clean(self) -> None:
        with patch.object(
            self.mod,
            "_load_env_values",
            return_value={
                "IATB_MODE": "paper",
                "EXECUTION_MODE": "paper",
                "LIVE_TRADING_ENABLED": "false",
            },
        ):
            result = self.mod.step_8_validate_no_live_conflict()
            assert result is True

    def test_step_8_validate_live_conflict_detected(self) -> None:
        with patch.object(
            self.mod,
            "_load_env_values",
            return_value={
                "IATB_MODE": "live",
                "EXECUTION_MODE": "paper",
                "LIVE_TRADING_ENABLED": "false",
            },
        ):
            result = self.mod.step_8_validate_no_live_conflict()
            assert result is False


# ── launch_paper_trading.py tests ──


class TestLaunchPaperTrading:
    """Tests for scripts/launch_paper_trading.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "launch_paper_trading", "scripts/launch_paper_trading.py"
        )

    def test_load_env_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ZERODHA_API_KEY=mykey\nZERODHA_API_SECRET=mysecret\n",
            encoding="utf-8",
        )
        values = self.mod._load_env_values(env_file)
        assert values["ZERODHA_API_KEY"] == "mykey"

    def test_pass_fail_utility(self) -> None:
        assert self.mod._pass_fail(True) == "PASS"
        assert self.mod._pass_fail(False) == "FAIL"

    def test_step_4_create_directories(self) -> None:
        result = self.mod.step_4_create_directories()
        assert result is True

    def test_step_2_validate_credentials_missing_env(self) -> None:
        with patch.object(Path, "exists", return_value=False):
            result = self.mod.step_2_validate_credentials()
            assert result is False

    def test_step_2_validate_credentials_present(self) -> None:
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
                result = self.mod.step_2_validate_credentials()
                assert result is True

    def test_step_12_kill_switch_drill(self) -> None:
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        components: dict[str, object] = {"kill_switch": ks}
        result = self.mod.step_12_kill_switch_drill(components)
        assert result is True
        assert not ks.is_engaged

    def test_step_11_sample_trades(self) -> None:
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
        db_path = _fresh_audit_db("test_step11")
        audit = TradeAuditLogger(db_path)
        throttle = OrderThrottle(max_ops=10)
        mgr = OrderManager(
            executor=executor,
            kill_switch=kill_switch,
            pre_trade_config=pre_trade_config,
            daily_loss_guard=daily_guard,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="TEST-PAPER-001",
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
        pnl_data = self.mod.step_11_sample_trades(components)
        assert "total_pnl" in pnl_data
        assert "filled" in pnl_data
        assert "errors" in pnl_data
        assert pnl_data["filled"] >= Decimal("0")


# ── observe_paper_trading.py tests ──


class TestObservePaperTrading:
    """Tests for scripts/observe_paper_trading.py functions."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod = _import_script(
            "observe_paper_trading", "scripts/observe_paper_trading.py"
        )

    def test_load_env_values(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=value\n", encoding="utf-8")
        values = self.mod._load_env_values(env_file)
        assert values["KEY"] == "value"

    def test_check_config_status_paper_mode(self) -> None:
        with patch("iatb.core.config._config_instance", None):
            status = self.mod.check_config_status()
            if status.get("config_loaded") == "True":
                assert status["execution_mode"] == "paper"

    def test_check_kill_switch_state(self) -> None:
        state = self.mod.check_kill_switch_state()
        if "error" not in state:
            assert "engaged" in state

    def test_check_database_files(self) -> None:
        result = self.mod.check_database_files()
        assert "audit_db" in result
        assert "duckdb" in result

    def test_check_audit_trades(self) -> None:
        today = datetime.now(UTC).date()
        trades = self.mod.check_audit_trades(today)
        assert isinstance(trades, list)

    def test_check_audit_chain_integrity(self) -> None:
        result = self.mod.check_audit_chain_integrity()
        assert isinstance(result, bool)

    def test_pass_fail_utility(self) -> None:
        assert self.mod._pass_fail(True) == "PASS"
        assert self.mod._pass_fail(False) == "FAIL"


# ── Integration: PaperExecutor + Safety Pipeline ──


class TestPaperExecutorSafetyPipeline:
    """Integration tests for PaperExecutor through the safety pipeline."""

    def test_paper_executor_slippage(self) -> None:
        from iatb.core.enums import Exchange, MarketType, OrderSide
        from iatb.execution.base import OrderRequest
        from iatb.execution.paper_executor import PaperExecutor

        executor = PaperExecutor()
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("2800"),
            market_type=MarketType.SPOT,
        )
        result = executor.execute_order(request)
        assert result.status.value == "FILLED"
        assert result.average_price >= Decimal("2800")

    def test_paper_executor_sell_slippage(self) -> None:
        from iatb.core.enums import Exchange, MarketType, OrderSide
        from iatb.execution.base import OrderRequest
        from iatb.execution.paper_executor import PaperExecutor

        executor = PaperExecutor()
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="NIFTY",
            side=OrderSide.SELL,
            quantity=Decimal("5"),
            price=Decimal("22500"),
            market_type=MarketType.SPOT,
        )
        result = executor.execute_order(request)
        assert result.status.value == "FILLED"
        assert result.average_price <= Decimal("22500")

    def test_order_manager_full_pipeline(self) -> None:
        """Test order through full pipeline with fresh audit DB."""
        from iatb.core.enums import Exchange, OrderSide
        from iatb.execution.base import OrderRequest
        from iatb.execution.order_manager import OrderManager
        from iatb.execution.order_throttle import OrderThrottle
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.execution.pre_trade_validator import PreTradeConfig
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        config = PreTradeConfig(
            max_order_quantity=Decimal("100"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        daily_guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=ks,
        )
        db_path = _fresh_audit_db("test_pipeline")
        audit = TradeAuditLogger(db_path)
        throttle = OrderThrottle(max_ops=10)
        mgr = OrderManager(
            executor=executor,
            kill_switch=ks,
            pre_trade_config=config,
            daily_loss_guard=daily_guard,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="TEST-PIPELINE-001",
        )
        mgr.update_market_data(
            last_prices={"RELIANCE": Decimal("2800")},
            positions={},
            total_exposure=Decimal("0"),
        )
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("2800"),
        )
        result = mgr.place_order(request, strategy_id="test_pipeline")
        assert result.status.value == "FILLED"
        assert result.filled_quantity == Decimal("10")

    def test_kill_switch_blocks_orders(self) -> None:
        """Test engaged kill switch blocks orders with fresh audit DB."""
        from iatb.core.enums import Exchange, OrderSide
        from iatb.execution.base import OrderRequest
        from iatb.execution.order_manager import OrderManager
        from iatb.execution.order_throttle import OrderThrottle
        from iatb.execution.paper_executor import PaperExecutor
        from iatb.execution.pre_trade_validator import PreTradeConfig
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.risk.daily_loss_guard import DailyLossGuard
        from iatb.risk.kill_switch import KillSwitch

        executor = PaperExecutor()
        ks = KillSwitch(executor)
        config = PreTradeConfig(
            max_order_quantity=Decimal("100"),
            max_order_value=Decimal("500000"),
            max_price_deviation_pct=Decimal("0.05"),
            max_position_per_symbol=Decimal("200"),
            max_portfolio_exposure=Decimal("1000000"),
        )
        daily_guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=ks,
        )
        db_path = _fresh_audit_db("test_ks")
        audit = TradeAuditLogger(db_path)
        throttle = OrderThrottle(max_ops=10)
        mgr = OrderManager(
            executor=executor,
            kill_switch=ks,
            pre_trade_config=config,
            daily_loss_guard=daily_guard,
            audit_logger=audit,
            order_throttle=throttle,
            algo_id="TEST-KS-001",
        )
        mgr.update_market_data(
            last_prices={"NIFTY": Decimal("22500")},
            positions={},
            total_exposure=Decimal("0"),
        )
        ks.engage("test block", datetime.now(UTC))
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="NIFTY",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("22500"),
        )
        with pytest.raises(Exception, match="kill switch"):
            mgr.place_order(request, strategy_id="test_blocked")
        ks.disengage(datetime.now(UTC))
