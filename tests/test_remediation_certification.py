"""
Certification remediation tests covering all 7 priority fixes.

CRITICAL: Executor async safety (place_order_async)
HIGH: Queue maxsize bounds
HIGH: State persistence/recovery
HIGH: _get_symbol_config exchange mapping fix
MEDIUM: HMAC hash chain tamper evidence
MEDIUM: Circuit breaker auto-wiring to kill switch
MEDIUM: Connection pooling for HTTP data providers
"""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.execution.order_manager import OrderManager
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.trade_audit import TradeAuditLogger
from iatb.risk.circuit_breaker import (
    evaluate_and_engage_kill_switch,
    evaluate_circuit_breaker,
)
from iatb.risk.kill_switch import KillSwitch
from iatb.risk.position_limit_guard import (
    ExchangeType,
    PositionLimitConfig,
    PositionLimitGuard,
)


def _make_order_request(**overrides):
    defaults = {
        "exchange": Exchange.NSE,
        "symbol": "RELIANCE",
        "side": OrderSide.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "price": Decimal("100"),
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


def _make_execution_result(**overrides):
    defaults = {
        "order_id": "ORD-001",
        "status": OrderStatus.FILLED,
        "filled_quantity": Decimal("10"),
        "average_price": Decimal("100"),
    }
    defaults.update(overrides)
    return ExecutionResult(**defaults)


class TestAsyncExecutorSafety:
    """CRITICAL: Verify place_order_async offloads to thread pool."""

    @pytest.mark.asyncio
    async def test_place_order_async_returns_result(self) -> None:
        executor = PaperExecutor()
        manager = OrderManager(executor=executor)
        request = _make_order_request()
        result = await manager.place_order_async(request)
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == Decimal("10")

    @pytest.mark.asyncio
    async def test_place_order_async_does_not_block_event_loop(self) -> None:
        executor = PaperExecutor()
        manager = OrderManager(executor=executor)
        tasks = [
            manager.place_order_async(_make_order_request(symbol=f"SYM{i:03d}")) for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        assert all(r.status == OrderStatus.FILLED for r in results)

    @pytest.mark.asyncio
    async def test_place_order_async_respects_kill_switch(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        manager = OrderManager(executor=executor, kill_switch=kill)
        kill.engage("test", datetime.now(UTC))
        request = _make_order_request()
        with pytest.raises(ConfigError):
            await manager.place_order_async(request)


class TestQueueMaxsizeBounds:
    """HIGH: Verify all asyncio.Queue instances have bounded maxsize."""

    def test_inprocess_backend_queue_has_maxsize(self) -> None:
        from iatb.core.queue import InProcessBackend

        backend = InProcessBackend(max_queue_size=50)
        assert backend._max_queue_size == 50

    def test_inprocess_backend_rejects_zero_maxsize(self) -> None:
        from iatb.core.exceptions import EventBusError
        from iatb.core.queue import InProcessBackend

        with pytest.raises(EventBusError):
            InProcessBackend(max_queue_size=0)

    @pytest.mark.asyncio
    async def test_subscribe_creates_bounded_queue(self) -> None:
        from iatb.core.queue import InProcessBackend

        backend = InProcessBackend(max_queue_size=5)
        await backend.start()
        queue = await backend.subscribe("test")
        assert queue.maxsize == 5
        await backend.stop()

    def test_sse_queue_has_maxsize(self) -> None:
        from iatb.core.sse_broadcaster import _SSE_QUEUE_MAXSIZE

        assert _SSE_QUEUE_MAXSIZE > 0

    def test_kite_ws_queue_has_maxsize(self) -> None:
        from iatb.data.kite_ws_provider import _TICK_QUEUE_MAXSIZE

        assert _TICK_QUEUE_MAXSIZE > 0

    def test_kite_ticker_queue_has_maxsize(self) -> None:
        from iatb.data.kite_ticker import _TICK_QUEUE_MAXSIZE

        assert _TICK_QUEUE_MAXSIZE > 0


class TestStatePersistence:
    """HIGH: Verify position/PnL state save and load for crash recovery."""

    def test_save_state_creates_json_file(self, tmp_path: Path) -> None:
        executor = PaperExecutor()
        manager = OrderManager(executor=executor)
        request = _make_order_request()
        manager.place_order(request)
        state_file = tmp_path / "state.json"
        manager.save_state(state_file)
        assert state_file.exists()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "position_state" in data
        assert "order_status" in data
        assert "saved_at_utc" in data

    def test_load_state_restores_positions(self, tmp_path: Path) -> None:
        from iatb.risk.daily_loss_guard import DailyLossGuard

        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        dlg = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=kill,
        )
        manager = OrderManager(executor=executor, daily_loss_guard=dlg)
        request = _make_order_request()
        manager.place_order(request)
        state_file = tmp_path / "state.json"
        manager.save_state(state_file)

        manager2 = OrderManager(executor=executor)
        manager2.load_state(state_file)
        assert "RELIANCE" in manager2._position_state

    def test_load_state_handles_missing_file(self, tmp_path: Path) -> None:
        executor = PaperExecutor()
        manager = OrderManager(executor=executor)
        missing = tmp_path / "nonexistent.json"
        manager.load_state(missing)

    def test_load_state_handles_corrupt_file(self, tmp_path: Path) -> None:
        executor = PaperExecutor()
        manager = OrderManager(executor=executor)
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{invalid json", encoding="utf-8")
        manager.load_state(corrupt)

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from iatb.risk.daily_loss_guard import DailyLossGuard

        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        dlg = DailyLossGuard(
            max_daily_loss_pct=Decimal("0.05"),
            starting_nav=Decimal("100000"),
            kill_switch=kill,
        )
        manager = OrderManager(executor=executor, daily_loss_guard=dlg)
        manager.place_order(_make_order_request(symbol="SYM-A"))
        manager.place_order(
            _make_order_request(symbol="SYM-B", side=OrderSide.SELL, quantity=Decimal("5"))
        )
        state_file = tmp_path / "state.json"
        manager.save_state(state_file)

        manager2 = OrderManager(executor=executor)
        manager2.load_state(state_file)
        assert "SYM-A" in manager2._position_state
        assert len(manager2._order_status) == 2


class TestSymbolConfigFix:
    """HIGH: Verify _get_symbol_config maps symbol to correct exchange."""

    def test_symbol_config_returns_correct_exchange(self) -> None:
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            ),
            PositionLimitConfig(
                exchange=ExchangeType.MCX,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("100000000"),
                max_total_notional=Decimal("1000000000"),
            ),
        ]
        guard = PositionLimitGuard(limits=limits)
        now = datetime.now(UTC)

        guard.validate_order(ExchangeType.NSE_FO, "RELIANCE", Decimal("100"), Decimal("500"), now)
        guard.update_position(ExchangeType.NSE_FO, "RELIANCE", Decimal("100"), Decimal("500"), now)
        config = guard._get_symbol_config("RELIANCE")
        assert config is not None
        assert config.exchange == ExchangeType.NSE_FO

    def test_symbol_config_returns_mcx_for_mcx_symbol(self) -> None:
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            ),
            PositionLimitConfig(
                exchange=ExchangeType.MCX,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("100000000"),
                max_total_notional=Decimal("1000000000"),
            ),
        ]
        guard = PositionLimitGuard(limits=limits)
        now = datetime.now(UTC)

        guard.validate_order(ExchangeType.MCX, "GOLD", Decimal("50"), Decimal("60000"), now)
        guard.update_position(ExchangeType.MCX, "GOLD", Decimal("50"), Decimal("60000"), now)
        config = guard._get_symbol_config("GOLD")
        assert config is not None
        assert config.exchange == ExchangeType.MCX

    def test_symbol_config_returns_none_for_unknown_symbol(self) -> None:
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            ),
        ]
        guard = PositionLimitGuard(limits=limits)
        config = guard._get_symbol_config("UNKNOWN")
        assert config is None


