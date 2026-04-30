"""
Tests for runtime entrypoint orchestration.
"""

import asyncio
from unittest.mock import patch

import iatb.core.runtime as runtime
import pytest


@pytest.mark.asyncio
async def test_run_runtime_starts_and_stops_components(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime should start and stop engine around stop event."""
    lifecycle: list[str] = []

    class _FakeEngine:
        async def start(self) -> None:
            lifecycle.append("engine-start")

        async def stop(self) -> None:
            lifecycle.append("engine-stop")

    monkeypatch.setattr(runtime, "Engine", _FakeEngine)
    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.run_runtime(stop_event=stop_event))
    await asyncio.sleep(0.01)
    stop_event.set()
    await task
    assert lifecycle == ["engine-start", "engine-stop"]


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

    async def _fake_run_runtime(stop_event: asyncio.Event | None = None) -> None:
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


@pytest.mark.asyncio
async def test_run_runtime_without_stop_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime should create its own stop event if not provided."""
    event_created: list[bool] = []

    class _FakeEngine:
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    monkeypatch.setattr(runtime, "Engine", _FakeEngine)

    # Mock asyncio.Event to track creation
    original_event = asyncio.Event

    def tracked_event() -> asyncio.Event:
        event_created.append(True)
        return original_event()

    with patch.object(asyncio, "Event", tracked_event):
        task = asyncio.create_task(runtime.run_runtime())
        await asyncio.sleep(0.01)
        # Cancel the task since we don't have a stop event to set
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(event_created) > 0


@pytest.mark.asyncio
async def test_run_runtime_handles_engine_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime should handle errors during engine startup gracefully."""

    class _FailingEngine:
        async def start(self) -> None:
            raise RuntimeError("Engine start failed")

    monkeypatch.setattr(runtime, "Engine", _FailingEngine)

    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.run_runtime(stop_event=stop_event))
    # Should raise the error
    with pytest.raises(RuntimeError, match="Engine start failed"):
        await asyncio.sleep(0.01)
        stop_event.set()
        await task


@pytest.mark.asyncio
async def test_run_runtime_handles_engine_stop_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime should handle errors during engine stop gracefully."""

    class _EngineWithStopError:
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            raise RuntimeError("Engine stop failed")

    monkeypatch.setattr(runtime, "Engine", _EngineWithStopError)

    stop_event = asyncio.Event()
    task = asyncio.create_task(runtime.run_runtime(stop_event=stop_event))
    await asyncio.sleep(0.01)
    stop_event.set()

    # Should propagate the error
    with pytest.raises(RuntimeError, match="Engine stop failed"):
        await task


@pytest.mark.asyncio
async def test_main_handles_signal_handler_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_main should propagate errors in signal handler registration."""
    called: list[str] = []

    async def _fake_run_runtime(stop_event: asyncio.Event | None = None) -> None:
        called.append("run_runtime")
        if stop_event:
            stop_event.set()

    monkeypatch.setattr(runtime, "run_runtime", _fake_run_runtime)
    monkeypatch.setattr(
        runtime,
        "_register_signal_handlers",
        lambda e: (_ for _ in ()).throw(RuntimeError("Signal handler error")),
    )

    # Should raise signal handler error (actual behavior)
    with pytest.raises(RuntimeError, match="Signal handler error"):
        await runtime._main()


def test_main_logging_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() should configure logging before running."""
    import logging as stdlib_logging

    configured: list[bool] = []

    def _fake_config(**kwargs: object) -> None:
        configured.append(True)

    def _fake_run(coro: object) -> None:
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[union-attr]

    monkeypatch.setattr(stdlib_logging, "basicConfig", _fake_config)
    monkeypatch.setattr(asyncio, "run", _fake_run)

    runtime.main()

    assert len(configured) > 0


@pytest.mark.asyncio
async def test_multiple_runtime_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that multiple runtime instances can run independently."""
    instance_count: list[int] = []

    class _CountingEngine:
        def __init__(self) -> None:
            instance_count.append(len(instance_count))

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    monkeypatch.setattr(runtime, "Engine", _CountingEngine)

    # Run two runtime instances sequentially
    stop_event1 = asyncio.Event()
    task1 = asyncio.create_task(runtime.run_runtime(stop_event=stop_event1))
    await asyncio.sleep(0.01)
    stop_event1.set()
    await task1

    stop_event2 = asyncio.Event()
    task2 = asyncio.create_task(runtime.run_runtime(stop_event=stop_event2))
    await asyncio.sleep(0.01)
    stop_event2.set()
    await task2

    # Should have created two engine instances
    assert len(instance_count) == 2
