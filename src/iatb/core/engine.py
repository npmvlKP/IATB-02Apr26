"""
Engine orchestrator for IATB.

Manages startup and shutdown lifecycle of system components.
"""

import asyncio
import logging
from collections.abc import Coroutine
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
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

logger = logging.getLogger(__name__)


class Engine:
    """Orchestrates system startup and shutdown."""

    def __init__(
        self,
        instrument_scorer: InstrumentScorer | None = None,
    ) -> None:
        """Initialize the engine."""
        self._event_bus = EventBus()
        self._scorer = instrument_scorer or InstrumentScorer()
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
            self._running = True
            await self._event_bus.start()
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

    @property
    def instrument_scorer(self) -> InstrumentScorer:
        """Get the instrument scorer instance."""
        return self._scorer

    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running