class TestHMACChainTamperEvidence:
    """MEDIUM: Verify HMAC hash chain for audit trail integrity."""

    def test_log_order_produces_chain_hash(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.db"
        logger = TradeAuditLogger(db)
        request = _make_order_request()
        result = _make_execution_result()
        logger.log_order(request, result, strategy_id="STRAT-1")
        trades = logger._store.list_trades(limit=1)
        assert len(trades) == 1
        assert "chain_hash" in trades[0].metadata
        assert len(trades[0].metadata["chain_hash"]) == 64

    def test_chain_hash_changes_per_entry(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.db"
        logger = TradeAuditLogger(db)
        request = _make_order_request()
        for i in range(3):
            result = _make_execution_result(order_id=f"ORD-{i:03d}")
            logger.log_order(request, result, strategy_id="STRAT-1")
        trades = logger._store.list_trades(limit=3)
        hashes = [t.metadata["chain_hash"] for t in trades]
        assert len(set(hashes)) == 3

    def test_verify_chain_passes_for_intact_data(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.db"
        logger = TradeAuditLogger(db)
        request = _make_order_request()
        for i in range(5):
            result = _make_execution_result(order_id=f"ORD-{i:03d}")
            logger.log_order(request, result, strategy_id="STRAT-1")
        assert logger.verify_chain() is True


class TestCircuitBreakerKillSwitchWiring:
    """MEDIUM: Verify circuit breaker auto-engages kill switch on halt."""

    def test_no_halt_does_not_engage_kill_switch(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        now = datetime.now(UTC)
        state = evaluate_and_engage_kill_switch(Decimal("5"), kill, now)
        assert state.halt_required is False
        assert kill.is_engaged is False

    def test_level1_halt_engages_kill_switch(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        now = datetime.now(UTC)
        state = evaluate_and_engage_kill_switch(Decimal("10"), kill, now)
        assert state.halt_required is True
        assert state.level == 1
        assert kill.is_engaged is True

    def test_level2_halt_engages_kill_switch(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        now = datetime.now(UTC)
        state = evaluate_and_engage_kill_switch(Decimal("15"), kill, now)
        assert state.level == 2
        assert kill.is_engaged is True

    def test_level3_halt_engages_kill_switch(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        now = datetime.now(UTC)
        state = evaluate_and_engage_kill_switch(Decimal("20"), kill, now)
        assert state.level == 3
        assert kill.is_engaged is True

    def test_already_engaged_does_not_double_engage(self) -> None:
        executor = PaperExecutor()
        kill = KillSwitch(executor=executor)
        now = datetime.now(UTC)
        evaluate_and_engage_kill_switch(Decimal("10"), kill, now)
        reason_before = kill.state.reason
        evaluate_and_engage_kill_switch(Decimal("20"), kill, now)
        assert kill.state.reason == reason_before

    def test_evaluate_circuit_breaker_still_works_standalone(self) -> None:
        state = evaluate_circuit_breaker(Decimal("12"))
        assert state.level == 1
        assert state.halt_required is True


class TestConnectionPooling:
    """MEDIUM: Verify HTTP connection pool for data providers."""

    def test_pooled_session_creates_with_config(self) -> None:
        from iatb.data.openalgo_provider import _PooledHTTPSession

        session = _PooledHTTPSession("https://api.example.com", pool_size=2, timeout=10)
        assert session._pool_size == 2
        assert session._host == "api.example.com"

    def test_pooled_session_release_reuses_connection(self) -> None:
        from iatb.data.openalgo_provider import _PooledHTTPSession

        session = _PooledHTTPSession("https://api.example.com", pool_size=2)
        conn = session._acquire()
        assert len(session._pool) == 1
        session._release(conn)
        conn2 = session._acquire()
        assert conn2 is conn

    def test_pooled_session_close_cleans_up(self) -> None:
        from iatb.data.openalgo_provider import _PooledHTTPSession

        session = _PooledHTTPSession("https://api.example.com", pool_size=2)
        session._acquire()
        session.close()
        assert len(session._pool) == 0

    @pytest.mark.asyncio
    async def test_provider_uses_injected_http_get(self) -> None:
        from iatb.data.openalgo_provider import OpenAlgoProvider

        call_log = []

        def mock_get(url: str, headers: dict) -> dict:
            call_log.append(url)
            return {
                "data": [
                    {
                        "timestamp": "2026-01-01T09:15:00+00:00",
                        "open": 100,
                        "high": 102,
                        "low": 99,
                        "close": 101,
                        "volume": 1000,
                    }
                ]
            }

        provider = OpenAlgoProvider(
            base_url="https://api.test.local",
            api_key="test",
            http_get=mock_get,
        )
        bars = await provider.get_ohlcv(
            symbol="TEST", exchange=Exchange.NSE, timeframe="1m", limit=1
        )
        assert len(call_log) > 0
        assert "market/ohlcv" in call_log[0]
        assert len(bars) == 1
