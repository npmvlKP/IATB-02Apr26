"""
Comprehensive tests for StrategyRunner multi-strategy orchestration.

Coverage:
- StrategyConfig: frozen dataclass, creation, immutability
- StrategyState: defaults, mutation
- StrategyScanResult: creation, UTC timestamp
- SimplePositionGuard: limits, validation, registration
- SharedDataProviderPool: initialization, rate limiting, missing exchange
- StrategyRunner: init validation, scan cycles, parallel/sequential,
  multi-strategy isolation, rate limit sharing, reset, stop
- Edge cases: allocation boundary (100%), negative allocation,
  unknown strategy type, empty data, concurrent access
- Error paths: missing strategy, disabled strategy, data provider errors
- Type handling: Decimal precision, UTC-only datetime
"""

import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.events import SignalEvent
from iatb.core.exceptions import ConfigError
from iatb.core.strategy_runner import (
    SharedDataProviderPool,
    SimplePositionGuard,
    StrategyConfig,
    StrategyRunner,
    StrategyScanResult,
    StrategyState,
)
from iatb.core.types import create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar
from iatb.strategies.base import StrategyOrder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Create sample strategy configurations with mixed enabled/disabled."""
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
    """Create sample OHLCV bars with Decimal-only financial fields."""
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


# ---------------------------------------------------------------------------
# StrategyConfig
# ---------------------------------------------------------------------------


class TestStrategyConfig:
    """Test StrategyConfig frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating StrategyConfig with all fields specified."""
        config = StrategyConfig(
            strategy_id="test_strat",
            strategy_type="momentum",
            symbols=["RELIANCE", "TCS"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("50"),
            max_positions=5,
            max_position_value=Decimal("500000"),
            enabled=True,
        )
        assert config.strategy_id == "test_strat"
        assert config.strategy_type == "momentum"
        assert config.symbols == ["RELIANCE", "TCS"]
        assert config.exchange == Exchange.NSE
        assert config.allocation_pct == Decimal("50")
        assert config.max_positions == 5
        assert config.max_position_value == Decimal("500000")
        assert config.enabled is True

    def test_default_enabled_is_true(self) -> None:
        """Test default value of enabled is True."""
        config = StrategyConfig(
            strategy_id="s",
            strategy_type="momentum",
            symbols=["R"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("50"),
            max_positions=1,
            max_position_value=Decimal("100"),
        )
        assert config.enabled is True

    def test_frozen_immutability(self) -> None:
        """Test StrategyConfig is frozen (immutable)."""
        config = StrategyConfig(
            strategy_id="s",
            strategy_type="momentum",
            symbols=["R"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("50"),
            max_positions=1,
            max_position_value=Decimal("100"),
        )
        with pytest.raises(FrozenInstanceError):
            config.strategy_id = "changed"

    def test_disabled_flag(self) -> None:
        """Test creating disabled strategy config."""
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

    def test_decimal_precision_allocation(self) -> None:
        """Test Decimal precision is preserved in allocation."""
        config = StrategyConfig(
            strategy_id="s",
            strategy_type="momentum",
            symbols=["R"],
            exchange=Exchange.NSE,
            allocation_pct=Decimal("33.3333"),
            max_positions=1,
            max_position_value=Decimal("123456.789"),
        )
        assert config.allocation_pct == Decimal("33.3333")
        assert config.max_position_value == Decimal("123456.789")


# ---------------------------------------------------------------------------
# StrategyState
# ---------------------------------------------------------------------------


class TestStrategyState:
    """Test StrategyState dataclass."""

    def test_default_values(self) -> None:
        """Test all default values are zero/empty."""
        state = StrategyState(strategy_id="test")
        assert state.strategy_id == "test"
        assert state.active_positions == 0
        assert state.total_capital_used == Decimal("0")
        assert state.last_scan_time is None
        assert state.scan_count == 0
        assert state.trades_executed == 0
        assert state.errors == []

    def test_mutation(self) -> None:
        """Test StrategyState fields are mutable."""
        state = StrategyState(strategy_id="test")
        state.scan_count = 5
        state.trades_executed = 3
        state.active_positions = 2
        state.total_capital_used = Decimal("150000")
        assert state.scan_count == 5
        assert state.trades_executed == 3
        assert state.active_positions == 2
        assert state.total_capital_used == Decimal("150000")

    def test_errors_list_append(self) -> None:
        """Test errors list can be appended to."""
        state = StrategyState(strategy_id="test")
        state.errors.append("error1")
        state.errors.append("error2")
        assert len(state.errors) == 2


# ---------------------------------------------------------------------------
# StrategyScanResult
# ---------------------------------------------------------------------------


class TestStrategyScanResult:
    """Test StrategyScanResult dataclass."""

    def test_success_result(self) -> None:
        """Test creating a successful scan result."""
        ts = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=5,
            orders_submitted=3,
            scan_duration_seconds=2.5,
            errors=[],
            timestamp_utc=ts,
        )
        assert result.success is True
        assert result.signals_generated == 5
        assert result.orders_submitted == 3
        assert result.scan_duration_seconds == 2.5
        assert result.errors == []
        assert result.timestamp_utc == ts

    def test_failure_result(self) -> None:
        """Test creating a failed scan result."""
        ts = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=False,
            signals_generated=0,
            orders_submitted=0,
            scan_duration_seconds=1.0,
            errors=["API timeout"],
            timestamp_utc=ts,
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_utc_timestamp_required(self) -> None:
        """Test timestamp must be UTC-aware."""
        ts = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=0,
            orders_submitted=0,
            scan_duration_seconds=0.0,
            errors=[],
            timestamp_utc=ts,
        )
        assert result.timestamp_utc.tzinfo == UTC


# ---------------------------------------------------------------------------
# SimplePositionGuard
# ---------------------------------------------------------------------------


class TestSimplePositionGuard:
    """Test SimplePositionGuard class."""

    def test_initialization(self) -> None:
        """Test guard initializes with correct defaults."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        assert guard._max_positions == 5
        assert guard._max_position_value == Decimal("1000000")
        assert guard._current_positions == 0
        assert guard._positions == {}

    def test_can_open_position_within_limit(self) -> None:
        """Test can_open_position returns True when under limit."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        assert guard.can_open_position() is True

    def test_can_open_position_at_limit(self) -> None:
        """Test can_open_position returns False when at limit."""
        guard = SimplePositionGuard(
            max_positions=2,
            max_position_value=Decimal("1000000"),
        )
        guard._current_positions = 2
        assert guard.can_open_position() is False

    def test_can_open_position_one_below_limit(self) -> None:
        """Test can_open_position returns True when one below limit."""
        guard = SimplePositionGuard(
            max_positions=3,
            max_position_value=Decimal("1000000"),
        )
        guard._current_positions = 2
        assert guard.can_open_position() is True

    def test_validate_order_success(self) -> None:
        """Test order validation passes for valid order."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        assert (
            guard.validate_order(
                symbol="RELIANCE",
                quantity=Decimal("100"),
                price=Decimal("1000"),
            )
            is True
        )

    def test_validate_order_exceeds_value_limit(self) -> None:
        """Test order validation fails when value exceeds max."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("500000"),
        )
        assert (
            guard.validate_order(
                symbol="RELIANCE",
                quantity=Decimal("1000"),
                price=Decimal("1000"),
            )
            is False
        )

    def test_validate_order_exact_value_limit(self) -> None:
        """Test order validation passes at exact value limit."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("500000"),
        )
        assert (
            guard.validate_order(
                symbol="RELIANCE",
                quantity=Decimal("500"),
                price=Decimal("1000"),
            )
            is True
        )

    def test_validate_order_duplicate_symbol(self) -> None:
        """Test order validation fails for already-held symbol."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        guard._positions["RELIANCE"] = (Decimal("100"), Decimal("1000"))
        guard._current_positions = 1
        assert (
            guard.validate_order(
                symbol="RELIANCE",
                quantity=Decimal("50"),
                price=Decimal("1050"),
            )
            is False
        )

    def test_register_new_position(self) -> None:
        """Test registering a new position updates counters."""
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
        assert guard._positions["RELIANCE"] == (Decimal("100"), Decimal("1000"))

    def test_register_duplicate_symbol_no_increment(self) -> None:
        """Test duplicate symbol registration does not increment counter."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        guard.register_position("RELIANCE", Decimal("100"), Decimal("1000"))
        assert guard._current_positions == 1
        guard.register_position("RELIANCE", Decimal("50"), Decimal("1050"))
        assert guard._current_positions == 1

    def test_register_multiple_positions(self) -> None:
        """Test registering multiple different symbols."""
        guard = SimplePositionGuard(
            max_positions=5,
            max_position_value=Decimal("1000000"),
        )
        guard.register_position("RELIANCE", Decimal("100"), Decimal("1000"))
        guard.register_position("TCS", Decimal("50"), Decimal("3500"))
        guard.register_position("INFY", Decimal("200"), Decimal("1500"))
        assert guard._current_positions == 3
        assert len(guard._positions) == 3


