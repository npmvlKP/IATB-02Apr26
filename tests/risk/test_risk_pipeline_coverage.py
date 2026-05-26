"""Comprehensive coverage tests for iatb.risk.risk_pipeline."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange, MarketType, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.risk.risk_pipeline import (
    RiskPipeline,
    RiskPipelineResult,
    _create_dummy_kill_switch,
    _validate_utc,
)

_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


def _make_order(**overrides: object) -> OrderRequest:
    defaults = {
        "exchange": Exchange.NSE,
        "symbol": "RELIANCE",
        "side": OrderSide.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "price": Decimal("2500"),
        "market_type": MarketType.SPOT,
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


def _make_execution_result(**overrides: object) -> ExecutionResult:
    defaults = {
        "order_id": "PAPER-000001",
        "status": OrderStatus.FILLED,
        "filled_quantity": Decimal("10"),
        "average_price": Decimal("2500"),
    }
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def _make_mock_executor() -> MagicMock:
    executor = MagicMock()
    executor.execute_order.return_value = _make_execution_result()
    executor.cancel_all.return_value = 0
    executor.close_order.return_value = False
    return executor


class TestRiskPipelineResult:
    def test_create_rejected_defaults(self) -> None:
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="test rejection",
        )
        assert result.allowed is False
        assert result.rejection_reason == "test rejection"
        assert result.kill_switch_engaged is False
        assert result.throttle_accepted is True
        assert result.pre_trade_passed is True
        assert result.execution_result is None
        assert result.audit_record_id == ""

    def test_create_rejected_kill_switch(self) -> None:
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="kill switch",
            kill_switch_engaged=True,
        )
        assert result.kill_switch_engaged is True

    def test_create_rejected_throttle(self) -> None:
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="throttle",
            throttle_accepted=False,
        )
        assert result.throttle_accepted is False

    def test_create_rejected_pre_trade(self) -> None:
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="pre-trade",
            pre_trade_passed=False,
        )
        assert result.pre_trade_passed is False

    def test_create_rejected_with_daily_loss_state(self) -> None:
        from iatb.risk.daily_loss_guard import DailyLossGuard

        guard = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.02"),
            starting_nav=Decimal("1000000"),
            kill_switch=_create_dummy_kill_switch(),
        )
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="test",
            daily_loss_state=guard.state,
        )
        assert result.daily_loss_state == guard.state

    def test_create_rejected_with_now_utc(self) -> None:
        result = RiskPipelineResult.create_rejected(
            order_id="TEST-001",
            rejection_reason="test",
            now_utc=_NOW,
        )
        assert result.timestamp_utc is not None


class TestRiskPipelineInit:
    def test_basic_init(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        assert pipeline.kill_switch is None


class TestRiskPipelineProcessOrder:
    def test_full_pipeline_passes(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order()
        result = pipeline.process_order(order, _NOW)
        assert result.allowed is True
        assert result.rejection_reason is None

    def test_kill_switch_rejects(self) -> None:
        ks = MagicMock()
        ks.check_order_allowed.return_value = False
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=ks,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order()
        result = pipeline.process_order(order, _NOW)
        assert result.allowed is False
        assert result.kill_switch_engaged is True

    def test_throttle_rejects(self) -> None:
        throttle = MagicMock()
        throttle.check_and_record.return_value = False
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=throttle,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order()
        result = pipeline.process_order(order, _NOW)
        assert result.allowed is False
        assert result.throttle_accepted is False

    def test_naive_datetime_raises(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order()
        with pytest.raises(ConfigError, match="UTC"):
            pipeline.process_order(order, datetime(2026, 5, 25, 10, 0))

    def test_with_trade_audit(self) -> None:
        audit = MagicMock()
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=audit,
        )
        order = _make_order()
        result = pipeline.process_order(
            order, _NOW, strategy_id="STRAT-1", algo_id="ALGO-1"
        )
        assert result.allowed is True
        audit.log_order.assert_called_once()


class TestRiskPipelineUpdateMarketData:
    def test_update_market_data(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pipeline.update_market_data(
            last_prices={"RELIANCE": Decimal("2500")},
            positions={"RELIANCE": Decimal("10")},
            total_exposure=Decimal("25000"),
        )
        assert pipeline._last_prices["RELIANCE"] == Decimal("2500")
        assert pipeline._positions["RELIANCE"] == Decimal("10")
        assert pipeline._total_exposure == Decimal("25000")


class TestRiskPipelineProcessBuyPnl:
    def test_buy_closing_short(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_buy_pnl(
            "RELIANCE", Decimal("10"), Decimal("2400"), Decimal("-15"), Decimal("2500")
        )
        assert pnl > Decimal("0")
        qty, _ = new_state
        assert qty < Decimal("0")

    def test_buy_closing_full_short(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_buy_pnl(
            "RELIANCE", Decimal("15"), Decimal("2400"), Decimal("-10"), Decimal("2500")
        )
        assert pnl > Decimal("0")
        qty, _ = new_state
        assert qty > Decimal("0")

    def test_buy_opening_long(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_buy_pnl(
            "RELIANCE", Decimal("10"), Decimal("2500"), Decimal("0"), Decimal("0")
        )
        assert pnl == Decimal("0")
        qty, avg = new_state
        assert qty == Decimal("10")
        assert avg == Decimal("2500")

    def test_buy_adding_to_long(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_buy_pnl(
            "RELIANCE", Decimal("10"), Decimal("2600"), Decimal("10"), Decimal("2500")
        )
        assert pnl == Decimal("0")
        qty, avg = new_state
        assert qty == Decimal("20")

    def test_buy_closing_exact_short(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_buy_pnl(
            "RELIANCE", Decimal("10"), Decimal("2400"), Decimal("-10"), Decimal("2500")
        )
        assert pnl > Decimal("0")
        qty, _ = new_state
        assert qty == Decimal("0")


class TestRiskPipelineProcessSellPnl:
    def test_sell_closing_long(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_sell_pnl(
            "RELIANCE", Decimal("10"), Decimal("2600"), Decimal("10"), Decimal("2500")
        )
        assert pnl > Decimal("0")
        qty, _ = new_state
        assert qty == Decimal("0")

    def test_sell_partial_close(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_sell_pnl(
            "RELIANCE", Decimal("5"), Decimal("2600"), Decimal("10"), Decimal("2500")
        )
        assert pnl > Decimal("0")
        qty, avg = new_state
        assert qty == Decimal("5")
        assert avg == Decimal("2500")

    def test_sell_opening_short(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_sell_pnl(
            "RELIANCE", Decimal("10"), Decimal("2500"), Decimal("0"), Decimal("0")
        )
        assert pnl == Decimal("0")
        qty, _ = new_state
        assert qty < Decimal("0")

    def test_sell_adding_to_short(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pnl, new_state = pipeline._process_sell_pnl(
            "RELIANCE", Decimal("5"), Decimal("2550"), Decimal("-10"), Decimal("2500")
        )
        assert pnl == Decimal("0")
        qty, _ = new_state
        assert qty == Decimal("-15")


class TestRiskPipelineCalculateRealizedPnl:
    def test_zero_filled_quantity(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order()
        result = _make_execution_result(filled_quantity=Decimal("0"))
        pnl = pipeline._calculate_realized_pnl(order, result)
        assert pnl == Decimal("0")

    def test_buy_pnl(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        order = _make_order(side=OrderSide.BUY)
        result = _make_execution_result()
        pnl = pipeline._calculate_realized_pnl(order, result)
        assert isinstance(pnl, Decimal)

    def test_sell_pnl(self) -> None:
        executor = _make_mock_executor()
        pipeline = RiskPipeline(
            kill_switch=None,
            order_throttle=None,
            pre_trade_config=None,
            paper_executor=executor,
            daily_loss_guard=None,
            trade_audit_logger=None,
        )
        pipeline._position_state["RELIANCE"] = (Decimal("10"), Decimal("2500"))
        order = _make_order(side=OrderSide.SELL)
        result = _make_execution_result(average_price=Decimal("2600"))
        pnl = pipeline._calculate_realized_pnl(order, result)
        assert pnl > Decimal("0")


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


class TestCreateDummyKillSwitch:
    def test_creates_kill_switch(self) -> None:
        ks = _create_dummy_kill_switch()
        assert ks is not None
        assert not ks.is_engaged

    def test_dummy_executor_cancel_all(self) -> None:
        ks = _create_dummy_kill_switch()
        state = ks.engage("test", _NOW)
        assert state.engaged is True

    def test_dummy_executor_execute_order(self) -> None:
        ks = _create_dummy_kill_switch()
        executor = ks._executor
        order = _make_order()
        result = executor.execute_order(order)
        assert result.order_id == "DUMMY"
        assert result.status == OrderStatus.FILLED

    def test_dummy_executor_close_order(self) -> None:
        ks = _create_dummy_kill_switch()
        executor = ks._executor
        assert executor.close_order("any-id") is False
