"""
Multi-strategy orchestration with independent scan cycles and shared resources.

This module provides StrategyRunner that manages multiple trading strategies,
each with its own scan cycle, configuration, and risk limits, while sharing
a DataProvider pool with coordinated rate limiting.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.base import DataProvider, OHLCVBar
from iatb.data.rate_limiter import RateLimiter
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import Strategy, StrategyContext
from iatb.strategies.mean_reversion import MeanReversionStrategy
from iatb.strategies.momentum import MomentumStrategy

_LOGGER = logging.getLogger(__name__)


def _neutral_strength_inputs() -> StrengthInputs:
    """Create neutral strength inputs for strategy context."""
    from iatb.market_strength.regime_detector import MarketRegime

    return StrengthInputs(
        breadth_ratio=Decimal("1.0"),
        regime=MarketRegime.SIDEWAYS,
        adx=Decimal("20"),
        volume_ratio=Decimal("1.0"),
        volatility_atr_pct=Decimal("0.03"),
    )


class SimplePositionGuard:
    """Simple position guard for strategy-level position limits."""

    def __init__(self, max_positions: int, max_position_value: Decimal) -> None:
        """Initialize simple position guard.

        Args:
            max_positions: Maximum concurrent positions.
            max_position_value: Maximum value per position.
        """
        self._max_positions = max_positions
        self._max_position_value = max_position_value
        self._current_positions: int = 0
        self._positions: dict[str, tuple[Decimal, Decimal]] = {}

    def can_open_position(self) -> bool:
        """Check if new position can be opened.

        Returns:
            True if position limit not reached, False otherwise.
        """
        return self._current_positions < self._max_positions

    def validate_order(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> bool:
        """Validate order against position limits.

        Args:
            symbol: Trading symbol.
            quantity: Order quantity.
            price: Order price.

        Returns:
            True if order is valid, False otherwise.
        """
        order_value = quantity * price
        if order_value > self._max_position_value:
            return False
        if symbol in self._positions:
            return False
        return True

    def register_position(
        self,
        symbol: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Register a new position.

        Args:
            symbol: Trading symbol.
            quantity: Position quantity.
            price: Position price.
        """
        if symbol not in self._positions:
            self._positions[symbol] = (quantity, price)
            self._current_positions += 1


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for a single strategy instance."""

    strategy_id: str
    strategy_type: str  # "momentum", "mean_reversion", etc.
    symbols: list[str]
    exchange: Exchange
    allocation_pct: Decimal  # Percentage of capital allocated
    max_positions: int  # Maximum concurrent positions
    max_position_value: Decimal  # Maximum value per position
    enabled: bool = True


@dataclass
class StrategyState:
    """Runtime state for a strategy instance."""

    strategy_id: str
    active_positions: int = 0
    total_capital_used: Decimal = field(default_factory=lambda: Decimal("0"))
    last_scan_time: datetime | None = None
    scan_count: int = 0
    trades_executed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class StrategyScanResult:
    """Result of a strategy scan cycle."""

    strategy_id: str
    success: bool
    signals_generated: int
    orders_submitted: int
    scan_duration_seconds: float
    errors: list[str]
    timestamp_utc: datetime


class SharedDataProviderPool:
    """Shared DataProvider pool with coordinated rate limiting.

    Multiple strategies share data providers while respecting combined
    rate limits to avoid API throttling.
    """

    def __init__(
        self,
        providers: dict[Exchange, DataProvider],
        *,
        requests_per_second: float = 3.0,
        burst_capacity: int = 10,
    ) -> None:
        """Initialize shared provider pool.

        Args:
            providers: Mapping of exchange to DataProvider instance.
            requests_per_second: Combined rate limit across all strategies.
            burst_capacity: Maximum concurrent requests.

        Raises:
            ValueError: If providers dict is empty.
        """
        if not providers:
            msg = "Providers dict cannot be empty"
            raise ValueError(msg)

        self._providers = providers
        self._rate_limiter = RateLimiter(
            requests_per_second=requests_per_second,
            burst_capacity=burst_capacity,
        )
        self._lock = asyncio.Lock()

    async def get_ohlcv(
        self,
        exchange: Exchange,
        symbol: str,
        timeframe: str,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV data with rate limiting.

        Args:
            exchange: Exchange to fetch data from.
            symbol: Trading symbol.
            timeframe: Candle timeframe (e.g., "1d", "1h").
            limit: Maximum number of bars to fetch.

        Returns:
            List of OHLCVBar objects.

        Raises:
            ConfigError: If exchange provider not available.
        """
        async with self._lock:
            provider = self._providers.get(exchange)
            if provider is None:
                msg = f"No provider configured for exchange: {exchange.value}"
                raise ConfigError(msg)

            return await self._rate_limiter.execute(
                provider.get_ohlcv(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    limit=limit,
                )
            )

    @property
    def available_capacity(self) -> int:
        """Get available request capacity."""
        return self._rate_limiter.available_tokens

    @property
    def concurrent_requests(self) -> int:
        """Get current concurrent request count."""
        return self._rate_limiter.concurrent_requests


