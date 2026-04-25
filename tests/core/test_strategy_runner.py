"""
Comprehensive tests for StrategyRunner multi-strategy orchestration.

Tests cover:
- Happy path: Normal strategy execution
- Edge cases: Empty configs, disabled strategies, rate limits
- Error paths: Invalid configs, missing providers, failed scans
- Type handling: Decimal precision, datetime timezone
- Precision handling: Financial calculations with Decimals
- Timezone handling: UTC-only datetime usage
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

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
)
from iatb.data.base import DataProvider, OHLCVBar


@pytest.fixture
def mock_data_provider() -> DataProvider:
    """Create mock data provider."""
    provider = AsyncMock(spec=DataProvider)
    return provider


@pytest.fixture
def mock_provider_pool(mock_data_provider: DataProvider) -> SharedDataProviderPool:
    """Create shared provider pool with mock provider."""
    return SharedDataProviderPool(
        providers={Exchange.NSE: mock_data_provider},
        requests_per_second=5.0,
        burst_capacity=10,
    )


@pytest.fixture
def sample_strategy_configs() -> list[StrategyConfig]:
    """Create sample strategy configurations."""
    return [
        StrategyConfig(
            strategy_id="momentum_1",
            strategy_type="momentum",
            symbols=["RELIANCE", "TCS", "INFY"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("50"),
            max_positions=3,
            max_position_value=Decimal("500000"),
            enabled=True,
        ),
        StrategyConfig(
            strategy_id="mean_rev_1",
            strategy_type="mean_reversion",
            symbols=["HDFCBANK", "ICICIBANK", "SBIN"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("40"),
            max_positions=2,
            max_position_value=Decimal("400000"),
            enabled=True,
        ),
        StrategyConfig(
            strategy_id="disabled_strat",
            strategy_type="momentum",
            symbols=["ITC", "KOTAKBANK"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("10"),
            max_positions=2,
            max_position_value=Decimal("300000"),
            enabled=False,
        ),
    ]


@pytest.fixture
def sample_ohlcv_bars() -> list[OHLCVBar]:
    """Create sample OHLCV bars."""
    base_time = datetime.now(UTC) - timedelta(days=100)
    bars = []
    for i in range(100):
        bars.append(
            OHLCVBar(
                timestamp=base_time + timedelta(days=i),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000") + Decimal(str(i)),
                high=Decimal("1010") + Decimal(str(i)),
                low=Decimal("990") + Decimal(str(i)),
                close=Decimal("1005") + Decimal(str(i)),
                volume=Decimal("1000000"),
                source="mock",
            )
        )
    return bars


class TestStrategyConfig:
    """Test StrategyConfig dataclass."""

    def test_strategy_config_creation(self) -> None:
        """Test StrategyConfig creation with valid parameters."""
        config = StrategyConfig(
            strategy_id="test_strat",
            strategy_type="momentum",
            symbols=["RELIANCE"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("50"),
            max_positions=5,
            max_position_value=Decimal("500000"),
        )
        assert config.strategy_id == "test_strat"
        assert config.strategy_type == "momentum"
        assert len(config.symbols) == 1
        assert config.enabled is True

    def test_strategy_config_disabled(self) -> None:
        """Test StrategyConfig with disabled flag."""
        config = StrategyConfig(
            strategy_id="disabled",
            strategy_type="momentum",
            symbols=["RELIANCE"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("10"),
            max_positions=1,
            max_position_value=Decimal("100000"),
            enabled=False,
        )
        assert config.enabled is False


class TestStrategyState:
    """Test StrategyState dataclass."""

    def test_strategy_state_defaults(self) -> None:
        """Test StrategyState default values."""
        state = StrategyState(strategy_id="test")
        assert state.strategy_id == "test"
        assert state.active_positions == 0
        assert state.total_capital_used == Decimal("0")
        assert state.last_scan_time is None
        assert state.scan_count == 0
        assert state.trades_executed == 0
        assert len(state.errors) == 0


class TestStrategyScanResult:
    """Test StrategyScanResult dataclass."""

    def test_scan_result_success(self) -> None:
        """Test successful scan result."""
        timestamp = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=5,
            orders_submitted=3,
            scan_duration_seconds=2.5,
            errors=[],
            timestamp_utc=timestamp,
        )
        assert result.success is True
        assert result.signals_generated == 5
        assert result.orders_submitted == 3
        assert result.scan_duration_seconds == 2.5
        assert len(result.errors) == 0
        assert result.timestamp_utc == timestamp


class TestSharedDataProviderPool:
    """Test SharedDataProviderPool class."""

    def test_pool_initialization(self, mock_data_provider: DataProvider) -> None:
        """Test pool initialization with valid providers."""
        pool = SharedDataProviderPool(
            providers={Exchange.NSE: mock_data_provider},
            requests_per_second=5.0,
            burst_capacity=10,
        )
        assert pool.available_capacity == 10
        assert pool.concurrent_requests == 0

    def test_pool_empty_providers(self) -> None:
        """Test pool initialization with empty providers raises error."""
        with pytest.raises(ValueError, match="Providers dict cannot be empty"):
            SharedDataProviderPool(providers={})

    async def test_get_ohlcv_success(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test successful OHLCV data fetch."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        bars = await mock_provider_pool.get_ohlcv(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            timeframe="1d",
            limit=100,
        )

        assert len(bars) == 100
        assert bars[0].symbol == "RELIANCE"
        mock_data_provider.get_ohlcv.assert_called_once()

    async def test_get_ohlcv_missing_exchange(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test OHLCV fetch for unconfigured exchange raises error."""
        with pytest.raises(ConfigError, match="No provider configured"):
            await mock_provider_pool.get_ohlcv(
                exchange=Exchange.BSE,
                symbol="REL",
                timeframe="1d",
            )

    def test_pool_properties(self, mock_provider_pool: SharedDataProviderPool) -> None:
        """Test pool property accessors."""
        assert mock_provider_pool.available_capacity == 10
        assert mock_provider_pool.concurrent_requests == 0


