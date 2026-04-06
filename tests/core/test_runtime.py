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


@pytest.mark.asyncio
async def test_register_signal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signal handler registration should wire stop_event.set to signals."""
    import signal

    registered: list[str] = []

    class _FakeLoop:
        def add_signal_handler(self, sig: signal.Signals, callback: object) -> None:
            registered.append(sig.name)

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
    stop_event = asyncio.Event()
    runtime._register_signal_handlers(stop_event)
    assert len(registered) >= 1


@pytest.mark.asyncio
async def test_main_runs_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """_main should invoke run_runtime and respect signal handlers."""
    called: list[str] = []

    async def _fake_run_runtime(
        stop_event: asyncio.Event | None = None, health_port: int = 8000
    ) -> None:
        called.append("run_runtime")
        if stop_event:
            stop_event.set()

    monkeypatch.setattr(runtime, "run_runtime", _fake_run_runtime)
    monkeypatch.setattr(runtime, "_register_signal_handlers", lambda e: None)
    await runtime._main()
    assert "run_runtime" in called


def test_main_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() should call asyncio.run with _main."""
    import logging as stdlib_logging

    called: list[str] = []

    def _fake_run(coro: object) -> None:
        called.append("asyncio.run")
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[union-attr]

    monkeypatch.setattr(asyncio, "run", _fake_run)
    monkeypatch.setattr(stdlib_logging, "basicConfig", lambda **kw: None)
    runtime.main()
    assert "asyncio.run" in called
