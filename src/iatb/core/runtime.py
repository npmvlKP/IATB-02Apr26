"""Runtime entrypoint for containerized/local engine startup."""

from __future__ import annotations

import asyncio
import logging
import signal

from iatb.core.engine import (
    Engine,  # noqa: F401 — module-level for type hints & test monkeypatching
)

logger = logging.getLogger(__name__)


async def run_runtime(stop_event: asyncio.Event | None = None) -> None:
    """Run engine until stop event is set."""
    event = stop_event or asyncio.Event()

    from iatb.core.config import get_config
    from iatb.core.event_bus import EventBus
    from iatb.core.sse_broadcaster import SSEBroadcaster

    config = get_config()
    event_bus = EventBus()
    sse_broadcaster = SSEBroadcaster()
    engine = Engine(
        event_bus=event_bus,
        sse_broadcaster=sse_broadcaster,
        config=config,
    )
    await engine.start()
    logger.info("IATB runtime started")
    logger.info(
        "Engine is running in '%s' mode - waiting for events/signals. "
        "Press Ctrl+C to stop gracefully.",
        config.execution_mode,
    )
    try:
        await _idle_loop(event, engine)
    finally:
        logger.info("Shutting down...")
        await engine.stop()
        logger.info("IATB runtime stopped")


async def _idle_loop(
    stop_event: asyncio.Event,
    engine: Engine,
    heartbeat_seconds: int = 60,
) -> None:
    """Idle loop with periodic heartbeat until stop event is set.

    Args:
        stop_event: Event that signals shutdown.
        engine: Running engine instance for health reporting.
        heartbeat_seconds: Seconds between heartbeat log messages.
    """
    elapsed = 0
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.0)
        except TimeoutError:
            elapsed += 1
            if elapsed >= heartbeat_seconds:
                health = engine.health_status()
                logger.info(
                    "Heartbeat | engine=%s | event_bus=%s | "
                    "uptime=%ds | mode=%s | press Ctrl+C to stop",
                    health.get("engine", "unknown"),
                    health.get("event_bus", "unknown"),
                    elapsed,
                    health.get("config", "unknown"),
                )
                elapsed = 0


def _register_signal_handlers(stop_event: asyncio.Event) -> None:
    """Wire SIGINT/SIGTERM handlers to stop event."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda _sig, _frame: stop_event.set())


async def _main() -> None:
    """Run runtime with process signal support."""
    stop_event = asyncio.Event()
    _register_signal_handlers(stop_event)
    await run_runtime(stop_event=stop_event)


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