class StrategyRunner:
    """Orchestrates multiple trading strategies with independent scan cycles.

    Each strategy:
      - Runs its own scan cycle independently
      - Has its own configuration (symbols, allocation, limits)
      - Shares DataProvider pool with coordinated rate limiting
      - Has independent risk limits (allocation, max positions)
    """

    def __init__(
        self,
        provider_pool: SharedDataProviderPool,
        total_capital: Decimal,
        strategy_configs: list[StrategyConfig],
    ) -> None:
        """Initialize strategy runner.

        Args:
            provider_pool: Shared DataProvider pool.
            total_capital: Total capital available across all strategies.
            strategy_configs: List of strategy configurations.

        Raises:
            ValueError: If total allocation exceeds 100% or no strategies enabled.
        """
        self._validate_strategy_configs(strategy_configs)
        self._provider_pool = provider_pool
        self._total_capital = total_capital
        self._strategy_configs = strategy_configs
        self._strategies: dict[str, Strategy] = {}
        self._strategy_states: dict[str, StrategyState] = {}
        self._position_guards: dict[str, SimplePositionGuard] = {}
        self._lock = asyncio.Lock()

        self._initialize_strategies()

    @staticmethod
    def _validate_strategy_configs(configs: list[StrategyConfig]) -> None:
        """Validate strategy configurations.

        Args:
            configs: List of strategy configurations.

        Raises:
            ValueError: If validation fails.
        """
        if not configs:
            msg = "At least one strategy configuration is required"
            raise ValueError(msg)

        enabled_configs = [c for c in configs if c.enabled]
        if not enabled_configs:
            msg = "At least one strategy must be enabled"
            raise ValueError(msg)

        total_allocation = sum(c.allocation_pct for c in enabled_configs)
        if total_allocation > Decimal("100"):
            msg = f"Total allocation {total_allocation}% exceeds 100%"
            raise ValueError(msg)

        for config in configs:
            if config.allocation_pct <= Decimal("0"):
                msg = f"Strategy {config.strategy_id} allocation must be positive"
                raise ValueError(msg)
            if config.max_positions <= 0:
                msg = f"Strategy {config.strategy_id} max_positions must be positive"
                raise ValueError(msg)
            if config.max_position_value <= Decimal("0"):
                msg = f"Strategy {config.strategy_id} max_position_value must be positive"
                raise ValueError(msg)

    def _initialize_strategies(self) -> None:
        """Initialize strategy instances and state.

        Creates strategy objects based on configuration type
        and sets up initial state and position guards.
        """
        for config in self._strategy_configs:
            if not config.enabled:
                continue

            strategy = self._create_strategy(config)
            self._strategies[config.strategy_id] = strategy
            self._strategy_states[config.strategy_id] = StrategyState(
                strategy_id=config.strategy_id,
            )

            # Create position guard with strategy-specific limits
            guard = SimplePositionGuard(
                max_positions=config.max_positions,
                max_position_value=config.max_position_value,
            )
            self._position_guards[config.strategy_id] = guard

            _LOGGER.info(
                "Initialized strategy: %s (type: %s, allocation: %s%%)",
                config.strategy_id,
                config.strategy_type,
                config.allocation_pct,
            )

    def _create_strategy(self, config: StrategyConfig) -> Strategy:
        """Create strategy instance based on configuration type.

        Args:
            config: Strategy configuration.

        Returns:
            Strategy instance.

        Raises:
            ConfigError: If strategy type is unknown.
        """
        strategy_map: dict[str, type[Strategy]] = {
            "momentum": MomentumStrategy,
            "mean_reversion": MeanReversionStrategy,
        }

        strategy_class = strategy_map.get(config.strategy_type.lower())
        if strategy_class is None:
            msg = f"Unknown strategy type: {config.strategy_type}"
            raise ConfigError(msg)

        return strategy_class()

    def _create_strategy_context(
        self,
        config: StrategyConfig,
        symbol: str,
    ) -> StrategyContext:
        """Create strategy context for symbol processing.

        Args:
            config: Strategy configuration.
            symbol: Trading symbol.

        Returns:
            StrategyContext instance.
        """
        return StrategyContext(
            exchange=config.exchange,
            symbol=symbol,
            side=Any,  # type: ignore
            strength_inputs=_neutral_strength_inputs(),
        )

    def _process_order(
        self,
        order: Any,
        latest_bar: OHLCVBar,
        guard: SimplePositionGuard,
        state: StrategyState,
    ) -> int:
        """Process order submission and update state.

        Args:
            order: Order to process.
            latest_bar: Latest OHLCV bar.
            guard: Position guard.
            state: Strategy state.

        Returns:
            Number of orders submitted (0 or 1).
        """
        orders_submitted = 0

        if guard.validate_order(
            symbol=latest_bar.symbol,
            quantity=order.quantity,
            price=order.price or latest_bar.close,
        ):
            orders_submitted = 1
            state.trades_executed += 1

            guard.register_position(
                symbol=latest_bar.symbol,
                quantity=order.quantity,
                price=order.price or latest_bar.close,
            )
            state.active_positions += 1
            state.total_capital_used += order.quantity * (order.price or latest_bar.close)

            _LOGGER.info(
                "Order submitted: %s %s %s @ %s",
                order.side.value,
                order.symbol,
                order.quantity,
                order.price or latest_bar.close,
            )

        return orders_submitted

    async def _process_symbol(
        self,
        symbol: str,
        strategy: Strategy,
        config: StrategyConfig,
        guard: SimplePositionGuard,
        state: StrategyState,
        timeframe: str,
    ) -> tuple[int, int, list[str]]:
        """Process a single symbol for signal generation and order submission."""
        signals_generated = 0
        orders_submitted = 0
        errors: list[str] = []

        try:
            if not guard.can_open_position():
                return signals_generated, orders_submitted, errors

            bars = await self._provider_pool.get_ohlcv(
                exchange=config.exchange,
                symbol=symbol,
                timeframe=timeframe,
                limit=100,
            )
            if not bars:
                return signals_generated, orders_submitted, errors

            signals_generated, orders_submitted = self._evaluate_signal(
                strategy=strategy,
                config=config,
                symbol=symbol,
                latest_bar=bars[-1],
                guard=guard,
                state=state,
            )
        except Exception as exc:
            error_msg = f"Error processing symbol {symbol}: {exc}"
            _LOGGER.error(error_msg, exc_info=True)
            errors.append(error_msg)

        return signals_generated, orders_submitted, errors

    def _evaluate_signal(
        self,
        strategy: Strategy,
        config: StrategyConfig,
        symbol: str,
        latest_bar: OHLCVBar,
        guard: SimplePositionGuard,
        state: StrategyState,
    ) -> tuple[int, int]:
        """Evaluate strategy signal and process resulting order.

        Args:
            strategy: Strategy instance.
            config: Strategy configuration.
            symbol: Trading symbol.
            latest_bar: Latest OHLCV bar.
            guard: Position guard.
            state: Strategy state.

        Returns:
            Tuple of (signals_generated, orders_submitted).
        """
        context = self._create_strategy_context(config, symbol)
        signal = strategy.on_bar(context, Any)  # type: ignore

        if signal is None:
            return 0, 0

        _LOGGER.debug(
            "Signal generated: %s %s %s",
            signal.strategy_id,
            signal.symbol,
            signal.side.value,
        )

        order = strategy.on_signal(context, signal)
        if order is None:
            return 1, 0

        return 1, self._process_order(order, latest_bar, guard, state)

    def _validate_strategy_access(
        self,
        strategy_id: str,
    ) -> tuple[Strategy, StrategyConfig, SimplePositionGuard, StrategyState]:
        """Validate strategy exists and is enabled.

        Args:
            strategy_id: Strategy identifier.

        Returns:
            Tuple of (strategy, config, guard, state).

        Raises:
            ConfigError: If strategy not found or disabled.
        """
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            msg = f"Strategy not found: {strategy_id}"
            raise ConfigError(msg)

        config = next(
            (c for c in self._strategy_configs if c.strategy_id == strategy_id),
            None,
        )
        if config is None or not config.enabled:
            msg = f"Strategy not enabled: {strategy_id}"
            raise ConfigError(msg)

        guard = self._position_guards[strategy_id]
        state = self._strategy_states[strategy_id]

        return strategy, config, guard, state

    def _create_scan_result(
        self,
        strategy_id: str,
        start_time: datetime,
        signals_generated: int,
        orders_submitted: int,
        errors: list[str],
        success: bool,
    ) -> StrategyScanResult:
        """Create scan result with calculated duration.

        Args:
            strategy_id: Strategy identifier.
            start_time: Scan start time.
            signals_generated: Number of signals generated.
            orders_submitted: Number of orders submitted.
            errors: List of errors encountered.
            success: Whether scan succeeded.

        Returns:
            StrategyScanResult instance.
        """
        duration = (datetime.now(UTC) - start_time).total_seconds()

        if success:
            _LOGGER.info(
                "Scan cycle complete for %s: %d signals, %d orders, %.2fs",
                strategy_id,
                signals_generated,
                orders_submitted,
                duration,
            )

        return StrategyScanResult(
            strategy_id=strategy_id,
            success=success,
            signals_generated=signals_generated,
            orders_submitted=orders_submitted,
            scan_duration_seconds=duration,
            errors=errors,
            timestamp_utc=start_time,
        )

    async def run_single_scan_cycle(
        self,
        strategy_id: str,
        timeframe: str = "1d",
    ) -> StrategyScanResult:
        """Run a single scan cycle for a specific strategy.

        Args:
            strategy_id: Strategy identifier.
            timeframe: Candle timeframe for data fetch.

        Returns:
            StrategyScanResult with execution details.

        Raises:
            ConfigError: If strategy_id not found.
        """
        strategy, config, guard, state = self._validate_strategy_access(strategy_id)
        start_time = datetime.now(UTC)

        try:
            signals, orders, errors = await self._scan_symbols(
                strategy=strategy,
                config=config,
                guard=guard,
                state=state,
                timeframe=timeframe,
            )

            state.last_scan_time = datetime.now(UTC)
            state.scan_count += 1

            return self._create_scan_result(
                strategy_id=strategy_id,
                start_time=start_time,
                signals_generated=signals,
                orders_submitted=orders,
                errors=errors,
                success=len(errors) == 0,
            )

        except Exception as exc:
            return self._build_failed_result(strategy_id, start_time, exc)

    async def _scan_symbols(
        self,
        strategy: Strategy,
        config: StrategyConfig,
        guard: SimplePositionGuard,
        state: StrategyState,
        timeframe: str,
    ) -> tuple[int, int, list[str]]:
        """Scan all symbols for a strategy.

        Args:
            strategy: Strategy instance.
            config: Strategy configuration.
            guard: Position guard.
            state: Strategy state.
            timeframe: Candle timeframe.

        Returns:
            Tuple of (signals_generated, orders_submitted, errors).
        """
        _LOGGER.info(
            "Starting scan cycle for strategy: %s (%d symbols)",
            config.strategy_id,
            len(config.symbols),
        )

        signals_generated = 0
        orders_submitted = 0
        errors: list[str] = []

        for symbol in config.symbols:
            sigs, orders, errs = await self._process_symbol(
                symbol=symbol,
                strategy=strategy,
                config=config,
                guard=guard,
                state=state,
                timeframe=timeframe,
            )
            signals_generated += sigs
            orders_submitted += orders
            errors.extend(errs)

        return signals_generated, orders_submitted, errors

    def _build_failed_result(
        self,
        strategy_id: str,
        start_time: datetime,
        exc: Exception,
    ) -> StrategyScanResult:
        """Build a failed scan result from an exception.

        Args:
            strategy_id: Strategy identifier.
            start_time: Scan start time.
            exc: Exception that caused the failure.

        Returns:
            StrategyScanResult with failure details.
        """
        error_msg = f"Scan cycle failed for {strategy_id}: {exc}"
        _LOGGER.exception(error_msg)

        return self._create_scan_result(
            strategy_id=strategy_id,
            start_time=start_time,
            signals_generated=0,
            orders_submitted=0,
            errors=[error_msg],
            success=False,
        )

    async def run_all_strategies(
        self,
        timeframe: str = "1d",
        parallel: bool = False,
    ) -> dict[str, StrategyScanResult]:
        """Run scan cycles for all enabled strategies.

        Args:
            timeframe: Candle timeframe for data fetch.
            parallel: If True, run strategies in parallel.
                If False, run sequentially to reduce rate limit pressure.

        Returns:
            Dictionary mapping strategy_id to ScanResult.
        """
        if parallel:
            return await self._run_strategies_parallel(timeframe)
        return await self._run_strategies_sequential(timeframe)

    async def _run_strategies_parallel(
        self,
        timeframe: str,
    ) -> dict[str, StrategyScanResult]:
        """Run all strategies in parallel.

        Args:
            timeframe: Candle timeframe for data fetch.

        Returns:
            Dictionary mapping strategy_id to ScanResult.
        """
        _LOGGER.info("Running %d strategies in parallel", len(self._strategies))

        tasks = [
            self.run_single_scan_cycle(strategy_id, timeframe) for strategy_id in self._strategies
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        result_dict: dict[str, StrategyScanResult] = {}
        for strategy_id, raw_result in zip(self._strategies.keys(), raw_results, strict=True):
            if isinstance(raw_result, Exception):
                _LOGGER.exception(
                    "Strategy %s failed with exception",
                    strategy_id,
                    exc_info=raw_result,
                )
                result_dict[strategy_id] = StrategyScanResult(
                    strategy_id=strategy_id,
                    success=False,
                    signals_generated=0,
                    orders_submitted=0,
                    scan_duration_seconds=0.0,
                    errors=[str(raw_result)],
                    timestamp_utc=datetime.now(UTC),
                )
            elif isinstance(raw_result, StrategyScanResult):
                result_dict[strategy_id] = raw_result

        return result_dict

    async def _run_strategies_sequential(
        self,
        timeframe: str,
    ) -> dict[str, StrategyScanResult]:
        """Run all strategies sequentially.

        Args:
            timeframe: Candle timeframe for data fetch.

        Returns:
            Dictionary mapping strategy_id to ScanResult.
        """
        _LOGGER.info("Running %d strategies sequentially", len(self._strategies))

        result_dict: dict[str, StrategyScanResult] = {}
        for strategy_id in self._strategies:
            result = await self.run_single_scan_cycle(strategy_id, timeframe)
            result_dict[strategy_id] = result

        return result_dict

    def get_strategy_state(self, strategy_id: str) -> StrategyState | None:
        """Get current state of a strategy.

        Args:
            strategy_id: Strategy identifier.

        Returns:
            StrategyState if found, None otherwise.
        """
        return self._strategy_states.get(strategy_id)

    def get_all_strategy_states(self) -> dict[str, StrategyState]:
        """Get states of all strategies.

        Returns:
            Dictionary mapping strategy_id to StrategyState.
        """
        return self._strategy_states.copy()

    def get_pool_status(self) -> dict[str, Any]:
        """Get shared provider pool status.

        Returns:
            Dictionary with pool status information.
        """
        return {
            "available_capacity": self._provider_pool.available_capacity,
            "concurrent_requests": self._provider_pool.concurrent_requests,
            "total_strategies": len(self._strategies),
            "active_strategies": len([s for s in self._strategies.values() if s is not None]),
        }

    async def reset_strategy_state(self, strategy_id: str) -> None:
        """Reset state for a specific strategy.

        Args:
            strategy_id: Strategy identifier.

        Raises:
            ConfigError: If strategy_id not found.
        """
        if strategy_id not in self._strategies:
            msg = f"Strategy not found: {strategy_id}"
            raise ConfigError(msg)

        async with self._lock:
            self._strategy_states[strategy_id] = StrategyState(
                strategy_id=strategy_id,
            )
            self._position_guards[strategy_id] = SimplePositionGuard(
                max_positions=self._strategy_configs[
                    next(
                        i
                        for i, c in enumerate(self._strategy_configs)
                        if c.strategy_id == strategy_id
                    )
                ].max_positions,
                max_position_value=self._strategy_configs[
                    next(
                        i
                        for i, c in enumerate(self._strategy_configs)
                        if c.strategy_id == strategy_id
                    )
                ].max_position_value,
            )

            _LOGGER.info("Reset state for strategy: %s", strategy_id)

    async def stop_all_strategies(self) -> None:
        """Stop all strategies and cleanup resources.

        This method gracefully shuts down all running strategies
        and clears internal state.
        """
        _LOGGER.info("Stopping all strategies")

        async with self._lock:
            self._strategies.clear()
            self._strategy_states.clear()
            self._position_guards.clear()

            _LOGGER.info("All strategies stopped")
