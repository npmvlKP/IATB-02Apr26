#!/usr/bin/env python
"""
iATB Master Startup Script — Orchestrates engine and dashboard startup.

This script ensures the Engine API (port 8000) starts BEFORE the dashboard (port 8080),
preventing the "Loading..." issue when the dashboard attempts to connect.

Startup sequence:
   1. Start Engine with event bus
   2. Wait for /health endpoint to return 200 OK
   3. Start Dashboard on port 8080
   4. Handle graceful shutdown on Ctrl+C

Run:  poetry run python scripts/start_master.py
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iatb.core.engine import Engine

# ── Logging Setup ──

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
_LOGGER = logging.getLogger("start_master")


# ── Engine Startup ──


async def start_engine() -> "Engine":
    """Start engine.

    Returns:
        Engine instance.
    """
    from iatb.core.engine import Engine
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.risk.kill_switch import KillSwitch

    _LOGGER.info("Starting engine components...")

    executor = PaperExecutor()
    kill_switch = KillSwitch(executor)
    engine: Engine = Engine(kill_switch=kill_switch)

    await engine.start()

    _LOGGER.info("  ✓ Engine started (running: %s)", engine.is_running)
    _LOGGER.info("  ✓ Health endpoints available via FastAPI: /health/live, /health/ready")

    return engine


# ── Dashboard Startup ──


def start_dashboard() -> subprocess.Popen[str] | None:
    """Start dashboard server in subprocess.

    Returns:
        Subprocess handle or None on failure.
    """
    _LOGGER.info("Starting dashboard server...")

    try:
        # Start dashboard in background
        # Command is fully controlled - no user input involved
        proc = subprocess.Popen(
            [sys.executable, "scripts/dashboard.py"],  # noqa: S603 - controlled subprocess call
            cwd=Path.cwd(),
            stdout=None,  # Inherit parent stdout to avoid pipe buffer blocking
            stderr=subprocess.STDOUT,
            text=True,
        )
        _LOGGER.info("  ✓ Dashboard started on port 8080 (PID: %d)", proc.pid)
        return proc
    except Exception as exc:
        _LOGGER.error("  ✗ Dashboard start failed: %s", exc)
        return None


# ── Main Orchestrator ──


async def main_async() -> int:
    """Main async entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    _LOGGER.info("=" * 70)
    _LOGGER.info("iATB Master Startup Script")
    _LOGGER.info("=" * 70)

    # Track background processes
    engine: Engine | None = None
    dashboard_proc: subprocess.Popen[str] | None = None
    exit_code = 0

    try:
        # Step 1: Start Engine
        engine = await start_engine()

        # Step 2: Start Dashboard
        dashboard_proc = start_dashboard()
        if not dashboard_proc:
            _LOGGER.error("Dashboard failed to start")
            return 1

        _LOGGER.info("")
        _LOGGER.info("=" * 70)
        _LOGGER.info("✓ All services started successfully!")
        _LOGGER.info("  - Engine API:   http://localhost:8000/health/live")
        _LOGGER.info("  - Engine API:   http://localhost:8000/health/ready")
        _LOGGER.info("  - Dashboard:    http://localhost:8080")
        _LOGGER.info("  - Press Ctrl+C to stop all services")
        _LOGGER.info("=" * 70)
        _LOGGER.info("")

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            # Check if dashboard process is still alive
            if dashboard_proc.poll() is not None:
                _LOGGER.warning("Dashboard process died unexpectedly")
                break

    except KeyboardInterrupt:
        _LOGGER.info("")
        _LOGGER.info("Shutting down gracefully...")
        exit_code = 0

    except Exception as exc:
        _LOGGER.exception("Fatal error during startup: %s", exc)
        exit_code = 1

    finally:
        # Cleanup
        if dashboard_proc:
            _LOGGER.info("Stopping dashboard (PID: %d)...", dashboard_proc.pid)
            dashboard_proc.terminate()
            try:
                dashboard_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _LOGGER.warning("Dashboard did not terminate gracefully, killing...")
                dashboard_proc.kill()

        if engine:
            _LOGGER.info("Stopping engine...")
            await engine.stop()
            _LOGGER.info("  ✓ Engine stopped")

        _LOGGER.info("Shutdown complete.")

    return exit_code


def main() -> None:
    """Synchronous main entry point."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
