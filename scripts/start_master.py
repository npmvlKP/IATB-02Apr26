#!/usr/bin/env python
"""
iATB Master Startup Script — Orchestrates engine and dashboard startup.

This script ensures the Engine API (port 8000) starts BEFORE the dashboard (port 8080),
preventing the "Loading..." issue when the dashboard attempts to connect.

Startup sequence:
  1. Start HealthServer on port 8000
  2. Start Engine with event bus
  3. Wait for /health endpoint to return 200 OK
  4. Start Dashboard on port 8080
  5. Handle graceful shutdown on Ctrl+C

Run:  poetry run python scripts/start_master.py
"""

import asyncio
import logging
import subprocess
import sys
import urllib.request
from pathlib import Path

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


async def start_engine() -> tuple[object, object]:
    """Start engine and health server.

    Returns:
        Tuple of (engine, health_server) instances.
    """
    from iatb.core.engine import Engine
    from iatb.core.health import HealthServer
    from iatb.execution.paper_executor import PaperExecutor
    from iatb.risk.kill_switch import KillSwitch

    _LOGGER.info("Starting engine components...")

    executor = PaperExecutor()
    kill_switch = KillSwitch(executor)
    engine = Engine(kill_switch=kill_switch)
    health = HealthServer(port=8000)

    health.start()
    await engine.start()

    _LOGGER.info("  ✓ Engine started (running: %s)", engine.is_running)
    _LOGGER.info("  ✓ Health server started on port 8000")

    return engine, health


async def wait_for_health_endpoint(timeout_seconds: int = 30) -> bool:
    """Wait for /health endpoint to return 200 OK.

    This function is fully async and uses asyncio.sleep() and asyncio.to_thread()
    to avoid blocking the event loop.

    Args:
        timeout_seconds: Maximum time to wait.

    Returns:
        True if health endpoint is responding, False on timeout.
    """
    _LOGGER.info("Waiting for health endpoint...")
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        try:
            # Run blocking urllib.request.urlopen in a thread to avoid blocking event loop
            result = await asyncio.to_thread(
                lambda: urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            )
            with result as resp:
                if resp.status == 200:
                    body = resp.read().decode()
                    _LOGGER.info("  ✓ Health endpoint responding: %s", body)
                    return True
        except Exception:
            _LOGGER.debug("  Health endpoint not ready yet, retrying...")
            # Use asyncio.sleep instead of time.sleep to avoid blocking
            await asyncio.sleep(1)

    _LOGGER.error("  ✗ Health endpoint timeout after %d seconds", timeout_seconds)
    return False


# ── Dashboard Startup ──


def start_dashboard() -> subprocess.Popen | None:
    """Start dashboard server in subprocess.

    Returns:
        Subprocess handle or None on failure.
    """
    _LOGGER.info("Starting dashboard server...")

    try:
        # Start dashboard in background
        # Command is fully controlled - no user input involved
        proc = subprocess.Popen(  # noqa: S603 - controlled subprocess call
            [sys.executable, "scripts/dashboard.py"],
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
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
    engine = None
    health = None
    dashboard_proc = None
    exit_code = 0

    try:
        # Step 1: Start Engine and Health Server
        engine, health = await start_engine()

        # Step 2: Wait for health endpoint
        if not await wait_for_health_endpoint(timeout_seconds=30):
            _LOGGER.error("Health endpoint did not become available")
            return 1

        # Step 3: Start Dashboard
        dashboard_proc = start_dashboard()
        if not dashboard_proc:
            _LOGGER.error("Dashboard failed to start")
            return 1

        _LOGGER.info("")
        _LOGGER.info("=" * 70)
        _LOGGER.info("✓ All services started successfully!")
        _LOGGER.info("  - Engine API:   http://localhost:8000/health")
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

        if health:
            _LOGGER.info("Stopping health server...")
            health.stop()
            _LOGGER.info("  ✓ Health server stopped")

        _LOGGER.info("Shutdown complete.")

    return exit_code


def main() -> None:
    """Synchronous main entry point."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