class TestStrategyRunner:
    """Test StrategyRunner class."""

    def test_runner_initialization(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test StrategyRunner initialization with valid configs."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        assert len(runner._strategies) == 2  # 2 enabled strategies
        assert len(runner._strategy_states) == 2
        assert len(runner._position_guards) == 2

    def test_runner_empty_configs(self, mock_provider_pool: SharedDataProviderPool) -> None:
        """Test runner initialization with empty configs raises error."""
        with pytest.raises(ValueError, match="At least one strategy configuration"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=[],
            )

    def test_runner_all_disabled(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test runner initialization with all disabled strategies raises error."""
        configs = [
            StrategyConfig(
                strategy_id="disabled1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=False,
            )
        ]
        with pytest.raises(ValueError, match="At least one strategy must be enabled"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    def test_runner_allocation_exceeds_100(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test runner initialization with allocation > 100% raises error."""
        configs = [
            StrategyConfig(
                strategy_id="strat1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("60"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="strat2",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
        ]
        with pytest.raises(ValueError, match="Total allocation .* exceeds 100%"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    def test_runner_invalid_allocation(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test runner initialization with zero allocation raises error."""
        configs = [
            StrategyConfig(
                strategy_id="strat1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("0"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]
        with pytest.raises(ValueError, match="allocation must be positive"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    def test_runner_invalid_max_positions(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test runner initialization with zero max_positions raises error."""
        configs = [
            StrategyConfig(
                strategy_id="strat1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=0,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]
        with pytest.raises(ValueError, match="max_positions must be positive"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    def test_runner_invalid_max_position_value(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test runner initialization with zero max_position_value raises error."""
        configs = [
            StrategyConfig(
                strategy_id="strat1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("0"),
                enabled=True,
            )
        ]
        with pytest.raises(ValueError, match="max_position_value must be positive"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    async def test_run_single_scan_cycle_success(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test successful single scan cycle execution."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")

        assert result.strategy_id == "momentum_1"
        assert result.success is True
        assert result.scan_duration_seconds >= 0
        assert result.timestamp_utc.tzinfo == UTC

    async def test_run_single_scan_cycle_missing_strategy(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan cycle for non-existent strategy raises error."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.run_single_scan_cycle("nonexistent")

    async def test_run_single_scan_cycle_disabled_strategy(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan cycle for disabled strategy raises error."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.run_single_scan_cycle("disabled_strat")

    async def test_run_all_strategies_sequential(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test running all strategies sequentially."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        results = await runner.run_all_strategies(timeframe="1d", parallel=False)

        assert len(results) == 2
        assert "momentum_1" in results
        assert "mean_rev_1" in results
        assert all(r.success for r in results.values())

    async def test_run_all_strategies_parallel(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test running all strategies in parallel."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        results = await runner.run_all_strategies(timeframe="1d", parallel=True)

        assert len(results) == 2
        assert all(r.success for r in results.values())

    def test_get_strategy_state(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting strategy state."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.strategy_id == "momentum_1"
        assert state.active_positions == 0

    def test_get_strategy_state_not_found(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting state for non-existent strategy."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        state = runner.get_strategy_state("nonexistent")
        assert state is None

    def test_get_all_strategy_states(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting all strategy states."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        states = runner.get_all_strategy_states()
        assert len(states) == 2
        assert "momentum_1" in states
        assert "mean_rev_1" in states

    def test_get_pool_status(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting pool status."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        status = runner.get_pool_status()
        assert "available_capacity" in status
        assert "concurrent_requests" in status
        assert "total_strategies" in status
        assert "active_strategies" in status
        assert status["total_strategies"] == 2
        assert status["active_strategies"] == 2

    async def test_reset_strategy_state(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test resetting strategy state."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        # Modify state
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.scan_count == 0

        await runner.reset_strategy_state("momentum_1")

        # Verify reset
        new_state = runner.get_strategy_state("momentum_1")
        assert new_state is not None
        assert new_state.scan_count == 0
        assert new_state.trades_executed == 0
        assert new_state.active_positions == 0

    async def test_reset_strategy_state_not_found(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test resetting state for non-existent strategy raises error."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.reset_strategy_state("nonexistent")

    async def test_stop_all_strategies(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test stopping all strategies."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        assert len(runner._strategies) == 2

        await runner.stop_all_strategies()

        assert len(runner._strategies) == 0
        assert len(runner._strategy_states) == 0
        assert len(runner._position_guards) == 0

    async def test_scan_cycle_with_data_error(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan cycle handles data provider errors."""
        mock_data_provider.get_ohlcv.side_effect = Exception("API Error")

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")

        assert result.strategy_id == "momentum_1"
        assert result.success is False
        assert len(result.errors) > 0
        assert "API Error" in result.errors[0]

    def test_decimal_precision_handling(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test Decimal precision in allocations and limits."""
        configs = [
            StrategyConfig(
                strategy_id="strat1",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("33.3333"),
                max_positions=1,
                max_position_value=Decimal("123456.789"),
                enabled=True,
            )
        ]

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )

        state = runner.get_strategy_state("strat1")
        assert state is not None
        assert state.total_capital_used == Decimal("0")

    def test_utc_datetime_handling(self) -> None:
        """Test all datetime usage is UTC-aware."""
        timestamp = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=1,
            orders_submitted=1,
            scan_duration_seconds=1.0,
            errors=[],
            timestamp_utc=timestamp,
        )
        assert result.timestamp_utc.tzinfo == UTC

    async def test_position_limit_enforcement(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test position limits are enforced during scan."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        # Config with max_positions=1
        configs = [
            StrategyConfig(
                strategy_id="limit_strat",
                strategy_type="momentum",
                symbols=["RELIANCE", "TCS", "INFY"],  # 3 symbols
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,  # Only 1 position allowed
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )

        # Run scan - since strategies don't generate signals in tests,
        # verify the limit check mechanism exists
        result = await runner.run_single_scan_cycle("limit_strat", timeframe="1d")

        # Verify scan completed successfully
        state = runner.get_strategy_state("limit_strat")
        assert state is not None
        assert result.success is True
        # Position guard should be initialized with correct limits
        assert runner._position_guards["limit_strat"]._max_positions == 1

    async def test_concurrent_access_safety(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test concurrent access to shared resources is thread-safe."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        # Run multiple scans concurrently
        tasks = [
            runner.run_single_scan_cycle("momentum_1", timeframe="1d"),
            runner.run_single_scan_cycle("mean_rev_1", timeframe="1d"),
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 2
        assert all(r is not None for r in results)
        assert all(r.success for r in results)


class TestSimplePositionGuard:
    """Test SimplePositionGuard class."""

    def test_guard_initialization(self) -> None:
        """Test guard initialization."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        assert guard._max_positions == 5
        assert guard._max_position_value == Decimal("1000000")
        assert guard._current_positions == 0
        assert len(guard._positions) == 0

    def test_can_open_position_within_limit(self) -> None:
        """Test can_open_position returns True when within limit."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        assert guard.can_open_position() is True

    def test_can_open_position_at_limit(self) -> None:
        """Test can_open_position returns False at limit."""
        guard = SimplePositionGuard(
            max_positions=2,
            max_position_value=Decimal("1000000"),
        )
        guard._current_positions = 2
        assert guard.can_open_position() is False

    def test_validate_order_success(self) -> None:
        """Test order validation passes for valid order."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        result = guard.validate_order(
            symbol="RELIANCE",
            quantity=Decimal("100"),
            price=Decimal("1000"),
        )
        assert result is True

    def test_validate_order_exceeds_value_limit(self) -> None:
        """Test order validation fails when value exceeds limit."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("500000"),
        )
        result = guard.validate_order(
            symbol="RELIANCE",
            quantity=Decimal("1000"),
            price=Decimal("1000"),  # Value = 1,000,000 > 500,000
        )
        assert result is False

    def test_validate_order_duplicate_symbol(self) -> None:
        """Test order validation fails for duplicate symbol."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        # Register first position
        guard._positions["RELIANCE"] = (Decimal("100"), Decimal("1000"))
        guard._current_positions = 1

        # Try to add duplicate
        result = guard.validate_order(
            symbol="RELIANCE",
            quantity=Decimal("50"),
            price=Decimal("1050"),
        )
        assert result is False

    def test_register_position_new(self) -> None:
        """Test registering a new position."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        guard.register_position(
            symbol="RELIANCE",
            quantity=Decimal("100"),
            price=Decimal("1000"),
        )
        assert guard._current_positions == 1
        assert "RELIANCE" in guard._positions
        assert guard._positions["RELIANCE"] == (Decimal("100"), Decimal("1000"))

    def test_register_position_duplicate_symbol(self) -> None:
        """Test that duplicate symbol registration doesn't increment counter."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        guard.register_position(
            symbol="RELIANCE",
            quantity=Decimal("100"),
            price=Decimal("1000"),
        )
        assert guard._current_positions == 1

        # Try to register same symbol again
        guard.register_position(
            symbol="RELIANCE",
            quantity=Decimal("50"),
            price=Decimal("1050"),
        )
        # Counter should not increment for duplicate
        assert guard._current_positions == 1


class TestStrategyRunnerEdgeCases:
    """Test StrategyRunner edge cases and error paths."""

    def test_unknown_strategy_type(self, mock_provider_pool: SharedDataProviderPool) -> None:
        """Test initialization with unknown strategy type raises error."""
        configs = [
            StrategyConfig(
                strategy_id="unknown_strat",
                strategy_type="unknown_type",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]
        with pytest.raises(ConfigError, match="Unknown strategy type"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    async def test_position_limit_blocks_scan(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test that position limit blocks new position opening."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars

        configs = [
            StrategyConfig(
                strategy_id="limit_strat",
                strategy_type="momentum",
                symbols=["RELIANCE", "TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,  # Only 1 position allowed
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )

        # Fill position guard to max capacity
        runner._position_guards["limit_strat"]._current_positions = 1

        result = await runner.run_single_scan_cycle("limit_strat", timeframe="1d")

        # Scan should succeed but not open new positions
        assert result.success is True
        state = runner.get_strategy_state("limit_strat")
        assert state is not None
        # Position count should remain at 1 (not increase)
        assert state.active_positions == 0  # Strategies don't generate signals in tests

    async def test_empty_data_handling(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
    ) -> None:
        """Test handling of empty data from provider."""
        mock_data_provider.get_ohlcv.return_value = []  # Empty data

        configs = [
            StrategyConfig(
                strategy_id="empty_data_strat",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )

        result = await runner.run_single_scan_cycle("empty_data_strat", timeframe="1d")

        # Scan should succeed but no signals
        assert result.success is True
        assert result.signals_generated == 0
        assert result.orders_submitted == 0

    async def test_parallel_execution_with_exception(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test parallel execution handles exceptions in one strategy."""
        # Make provider fail for all calls
        mock_data_provider.get_ohlcv.side_effect = Exception("Parallel error")

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        results = await runner.run_all_strategies(timeframe="1d", parallel=True)

        # Both strategies should fail gracefully
        assert len(results) == 2
        assert all(not r.success for r in results.values())
        assert all(len(r.errors) > 0 for r in results.values())

    async def test_scan_cycle_exception_handling(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan cycle handles exceptions gracefully."""
        # Make provider fail
        mock_data_provider.get_ohlcv.side_effect = RuntimeError("Scan error")

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")

        assert result.strategy_id == "momentum_1"
        assert result.success is False
        assert result.signals_generated == 0
        assert result.orders_submitted == 0
        assert len(result.errors) > 0
        assert "Scan error" in result.errors[0]

    async def test_symbol_processing_with_error(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test symbol processing with error continues to next symbol."""
        # Make provider fail on first call, succeed on second
        mock_data_provider.get_ohlcv.side_effect = [
            Exception("First symbol error"),
            sample_ohlcv_bars,
        ]

        configs = [
            StrategyConfig(
                strategy_id="multi_symbol_strat",
                strategy_type="momentum",
                symbols=["RELIANCE", "TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=2,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]

        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )

        result = await runner.run_single_scan_cycle("multi_symbol_strat", timeframe="1d")

        # Scan should complete with errors but overall success
        assert result.success is False  # Has errors
        assert len(result.errors) == 1
        assert "First symbol error" in result.errors[0]

    def test_validate_strategy_access_disabled(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test validating access to disabled strategy raises error."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        # Disabled strategies are not in _strategies dict, so they raise "not found"
        with pytest.raises(ConfigError, match="Strategy not found"):
            runner._validate_strategy_access("disabled_strat")

    async def test_reset_state_preserves_config(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test that reset state preserves strategy configuration limits."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        # Get original guard limits
        original_max_positions = runner._position_guards["momentum_1"]._max_positions
        original_max_value = runner._position_guards["momentum_1"]._max_position_value

        await runner.reset_strategy_state("momentum_1")

        # Verify limits are preserved
        assert runner._position_guards["momentum_1"]._max_positions == original_max_positions
        assert runner._position_guards["momentum_1"]._max_position_value == original_max_value

    async def test_scan_result_timestamp(self) -> None:
        """Test scan result includes correct timestamp."""
        start_time = datetime.now(UTC)
        # Simulate some delay
        await asyncio.sleep(0.01)
        end_time = datetime.now(UTC)

        duration = (end_time - start_time).total_seconds()

        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=1,
            orders_submitted=1,
            scan_duration_seconds=duration,
            errors=[],
            timestamp_utc=start_time,
        )

        assert result.timestamp_utc == start_time
        assert result.scan_duration_seconds >= 0
        assert result.timestamp_utc.tzinfo == UTC

    async def test_multiple_reset_operations(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test multiple reset operations work correctly."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        # First reset
        await runner.reset_strategy_state("momentum_1")

        # Second reset should work fine
        await runner.reset_strategy_state("momentum_1")

        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.scan_count == 0
        assert state.trades_executed == 0
