"""
Paper trading runtime with continuous work loop.

This runtime:
- Runs continuous scanning cycles
- Executes paper trades
- Maintains paper trading state
- Handles graceful shutdown
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from iatb.core.engine import Engine
from iatb.core.event_bus import EventBus
from iatb.execution.paper_executor import PaperExecutor
from iatb.storage.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class PaperTradingRuntime:
    """Continuous paper trading runtime."""

    def __init__(
        self,
        scan_interval_seconds: float = 60.0,
        audit_db_path: Path | None = None,
    ) -> None:
        """Initialize paper trading runtime.

        Args:
            scan_interval_seconds: Interval between scan cycles
            audit_db_path: Path to audit database
        """
        self._scan_interval = scan_interval_seconds
        self._audit_db_path = audit_db_path or Path("data/audit/trades.sqlite")
        self._running = False
        self._stop_event = asyncio.Event()

        # Components
        self._engine = Engine()
        self._paper_executor = PaperExecutor()
        self._audit_logger = AuditLogger(self._audit_db_path)
        self._event_bus = EventBus()

    async def start(self) -> None:
        """Start paper trading runtime."""
        logger.info("Starting paper trading runtime")
        self._running = True
        self._stop_event.clear()

        # Start components
        await self._engine.start()
        await self._event_bus.start()

        logger.info("Paper trading runtime started - beginning scan loop")

    async def stop(self) -> None:
        """Stop paper trading runtime."""
        logger.info("Stopping paper trading runtime")
        self._running = False
        self._stop_event.set()

        # Stop components
        await self._event_bus.stop()
        await self._engine.stop()

        logger.info("Paper trading runtime stopped")

    async def run_scan_cycle(self) -> None:
        """Run a single scanning and trading cycle."""
        try:
            timestamp = datetime.now(UTC).isoformat()
            logger.info("Starting scan cycle", extra={"timestamp_utc": timestamp})

            # In a real implementation, this would:
            # 1. Fetch market data
            # 2. Run sentiment analysis
            # 3. Calculate market strength
            # 4. Run scanner
            # 5. Execute paper trades for qualified instruments
            # 6. Log all trades to audit database

            # For now, just log that we ran a cycle
            logger.info("Scan cycle completed")

        except Exception as e:
            logger.error(
                "Error in scan cycle",
                extra={
                    "error": str(e),
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                },
                exc_info=True,
            )

    async def run_continuous(self) -> None:
        """Run continuous paper trading loop."""
        while self._running and not self._stop_event.is_set():
            try:
                await self.run_scan_cycle()

                # Wait for next cycle or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._scan_interval,
                    )
                    # If we get here, stop_event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout is expected - continue to next cycle
                    continue

            except asyncio.CancelledError:
                logger.info("Scan loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "Unexpected error in scan loop",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                # Wait a bit before retrying
                await asyncio.sleep(5)

    async def run(self) -> None:
        """Main entry point - start and run continuously."""
        await self.start()
        try:
            await self.run_continuous()
        finally:
            await self.stop()


async def run_paper_runtime(scan_interval_seconds: float = 60.0) -> None:
    """Convenience function to run paper trading runtime.

    Args:
        scan_interval_seconds: Interval between scan cycles
    """
    runtime = PaperTradingRuntime(scan_interval_seconds=scan_interval_seconds)
    await runtime.run()


def _register_signal_handlers(stop_event: asyncio.Event) -> None:
    """Wire SIGINT/SIGTERM handlers to stop event."""
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, OSError):
            pass


async def _main() -> None:
    """Run paper runtime with process signal support."""
    stop_event = asyncio.Event()
    _register_signal_handlers(stop_event)

    # Create and run runtime
    runtime = PaperTradingRuntime()
    await runtime.start()

    try:
        # Run continuous loop with stop_event
        while not stop_event.is_set():
            await runtime.run_scan_cycle()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                continue
    finally:
        await runtime.stop()


def main() -> None:
    """CLI entrypoint for paper trading runtime."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(_main())


if __name__ == "__main__":
    main()
