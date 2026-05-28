"""Coverage tests for iatb.core.strategy_runner — multi-strategy orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.strategy_runner import (
    SharedDataProviderPool,
    SimplePositionGuard,
    StrategyConfig,
    StrategyRunner,
    StrategyScanResult,
    StrategyState,
    _neutral_strength_inputs,
)
from iatb.data.base import OHLCVBar


def _make_config(
    strategy_id: str = "strat-1",
    strategy_type: str = "momentum",
    allocation_pct: Decimal = Decimal("50"),
    max_positions: int = 5,
    max_position_value: Decimal = Decimal("100000"),
    enabled: bool = True,
) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        symbols=["RELIANCE", "TCS"],
        exchange=Exchange.NSE,
        allocation_pct=allocation_pct,
        max_positions=max_positions,
        max_position_value=max_position_value,
        enabled=enabled,
    )


def _make_bar(symbol: str = "RELIANCE", close: str = "2500") -> OHLCVBar:
    from iatb.core.types import create_price, create_quantity, create_timestamp

    return OHLCVBar(
        timestamp=create_timestamp(datetime(2024, 6, 15, 10, 0, tzinfo=UTC)),
        exchange=Exchange.NSE,
        symbol=symbol,
        open=create_price(close),
        high=create_price(close),
        low=create_price(close),
        close=create_price(close),
        volume=create_quantity("1000"),
        source="test",
    )


class TestNeutralStrengthInputs:
    def test_returns_strength_inputs(self) -> None:
        inputs = _neutral_strength_inputs()
        assert inputs.breadth_ratio == Decimal("1.0")
        assert inputs.adx == Decimal("20")
        assert inputs.volume_ratio == Decimal("1.0")

    def test_regime_is_sideways(self) -> None:
        inputs = _neutral_strength_inputs()
        from iatb.market_strength.regime_detector import MarketRegime

        assert inputs.regime == MarketRegime.SIDEWAYS


class TestSimplePositionGuard:
    def test_can_open_position_when_below_limit(self) -> None:
        guard = SimplePositionGuard(
            max_positions=3, max_position_value=Decimal("100000")
        )
        assert guard.can_open_position() is True

    def test_cannot_open_position_at_limit(self) -> None:
        guard = SimplePositionGuard(
            max_positions=1, max_position_value=Decimal("100000")
        )
        guard.register_position("RELIANCE", Decimal("10"), Decimal("1000"))
        assert guard.can_open_position() is False

    def test_validate_order_within_value_limit(self) -> None:
        guard = SimplePositionGuard(
            max_positions=5, max_position_value=Decimal("100000")
        )
        assert guard.validate_order("RELIANCE", Decimal("10"), Decimal("5000")) is True

    def test_validate_order_exceeds_value_limit(self) -> None:
        guard = SimplePositionGuard(max_positions=5, max_position_value=Decimal("1000"))
        assert guard.validate_order("RELIANCE", Decimal("10"), Decimal("5000")) is False

    def test_validate_order_duplicate_symbol_rejected(self) -> None:
        guard = SimplePositionGuard(
            max_positions=5, max_position_value=Decimal("100000")
        )
        guard.register_position("RELIANCE", Decimal("10"), Decimal("2500"))
        assert guard.validate_order("RELIANCE", Decimal("10"), Decimal("2500")) is False

    def test_register_position_increments_count(self) -> None:
        guard = SimplePositionGuard(
            max_positions=5, max_position_value=Decimal("100000")
        )
        guard.register_position("TCS", Decimal("5"), Decimal("3000"))
        assert guard._current_positions == 1
        assert "TCS" in guard._positions

    def test_register_position_duplicate_not_double_counted(self) -> None:
        guard = SimplePositionGuard(
            max_positions=5, max_position_value=Decimal("100000")
        )
        guard.register_position("TCS", Decimal("5"), Decimal("3000"))
        guard.register_position("TCS", Decimal("5"), Decimal("3000"))
        assert guard._current_positions == 1

    def test_boundary_max_positions_zero(self) -> None:
        guard = SimplePositionGuard(
            max_positions=0, max_position_value=Decimal("100000")
        )
        assert guard.can_open_position() is False

    def test_boundary_max_position_value_zero(self) -> None:
        guard = SimplePositionGuard(max_positions=5, max_position_value=Decimal("0"))
        assert guard.validate_order("RELIANCE", Decimal("1"), Decimal("1")) is False


class TestStrategyConfig:
    def test_frozen_dataclass(self) -> None:
        config = _make_config()
        with pytest.raises(AttributeError):
            config.strategy_id = "changed"  # type: ignore[misc]

    def test_default_enabled(self) -> None:
        config = StrategyConfig(
            strategy_id="s1",
            strategy_type="momentum",
            symbols=["X"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("100"),
            max_positions=1,
            max_position_value=Decimal("1000"),
        )
        assert config.enabled is True

    def test_disabled_config(self) -> None:
        config = _make_config(enabled=False)
        assert config.enabled is False


class TestStrategyState:
    def test_defaults(self) -> None:
        state = StrategyState(strategy_id="s1")
        assert state.active_positions == 0
        assert state.total_capital_used == Decimal("0")
        assert state.last_scan_time is None
        assert state.scan_count == 0
        assert state.trades_executed == 0
        assert state.errors == []


class TestStrategyScanResult:
    def test_fields(self) -> None:
        now = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        result = StrategyScanResult(
            strategy_id="s1",
            success=True,
            signals_generated=3,
            orders_submitted=1,
            scan_duration_seconds=0.5,
            errors=[],
            timestamp_utc=now,
        )
        assert result.success is True
        assert result.signals_generated == 3
        assert result.scan_duration_seconds == 0.5


class TestSharedDataProviderPool:
    def test_empty_providers_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            SharedDataProviderPool({})

    @pytest.mark.asyncio
    async def test_get_ohlcv_missing_exchange_raises_config_error(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        with pytest.raises(ConfigError, match="No provider configured"):
            await pool.get_ohlcv(Exchange.BSE, "RELIANCE", "1d")

    @pytest.mark.asyncio
    async def test_get_ohlcv_delegates_to_provider(self) -> None:
        bar = _make_bar()
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(return_value=[bar])
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        result = await pool.get_ohlcv(Exchange.NSE, "RELIANCE", "1d", limit=100)
        assert len(result) == 1

    def test_available_capacity(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        assert isinstance(pool.available_capacity, int)

    def test_concurrent_requests(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        assert isinstance(pool.concurrent_requests, int)


class TestStrategyRunnerValidation:
    def test_empty_configs_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        with pytest.raises(ValueError, match="At least one strategy"):
            StrategyRunner(pool, Decimal("100000"), [])

    def test_no_enabled_strategies_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        disabled = _make_config(enabled=False)
        with pytest.raises(ValueError, match="At least one strategy must be enabled"):
            StrategyRunner(pool, Decimal("100000"), [disabled])

    def test_allocation_exceeds_100_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        c1 = _make_config(strategy_id="s1", allocation_pct=Decimal("60"))
        c2 = _make_config(strategy_id="s2", allocation_pct=Decimal("50"))
        with pytest.raises(ValueError, match="exceeds 100%"):
            StrategyRunner(pool, Decimal("100000"), [c1, c2])

    def test_zero_allocation_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(allocation_pct=Decimal("0"))
        with pytest.raises(ValueError, match="allocation must be positive"):
            StrategyRunner(pool, Decimal("100000"), [config])

    def test_zero_max_positions_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(max_positions=0)
        with pytest.raises(ValueError, match="max_positions must be positive"):
            StrategyRunner(pool, Decimal("100000"), [config])

    def test_zero_max_position_value_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(max_position_value=Decimal("0"))
        with pytest.raises(ValueError, match="max_position_value must be positive"):
            StrategyRunner(pool, Decimal("100000"), [config])

    def test_unknown_strategy_type_raises_config_error(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(strategy_type="unknown_type")
        with pytest.raises(ConfigError, match="Unknown strategy type"):
            StrategyRunner(pool, Decimal("100000"), [config])

    def test_disabled_config_not_counted_in_allocation(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        c1 = _make_config(strategy_id="s1", allocation_pct=Decimal("100"))
        c2 = _make_config(
            strategy_id="s2", allocation_pct=Decimal("100"), enabled=False
        )
        runner = StrategyRunner(pool, Decimal("100000"), [c1, c2])
        assert "s1" in runner._strategies
        assert "s2" not in runner._strategies


class TestStrategyRunnerInit:
    def _make_runner(self) -> StrategyRunner:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        return StrategyRunner(pool, Decimal("100000"), [config])

    def test_strategies_initialized(self) -> None:
        runner = self._make_runner()
        assert "strat-1" in runner._strategies

    def test_position_guards_initialized(self) -> None:
        runner = self._make_runner()
        assert "strat-1" in runner._position_guards

    def test_strategy_states_initialized(self) -> None:
        runner = self._make_runner()
        state = runner.get_strategy_state("strat-1")
        assert state is not None
        assert state.strategy_id == "strat-1"

    def test_get_strategy_state_not_found_returns_none(self) -> None:
        runner = self._make_runner()
        assert runner.get_strategy_state("nonexistent") is None

    def test_get_all_strategy_states(self) -> None:
        runner = self._make_runner()
        states = runner.get_all_strategy_states()
        assert "strat-1" in states

    def test_get_pool_status(self) -> None:
        runner = self._make_runner()
        status = runner.get_pool_status()
        assert "available_capacity" in status
        assert "concurrent_requests" in status
        assert "total_strategies" in status
        assert "active_strategies" in status


class TestStrategyRunnerValidateAccess:
    def _make_runner(self) -> StrategyRunner:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        return StrategyRunner(pool, Decimal("100000"), [config])

    def test_unknown_strategy_raises_config_error(self) -> None:
        runner = self._make_runner()
        with pytest.raises(ConfigError, match="Strategy not found"):
            runner._validate_strategy_access("nonexistent")

    def test_disabled_strategy_raises_config_error(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(enabled=False)
        with pytest.raises(ValueError):
            StrategyRunner(pool, Decimal("100000"), [config])


class TestStrategyRunnerScanCycle:
    @pytest.mark.asyncio
    async def test_run_single_scan_cycle_unknown_strategy(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])
        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.run_single_scan_cycle("nonexistent")

    @pytest.mark.asyncio
    async def test_run_single_scan_cycle_with_mocked_provider(self) -> None:
        bar = _make_bar()
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(return_value=[bar])
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = None
        runner._strategies["strat-1"] = mock_strategy

        result = await runner.run_single_scan_cycle("strat-1", timeframe="1d")
        assert isinstance(result, StrategyScanResult)
        assert result.strategy_id == "strat-1"

    @pytest.mark.asyncio
    async def test_run_single_scan_cycle_exception_returns_failed(self) -> None:
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(side_effect=RuntimeError("data error"))
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        result = await runner.run_single_scan_cycle("strat-1", timeframe="1d")
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_run_single_scan_cycle_position_guard_blocks(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(max_positions=1, max_position_value=Decimal("100000"))
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        guard = runner._position_guards["strat-1"]
        guard.register_position("RELIANCE", Decimal("10"), Decimal("2500"))

        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = None
        runner._strategies["strat-1"] = mock_strategy

        result = await runner.run_single_scan_cycle("strat-1", timeframe="1d")
        assert isinstance(result, StrategyScanResult)

    @pytest.mark.asyncio
    async def test_run_single_scan_empty_bars(self) -> None:
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(return_value=[])
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        result = await runner.run_single_scan_cycle("strat-1", timeframe="1d")
        assert result.signals_generated == 0
        assert result.orders_submitted == 0


class TestStrategyRunnerSignalGeneration:
    @pytest.mark.asyncio
    async def test_signal_none_returns_zero(self) -> None:
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = None
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])
        runner._strategies["strat-1"] = mock_strategy

        bar = _make_bar()
        signals, orders = runner._evaluate_signal(
            mock_strategy,
            config,
            "RELIANCE",
            bar,
            runner._position_guards["strat-1"],
            runner._strategy_states["strat-1"],
        )
        assert signals == 0
        assert orders == 0

    @pytest.mark.asyncio
    async def test_signal_but_no_order(self) -> None:
        from iatb.core.enums import OrderSide
        from iatb.core.events import SignalEvent

        mock_signal = MagicMock(spec=SignalEvent)
        mock_signal.strategy_id = "strat-1"
        mock_signal.symbol = "RELIANCE"
        mock_signal.side = OrderSide.BUY

        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = mock_signal
        mock_strategy.on_signal.return_value = None

        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])
        runner._strategies["strat-1"] = mock_strategy

        bar = _make_bar()
        signals, orders = runner._evaluate_signal(
            mock_strategy,
            config,
            "RELIANCE",
            bar,
            runner._position_guards["strat-1"],
            runner._strategy_states["strat-1"],
        )
        assert signals == 1
        assert orders == 0


class TestStrategyRunnerProcessOrder:
    def test_process_order_valid(self) -> None:
        from iatb.core.enums import OrderSide
        from iatb.strategies.base import StrategyOrder

        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        guard = runner._position_guards["strat-1"]
        state = runner._strategy_states["strat-1"]
        bar = _make_bar()

        order = StrategyOrder(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("2500"),
        )

        result = runner._process_order(order, bar, guard, state)
        assert result == 1
        assert state.trades_executed == 1
        assert state.active_positions == 1

    def test_process_order_exceeds_value(self) -> None:
        from iatb.core.enums import OrderSide
        from iatb.strategies.base import StrategyOrder

        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config(max_position_value=Decimal("100"))
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        guard = runner._position_guards["strat-1"]
        state = runner._strategy_states["strat-1"]
        bar = _make_bar()

        order = StrategyOrder(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("2500"),
        )

        result = runner._process_order(order, bar, guard, state)
        assert result == 0
        assert state.trades_executed == 0

    def test_process_order_uses_latest_bar_close_when_price_none(self) -> None:
        from iatb.core.enums import OrderSide
        from iatb.strategies.base import StrategyOrder

        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        guard = runner._position_guards["strat-1"]
        state = runner._strategy_states["strat-1"]
        bar = _make_bar(close="100")

        order = StrategyOrder(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            price=None,
        )

        result = runner._process_order(order, bar, guard, state)
        assert result == 1


class TestStrategyRunnerAllStrategies:
    @pytest.mark.asyncio
    async def test_run_all_sequential(self) -> None:
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(return_value=[])
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        results = await runner.run_all_strategies(parallel=False)
        assert "strat-1" in results
        assert isinstance(results["strat-1"], StrategyScanResult)

    @pytest.mark.asyncio
    async def test_run_all_parallel(self) -> None:
        mock_provider = MagicMock()
        mock_provider.get_ohlcv = AsyncMock(return_value=[])
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        results = await runner.run_all_strategies(parallel=True)
        assert "strat-1" in results


class TestStrategyRunnerResetState:
    @pytest.mark.asyncio
    async def test_reset_existing_strategy(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        state = runner._strategy_states["strat-1"]
        state.trades_executed = 10

        await runner.reset_strategy_state("strat-1")
        state = runner._strategy_states["strat-1"]
        assert state.trades_executed == 0

    @pytest.mark.asyncio
    async def test_reset_nonexistent_strategy_raises(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.reset_strategy_state("nonexistent")


class TestStrategyRunnerStopAll:
    @pytest.mark.asyncio
    async def test_stop_all_clears_state(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        await runner.stop_all_strategies()
        assert len(runner._strategies) == 0
        assert len(runner._strategy_states) == 0
        assert len(runner._position_guards) == 0


class TestStrategyRunnerCreateScanResult:
    def test_create_scan_result_success(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        start = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        result = runner._create_scan_result(
            strategy_id="strat-1",
            start_time=start,
            signals_generated=5,
            orders_submitted=2,
            errors=[],
            success=True,
        )
        assert result.success is True
        assert result.strategy_id == "strat-1"

    def test_create_scan_result_failure(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        start = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        result = runner._create_scan_result(
            strategy_id="strat-1",
            start_time=start,
            signals_generated=0,
            orders_submitted=0,
            errors=["error1"],
            success=False,
        )
        assert result.success is False


class TestStrategyRunnerBuildFailedResult:
    def test_build_failed_result(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        start = datetime(2024, 6, 15, 10, 0, tzinfo=UTC)
        exc = RuntimeError("test failure")
        result = runner._build_failed_result("strat-1", start, exc)
        assert result.success is False
        assert "test failure" in result.errors[0]


class TestStrategyRunnerCreateStrategyContext:
    def test_create_strategy_context(self) -> None:
        mock_provider = MagicMock()
        pool = SharedDataProviderPool({Exchange.NSE: mock_provider})
        config = _make_config()
        runner = StrategyRunner(pool, Decimal("100000"), [config])

        ctx = runner._create_strategy_context(config, "RELIANCE")
        assert ctx.exchange == Exchange.NSE
        assert ctx.symbol == "RELIANCE"
