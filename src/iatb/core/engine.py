"""
Engine orchestrator for IATB.

Manages startup and shutdown lifecycle of system components.
"""

import asyncio
import logging
from collections.abc import Coroutine

from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError

logger = logging.getLogger(__name__)


class Engine:
    """Orchestrates system startup and shutdown."""

    def __init__(self) -> None:
        """Initialize the engine."""
        self._event_bus = EventBus()
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

    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._running
