"""
Engine orchestrator for IATB.

Manages startup and shutdown lifecycle of system components.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.config import Config
from iatb.core.enums import OrderSide
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError
from iatb.core.sse_broadcaster import SSEBroadcaster
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.risk.kill_switch import KillSwitch
from iatb.selection.instrument_scorer import (
    InstrumentScorer,
    InstrumentSignals,
)
from iatb.selection.ranking import SelectionResult
from iatb.selection.selection_bridge import (
    build_strategy_contexts,
    extract_strength_map,
)
from iatb.strategies.base import StrategyContext

if TYPE_CHECKING:
    from iatb.data.base import DataProvider
    from iatb.execution.order_manager import OrderManager
    from iatb.scanner.instrument_scanner import (
        InstrumentScanner,
        ScannerConfig,
        ScannerResult,
        SortDirection,
    )
    from iatb.scanner.scan_cycle import ScanCycleResult

logger = logging.getLogger(__name__)


class Engine:
    """Orchestrates system startup and shutdown."""

    def __init__(
        self,
        event_bus: EventBus,
        sse_broadcaster: SSEBroadcaster,
        config: Config,
        instrument_scorer: InstrumentScorer | None = None,
        kill_switch: KillSwitch | None = None,
        data_provider: DataProvider | None = None,
        instrument_scanner: InstrumentScanner | None = None,
        order_manager: OrderManager | None = None,
        scanner_config: ScannerConfig | None = None,
    ) -> None:
        """Initialize the engine with core components and optional pipeline dependencies."""
        self._event_bus = event_bus
        self._sse_broadcaster = sse_broadcaster
        self._config = config
        self._scorer = instrument_scorer or InstrumentScorer()
        self._kill_switch = kill_switch
        self._data_provider = data_provider
        self._instrument_scanner = instrument_scanner
        self._order_manager = order_manager
        self._scanner_config = scanner_config
        self._running = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the engine and all components."""
        async with self._lock:
            if self._running:
                logger.warning("Engine already running")
                return

            logger.info("Starting engine")

            # Preflight checks
            if self._config.execution_mode == "live" and not self._config.live_trading_enabled:
                raise EngineError(
                    "Live trading enabled in config but live_trading_enabled is False",
                )

            self._running = True
            await self._event_bus.start()
            await self._sse_broadcaster.start(self._event_bus)

            logger.info("Engine started")

    async def stop(self) -> None:
        """Stop the engine and all components."""
        async with self._lock:
            if not self._running:
                logger.warning("Engine not running")
                return

            logger.info("Stopping engine")
            self._running = False

            # Cancel all tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()

            # Wait for tasks to complete
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)

            await self._sse_broadcaster.stop()
            await self._event_bus.stop()
            self._tasks.clear()
            logger.info("Engine stopped")

    async def run_task(self, coro: Coroutine[None, None, None]) -> None:
        """Run a task in the engine's task group."""
        if not self._running:
            coro.close()
            msg = "Engine not running"
            raise EngineError(msg)

        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @property
    def event_bus(self) -> EventBus:
        """Get the event bus instance."""
        return self._event_bus

    def select_instruments(
        self,
        signals: list[InstrumentSignals],
        regime: MarketRegime,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> SelectionResult:
        """Run instrument selection via the scorer."""
        return self._scorer.score_and_select(signals, regime, correlations)

    def run_selection_cycle(
        self,
        signals: list[InstrumentSignals],
        regime: MarketRegime,
        strength_by_symbol: dict[str, StrengthInputs] | None = None,
        side: OrderSide = OrderSide.BUY,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> list[StrategyContext]:
        """Full cycle: score → select → build StrategyContext list."""
        strength_map = strength_by_symbol or extract_strength_map(signals)
        selection = self.select_instruments(signals, regime, correlations)
        return build_strategy_contexts(selection, strength_map, side)

    async def run_selection_cycle_async(
        self,
        signals: list[InstrumentSignals],
        regime: MarketRegime,
        strength_by_symbol: dict[str, StrengthInputs] | None = None,
        side: OrderSide = OrderSide.BUY,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> list[StrategyContext]:
        """Async variant: runs selection in executor to avoid blocking."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.run_selection_cycle,
            signals,
            regime,
            strength_by_symbol,
            side,
            correlations,
        )

    def run_full_cycle(
        self,
        *,
        symbols: Sequence[str] | None = None,
        max_trades: int = 5,
    ) -> ScanCycleResult:
        """Run full pipeline: DataProvider -> Scanner -> Execution -> Audit.

        Delegates to scan_cycle.run_scan_cycle() using the engine's
        configured dependencies (data_provider, order_manager,
        scanner_config).

        Args:
            symbols: Symbols to scan (default: NIFTY50).
            max_trades: Maximum trades per cycle.

        Returns:
            ScanCycleResult with scan results, trades, PnL, and errors.
        """
        from iatb.scanner.scan_cycle import run_scan_cycle

        return run_scan_cycle(
            symbols=symbols,
            max_trades=max_trades,
            order_manager=self._order_manager,
            data_provider=self._data_provider,
            scanner_config=self._scanner_config,
        )

    def run_scan_only(
        self,
        *,
        symbols: Sequence[str] | None = None,
        direction: SortDirection | None = None,
    ) -> ScannerResult:
        """Run scanner without trade execution.

        Uses the configured InstrumentScanner or creates one from the
        stored DataProvider and ScannerConfig. The *symbols* parameter
        is only used when creating a new scanner; a pre-configured
        scanner uses its own symbol list.

        Args:
            symbols: Symbols to scan (used only if no scanner configured).
            direction: Sort direction (default: GAINERS).

        Returns:
            ScannerResult with ranked gainers/losers.

        Raises:
            EngineError: If neither scanner nor data_provider is configured.
        """
        from iatb.scanner.instrument_scanner import (
            InstrumentScanner as _InstrumentScanner,
        )
        from iatb.scanner.instrument_scanner import (
            SortDirection as _SortDirection,
        )

        direction_resolved = direction or _SortDirection.GAINERS

        scanner = self._instrument_scanner
        if scanner is None:
            if self._data_provider is None:
                msg = (
                    "Cannot run scan: no instrument_scanner or "
                    "data_provider configured. Provide them at "
                    "construction or use run_selection_cycle() instead."
                )
                raise EngineError(msg)
            scanner = _InstrumentScanner(
                config=self._scanner_config,
                data_provider=self._data_provider,
                symbols=list(symbols) if symbols else None,
            )
        return scanner.scan(direction=direction_resolved)

    def engage_kill_switch(self, reason: str) -> None:
        """Engage kill switch from engine level."""
        if self._kill_switch is None:
            msg = "no kill switch configured"
            raise EngineError(msg)
        from datetime import UTC, datetime

        self._kill_switch.engage(reason, datetime.now(UTC))

    def disengage_kill_switch(self) -> None:
        """Disengage kill switch from engine level."""
        if self._kill_switch is None:
            msg = "no kill switch configured"
            raise EngineError(msg)
        from datetime import UTC, datetime

        self._kill_switch.disengage(datetime.now(UTC))

    @property
    def kill_switch(self) -> KillSwitch | None:
        return self._kill_switch

    @property
    def instrument_scorer(self) -> InstrumentScorer:
        """Get the instrument scorer instance."""
        return self._scorer

    @property
    def data_provider(self) -> DataProvider | None:
        """Get the configured data provider."""
        return self._data_provider

    @property
    def instrument_scanner(self) -> InstrumentScanner | None:
        """Get the configured instrument scanner."""
        return self._instrument_scanner

    @property
    def order_manager(self) -> OrderManager | None:
        """Get the configured order manager."""
        return self._order_manager

    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running

    def health_status(self) -> dict[str, str]:
        """Return aggregated health status of core components."""
        # Determine SSE broadcaster status without accessing private attribute
        sse_status = "ok" if self._running and self._event_bus.is_running else "stopped"

        return {
            "engine": "running" if self._running else "stopped",
            "event_bus": "ok" if self._event_bus.is_running else "stopped",
            "sse_broadcaster": sse_status,
            "config": "loaded",
        }