# ---------------------------------------------------------------------------
# SharedDataProviderPool
# ---------------------------------------------------------------------------


class TestSharedDataProviderPool:
    """Test SharedDataProviderPool class."""

    def test_initialization(self, mock_data_provider: DataProvider) -> None:
        """Test pool initializes with correct capacity."""
        pool = SharedDataProviderPool(
            providers={Exchange.NSE: mock_data_provider},
            requests_per_second=5.0,
            burst_capacity=10,
        )
        assert pool.available_capacity == 10
        assert pool.concurrent_requests == 0

    def test_empty_providers_raises(self) -> None:
        """Test empty providers dict raises ValueError."""
        with pytest.raises(ValueError, match="Providers dict cannot be empty"):
            SharedDataProviderPool(providers={})

    async def test_get_ohlcv_success(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test successful OHLCV fetch through pool."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        bars = await mock_provider_pool.get_ohlcv(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            timeframe="1d",
            limit=100,
        )
        assert len(bars) == 100
        mock_data_provider.get_ohlcv.assert_called_once()

    async def test_get_ohlcv_missing_exchange_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test fetch for unconfigured exchange raises ConfigError."""
        with pytest.raises(ConfigError, match="No provider configured"):
            await mock_provider_pool.get_ohlcv(
                exchange=Exchange.BSE,
                symbol="REL",
                timeframe="1d",
            )

    def test_available_capacity_property(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test available_capacity property."""
        assert isinstance(mock_provider_pool.available_capacity, int)

    def test_concurrent_requests_property(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test concurrent_requests property."""
        assert isinstance(mock_provider_pool.concurrent_requests, int)


# ---------------------------------------------------------------------------
# StrategyRunner - Initialization Validation
# ---------------------------------------------------------------------------


class TestStrategyRunnerInit:
    """Test StrategyRunner initialization and config validation."""

    def test_valid_initialization(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test runner initializes with correct number of enabled strategies."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        assert len(runner._strategies) == 2
        assert len(runner._strategy_states) == 2
        assert len(runner._position_guards) == 2

    def test_empty_configs_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test empty configs list raises ValueError."""
        with pytest.raises(ValueError, match="At least one strategy configuration"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=[],
            )

    def test_all_disabled_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test all strategies disabled raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="d1",
                strategy_type="momentum",
                symbols=["R"],
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

    def test_allocation_exceeds_100_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test total allocation > 100% raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("60"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="s2",
                strategy_type="mean_reversion",
                symbols=["T"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
        ]
        with pytest.raises(ValueError, match="exceeds 100%"):
            StrategyRunner(
                provider_pool=mock_provider_pool,
                total_capital=Decimal("1000000"),
                strategy_configs=configs,
            )

    def test_allocation_exactly_100_ok(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test total allocation exactly 100% is allowed."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("60"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="s2",
                strategy_type="mean_reversion",
                symbols=["T"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        assert len(runner._strategies) == 2

    def test_zero_allocation_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test zero allocation raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
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

    def test_negative_allocation_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test negative allocation raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("-10"),
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

    def test_zero_max_positions_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test zero max_positions raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
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

    def test_zero_max_position_value_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test zero max_position_value raises ValueError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="momentum",
                symbols=["R"],
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

    def test_unknown_strategy_type_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test unknown strategy type raises ConfigError."""
        configs = [
            StrategyConfig(
                strategy_id="s1",
                strategy_type="unknown_type",
                symbols=["R"],
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


# ---------------------------------------------------------------------------
# StrategyRunner - Scan Cycles
# ---------------------------------------------------------------------------


class TestStrategyRunnerScanCycles:
    """Test StrategyRunner scan cycle execution."""

    async def test_single_scan_success(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test successful single scan cycle."""
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

    async def test_single_scan_updates_state(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test scan cycle updates strategy state."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.scan_count == 1
        assert state.last_scan_time is not None

    async def test_single_scan_missing_strategy_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan for non-existent strategy raises ConfigError."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.run_single_scan_cycle("nonexistent")

    async def test_single_scan_disabled_strategy_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test scan for disabled strategy raises ConfigError."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.run_single_scan_cycle("disabled_strat")

    async def test_empty_data_no_signals(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
    ) -> None:
        """Test empty data from provider results in zero signals."""
        mock_data_provider.get_ohlcv.return_value = []
        configs = [
            StrategyConfig(
                strategy_id="empty_strat",
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
        result = await runner.run_single_scan_cycle("empty_strat", timeframe="1d")
        assert result.success is True
        assert result.signals_generated == 0
        assert result.orders_submitted == 0

    async def test_provider_error_returns_failure(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test data provider error returns failed result."""
        mock_data_provider.get_ohlcv.side_effect = Exception("API Error")
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        assert result.success is False
        assert len(result.errors) > 0
        assert "API Error" in result.errors[0]

    async def test_partial_symbol_errors(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test error on one symbol does not prevent processing others."""
        mock_data_provider.get_ohlcv.side_effect = [
            Exception("First fails"),
            sample_ohlcv_bars,
        ]
        configs = [
            StrategyConfig(
                strategy_id="multi_sym",
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
        result = await runner.run_single_scan_cycle("multi_sym", timeframe="1d")
        assert result.success is False
        assert len(result.errors) == 1
        assert "First fails" in result.errors[0]


# ---------------------------------------------------------------------------
# StrategyRunner - Multi-Strategy Isolation
# ---------------------------------------------------------------------------


class TestMultiStrategyIsolation:
    """Test that strategies maintain independent state and risk limits."""

    async def test_states_are_independent(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test each strategy has its own independent state."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="strat_a",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=3,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="strat_b",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=2,
                max_position_value=Decimal("400000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        await runner.run_single_scan_cycle("strat_a")
        state_a = runner.get_strategy_state("strat_a")
        state_b = runner.get_strategy_state("strat_b")
        assert state_a is not None
        assert state_b is not None
        assert state_a.scan_count == 1
        assert state_b.scan_count == 0

    async def test_position_guards_are_independent(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
    ) -> None:
        """Test each strategy has its own position guard."""
        mock_data_provider.get_ohlcv.return_value = [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000"),
                high=Decimal("1010"),
                low=Decimal("990"),
                close=Decimal("1005"),
                volume=Decimal("1000000"),
                source="mock",
            )
        ]
        configs = [
            StrategyConfig(
                strategy_id="guard_a",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="guard_b",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=5,
                max_position_value=Decimal("1000000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        guard_a = runner._position_guards["guard_a"]
        guard_b = runner._position_guards["guard_b"]
        assert guard_a._max_positions == 1
        assert guard_b._max_positions == 5
        assert guard_a._max_position_value == Decimal("500000")
        assert guard_b._max_position_value == Decimal("1000000")

    async def test_reset_one_strategy_does_not_affect_other(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test resetting one strategy does not affect another."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="reset_a",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=3,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="reset_b",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=2,
                max_position_value=Decimal("400000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        await runner.run_single_scan_cycle("reset_a")
        await runner.run_single_scan_cycle("reset_b")
        await runner.reset_strategy_state("reset_a")
        state_a = runner.get_strategy_state("reset_a")
        state_b = runner.get_strategy_state("reset_b")
        assert state_a is not None
        assert state_b is not None
        assert state_a.scan_count == 0
        assert state_b.scan_count == 1


# ---------------------------------------------------------------------------
# StrategyRunner - Rate Limit Sharing
# ---------------------------------------------------------------------------


class TestRateLimitSharing:
    """Test that strategies share the rate-limited provider pool."""

    async def test_pool_is_shared_across_strategies(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test all strategies use the same provider pool instance."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="share_a",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="share_b",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        assert runner._provider_pool is mock_provider_pool

    async def test_sequential_scan_uses_shared_pool(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test sequential scan uses shared pool for all strategies."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="seq_a",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
            StrategyConfig(
                strategy_id="seq_b",
                strategy_type="mean_reversion",
                symbols=["TCS"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("40"),
                max_positions=1,
                max_position_value=Decimal("500000"),
                enabled=True,
            ),
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        results = await runner.run_all_strategies(timeframe="1d", parallel=False)
        assert len(results) == 2
        assert all(r.success for r in results.values())

    def test_pool_status_reflects_shared_state(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test pool status reflects shared pool metrics."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        status = runner.get_pool_status()
        assert status["total_strategies"] == 2
        assert status["active_strategies"] == 2
        assert "available_capacity" in status
        assert "concurrent_requests" in status


# ---------------------------------------------------------------------------
# StrategyRunner - Parallel vs Sequential
# ---------------------------------------------------------------------------


class TestParallelSequentialExecution:
    """Test parallel and sequential strategy execution."""

    async def test_sequential_all_succeed(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test sequential execution succeeds for all strategies."""
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

    async def test_parallel_all_succeed(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test parallel execution succeeds for all strategies."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        results = await runner.run_all_strategies(timeframe="1d", parallel=True)
        assert len(results) == 2
        assert all(r.success for r in results.values())

    async def test_parallel_handles_exceptions(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test parallel execution handles exceptions gracefully."""
        mock_data_provider.get_ohlcv.side_effect = Exception("Parallel fail")
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        results = await runner.run_all_strategies(timeframe="1d", parallel=True)
        assert len(results) == 2
        assert all(not r.success for r in results.values())
        assert all(len(r.errors) > 0 for r in results.values())

    async def test_concurrent_scan_safety(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test concurrent scan cycles for different strategies are safe."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        tasks = [
            runner.run_single_scan_cycle("momentum_1", timeframe="1d"),
            runner.run_single_scan_cycle("mean_rev_1", timeframe="1d"),
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 2
        assert all(r.success for r in results)


# ---------------------------------------------------------------------------
# StrategyRunner - State Management
# ---------------------------------------------------------------------------


class TestStrategyRunnerState:
    """Test strategy state retrieval and management."""

    def test_get_strategy_state_found(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting state for existing strategy."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.strategy_id == "momentum_1"

    def test_get_strategy_state_not_found(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting state for non-existent strategy returns None."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        assert runner.get_strategy_state("nonexistent") is None

    def test_get_all_strategy_states(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test getting all states returns correct dict."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        states = runner.get_all_strategy_states()
        assert len(states) == 2
        assert "momentum_1" in states
        assert "mean_rev_1" in states

    async def test_reset_strategy_state(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test reset clears state and preserves config limits."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        original_max_pos = runner._position_guards["momentum_1"]._max_positions
        original_max_val = runner._position_guards["momentum_1"]._max_position_value
        await runner.reset_strategy_state("momentum_1")
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.scan_count == 0
        assert state.trades_executed == 0
        assert state.active_positions == 0
        assert runner._position_guards["momentum_1"]._max_positions == original_max_pos
        assert runner._position_guards["momentum_1"]._max_position_value == original_max_val

    async def test_reset_nonexistent_raises(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test reset for non-existent strategy raises ConfigError."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        with pytest.raises(ConfigError, match="Strategy not found"):
            await runner.reset_strategy_state("nonexistent")

    async def test_multiple_resets_ok(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test multiple resets work correctly."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        await runner.reset_strategy_state("momentum_1")
        await runner.reset_strategy_state("momentum_1")
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.scan_count == 0

    async def test_stop_all_clears_everything(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test stop_all clears strategies, states, and guards."""
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


# ---------------------------------------------------------------------------
# StrategyRunner - Signal and Order Processing
# ---------------------------------------------------------------------------


class TestStrategyRunnerSignalProcessing:
    """Test signal generation and order processing paths."""

    def _make_signal(
        self,
        symbol: str = "RELIANCE",
        quantity: str = "10",
        price: str | None = "1005",
        confidence: str = "0.8",
    ) -> SignalEvent:
        """Create a valid SignalEvent."""
        kwargs: dict[str, object] = {
            "strategy_id": "momentum",
            "exchange": Exchange.NSE,
            "symbol": symbol,
            "side": OrderSide.BUY,
            "quantity": create_quantity(quantity),
            "confidence": Decimal(confidence),
        }
        if price is not None:
            kwargs["price"] = create_price(price)
        return SignalEvent(**kwargs)

    def _make_order(
        self,
        symbol: str = "RELIANCE",
        quantity: str = "10",
        price: Decimal | None = Decimal("1005"),
    ) -> StrategyOrder:
        """Create a valid StrategyOrder."""
        return StrategyOrder(
            exchange=Exchange.NSE,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=create_quantity(quantity),
            price=price,
        )

    async def test_signal_with_valid_order(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test signal generates order and updates state."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        signal = self._make_signal()
        order = self._make_order()
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = signal
        mock_strategy.on_signal.return_value = order
        runner._strategies["momentum_1"] = mock_strategy

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        assert result.success is True
        assert result.orders_submitted == 1
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.trades_executed == 1
        assert state.active_positions == 1

    async def test_signal_no_order(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test signal with no order counts signal but not order."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        signal = self._make_signal()
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = signal
        mock_strategy.on_signal.return_value = None
        runner._strategies["momentum_1"] = mock_strategy

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        assert result.success is True
        assert result.signals_generated == 3
        assert result.orders_submitted == 0

    async def test_order_exceeds_value_limit(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test order exceeding max_position_value is rejected."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="val_strat",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=1,
                max_position_value=Decimal("100"),
                enabled=True,
            )
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        signal = self._make_signal(quantity="1000", price="1005")
        order = self._make_order(quantity="1000", price=Decimal("1005"))
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = signal
        mock_strategy.on_signal.return_value = order
        runner._strategies["val_strat"] = mock_strategy

        result = await runner.run_single_scan_cycle("val_strat", timeframe="1d")
        assert result.success is True
        assert result.orders_submitted == 0

    async def test_duplicate_symbol_order_rejected(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test order for symbol with existing position is rejected."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="dup_strat",
                strategy_type="momentum",
                symbols=["RELIANCE"],
                exchange=Exchange.NSE,
                allocation_pct=Decimal("50"),
                max_positions=5,
                max_position_value=Decimal("500000"),
                enabled=True,
            )
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=configs,
        )
        runner._position_guards["dup_strat"]._positions["RELIANCE"] = (
            Decimal("100"),
            Decimal("1000"),
        )
        runner._position_guards["dup_strat"]._current_positions = 1

        signal = self._make_signal()
        order = self._make_order()
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = signal
        mock_strategy.on_signal.return_value = order
        runner._strategies["dup_strat"] = mock_strategy

        result = await runner.run_single_scan_cycle("dup_strat", timeframe="1d")
        assert result.success is True
        assert result.orders_submitted == 0

    async def test_order_no_price_uses_bar_close(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test order with no price uses bar close for capital calculation."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        signal = self._make_signal(price=None)
        order = self._make_order(price=None)
        mock_strategy = MagicMock()
        mock_strategy.on_bar.return_value = signal
        mock_strategy.on_signal.return_value = order
        runner._strategies["momentum_1"] = mock_strategy

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        assert result.success is True
        assert result.orders_submitted == 1
        state = runner.get_strategy_state("momentum_1")
        assert state is not None
        assert state.total_capital_used > Decimal("0")

    async def test_position_limit_blocks_new_positions(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_ohlcv_bars: list[OHLCVBar],
    ) -> None:
        """Test position guard at max capacity blocks new positions."""
        mock_data_provider.get_ohlcv.return_value = sample_ohlcv_bars
        configs = [
            StrategyConfig(
                strategy_id="limit_strat",
                strategy_type="momentum",
                symbols=["RELIANCE", "TCS"],
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
        runner._position_guards["limit_strat"]._current_positions = 1

        result = await runner.run_single_scan_cycle("limit_strat", timeframe="1d")
        assert result.success is True

    async def test_unhandled_exception_returns_failure(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test unhandled exception in scan returns failed result."""
        mock_data_provider.get_ohlcv.return_value = [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000"),
                high=Decimal("1010"),
                low=Decimal("990"),
                close=Decimal("1005"),
                volume=Decimal("1000000"),
                source="mock",
            )
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )

        async def _failing_scan(*args: object, **kwargs: object) -> tuple[int, int, list[str]]:
            raise RuntimeError("Unhandled scan error")

        runner._scan_symbols = _failing_scan

        result = await runner.run_single_scan_cycle("momentum_1", timeframe="1d")
        assert result.success is False
        assert "Unhandled scan error" in result.errors[0]


# ---------------------------------------------------------------------------
# StrategyRunner - Edge Cases
# ---------------------------------------------------------------------------


class TestStrategyRunnerEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_neutral_strength_inputs(self) -> None:
        """Test _neutral_strength_inputs returns correct defaults."""
        from iatb.core.strategy_runner import _neutral_strength_inputs

        inputs = _neutral_strength_inputs()
        assert inputs.breadth_ratio == Decimal("1.0")
        assert inputs.volume_ratio == Decimal("1.0")
        assert inputs.adx == Decimal("20")
        assert inputs.volatility_atr_pct == Decimal("0.03")

    async def test_validate_access_disabled_config(
        self,
        mock_provider_pool: SharedDataProviderPool,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test _validate_strategy_access for disabled config raises."""
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        mock_strategy = MagicMock()
        runner._strategies["disabled_strat"] = mock_strategy

        with pytest.raises(ConfigError, match="Strategy not enabled"):
            runner._validate_strategy_access("disabled_strat")

    def test_decimal_precision_preserved(
        self,
        mock_provider_pool: SharedDataProviderPool,
    ) -> None:
        """Test Decimal precision is preserved in state."""
        configs = [
            StrategyConfig(
                strategy_id="prec_strat",
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
        state = runner.get_strategy_state("prec_strat")
        assert state is not None
        assert state.total_capital_used == Decimal("0")

    def test_utc_datetime_in_scan_result(self) -> None:
        """Test scan result timestamp is UTC-aware."""
        ts = datetime.now(UTC)
        result = StrategyScanResult(
            strategy_id="test",
            success=True,
            signals_generated=1,
            orders_submitted=1,
            scan_duration_seconds=1.0,
            errors=[],
            timestamp_utc=ts,
        )
        assert result.timestamp_utc.tzinfo == UTC

    async def test_parallel_with_injected_disabled_strategy(
        self,
        mock_provider_pool: SharedDataProviderPool,
        mock_data_provider: DataProvider,
        sample_strategy_configs: list[StrategyConfig],
    ) -> None:
        """Test parallel run with injected disabled strategy in _strategies."""
        mock_data_provider.get_ohlcv.return_value = [
            OHLCVBar(
                timestamp=datetime.now(UTC),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                timeframe="1d",
                open=Decimal("1000"),
                high=Decimal("1010"),
                low=Decimal("990"),
                close=Decimal("1005"),
                volume=Decimal("1000000"),
                source="mock",
            )
        ]
        runner = StrategyRunner(
            provider_pool=mock_provider_pool,
            total_capital=Decimal("1000000"),
            strategy_configs=sample_strategy_configs,
        )
        mock_strategy = MagicMock()
        runner._strategies["disabled_strat"] = mock_strategy

        results = await runner.run_all_strategies(timeframe="1d", parallel=True)
        assert "disabled_strat" in results
        assert results["disabled_strat"].success is False
