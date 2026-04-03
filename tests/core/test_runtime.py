"""
Tests for runtime entrypoint orchestration.
"""

import asyncio

import iatb.core.runtime as runtime
import pytest


@pytest.mark.asyncio
async def test_run_runtime_starts_and_stops_components(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime should start and stop health server and engine around stop event."""
    lifecycle: list[str] = []

    class _FakeEngine:
        async def start(self) -> None:
            lifecycle.append("engine-start")

        async def stop(self) -> None:
            lifecycle.append("engine-stop")

    class _FakeHealthServer:
        def __init__(self, host: str = "127.0.0.1", port: int = 8000) -> None:
            _ = (host, port)

        def start(self) -> None:
            lifecycle.append("health-start")

        def stop(self) -> None:
            lifecycle.append("health-stop")

    monkeypatch.setattr(runtime, "Engine", _FakeEngine)
    monkeypatch.setattr(runtime, "HealthServer", _FakeHealthServer)
    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.run_runtime(stop_event=stop_event, health_port=8111))
    await asyncio.sleep(0.01)
    stop_event.set()
    await task
    assert lifecycle == ["health-start", "engine-start", "engine-stop", "health-stop"]
