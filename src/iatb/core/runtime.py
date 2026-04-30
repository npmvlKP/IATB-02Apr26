"""
Runtime entrypoint for containerized/local engine startup.
"""

import asyncio
import logging
import signal

from iatb.core.engine import Engine

logger = logging.getLogger(__name__)


async def run_runtime(stop_event: asyncio.Event | None = None) -> None:
    """Run engine until stop event is set."""
    event = stop_event or asyncio.Event()
    engine = Engine()
    await engine.start()
    logger.info("IATB runtime started")
    try:
        await event.wait()
    finally:
        await engine.stop()
        logger.info("IATB runtime stopped")


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
