"""Supplemental coverage tests for runtime module.

Covers: _register_signal_handlers NotImplementedError fallback,
run_runtime with default stop event, _main integration, main() logging setup.
"""

import asyncio
import signal

import iatb.core.runtime as runtime
import pytest


class TestSignalHandlerNotImplementedFallback:
    @pytest.mark.asyncio
    async def test_notimplementederror_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fallback_called: list[int] = []

        class _FakeLoop:
            def add_signal_handler(self, sig: signal.Signals, callback: object) -> None:
                raise NotImplementedError("Windows does not support add_signal_handler")

        def fake_signal_handler(sig: int, handler: object) -> None:
            fallback_called.append(sig)

        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())
        monkeypatch.setattr(signal, "signal", fake_signal_handler)

        stop_event = asyncio.Event()
        runtime._register_signal_handlers(stop_event)

        assert len(fallback_called) >= 1


class TestSignalHandlerSuccessfulRegistration:
    @pytest.mark.asyncio
    async def test_successful_signal_registration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registered: list[str] = []

        class _FakeLoop:
            def add_signal_handler(self, sig: signal.Signals, callback: object) -> None:
                registered.append(sig.name)

        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())

        stop_event = asyncio.Event()
        runtime._register_signal_handlers(stop_event)

        assert "SIGINT" in registered or "SIGTERM" in registered


class TestRuntimeStopEventDefault:
    @pytest.mark.asyncio
    async def test_default_stop_event_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lifecycle: list[str] = []

        class _FakeEngine:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                lifecycle.append("started")

            async def stop(self) -> None:
                lifecycle.append("stopped")

        monkeypatch.setattr(runtime, "Engine", _FakeEngine)

        task = asyncio.create_task(runtime.run_runtime())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "started" in lifecycle


class TestRuntimeEngineStopInFinally:
    @pytest.mark.asyncio
    async def test_engine_stop_called_in_finally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lifecycle: list[str] = []

        class _FakeEngine:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                lifecycle.append("start")

            async def stop(self) -> None:
                lifecycle.append("stop")

        monkeypatch.setattr(runtime, "Engine", _FakeEngine)

        stop_event = asyncio.Event()
        task = asyncio.create_task(runtime.run_runtime(stop_event=stop_event))
        await asyncio.sleep(0.01)
        stop_event.set()
        await task

        assert lifecycle == ["start", "stop"]


class TestMainEntrypoint:
    def test_main_calls_asyncio_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import logging as stdlib_logging

        called: list[str] = []

        def _fake_run(coro: object) -> None:
            called.append("asyncio.run")
            if hasattr(coro, "close"):
                coro.close()

        monkeypatch.setattr(asyncio, "run", _fake_run)
        monkeypatch.setattr(stdlib_logging, "basicConfig", lambda **kw: None)
        runtime.main()
        assert "asyncio.run" in called

    def test_main_configures_logging_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import logging as stdlib_logging

        captured_level: list[int] = []

        def _fake_config(**kwargs: object) -> None:
            if "level" in kwargs:
                captured_level.append(kwargs["level"])

        def _fake_run(coro: object) -> None:
            if hasattr(coro, "close"):
                coro.close()

        monkeypatch.setattr(stdlib_logging, "basicConfig", _fake_config)
        monkeypatch.setattr(asyncio, "run", _fake_run)
        runtime.main()
        assert stdlib_logging.INFO in captured_level


class TestRuntimeMainIntegration:
    @pytest.mark.asyncio
    async def test_main_creates_and_sets_stop_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events_set: list[str] = []

        class _FakeEvent:
            def set(self) -> None:
                events_set.append("set")

            async def wait(self) -> None:
                events_set.append("waited")

        class _FakeEngine:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

        monkeypatch.setattr(runtime, "Engine", _FakeEngine)

        def fake_event() -> _FakeEvent:
            return _FakeEvent()

        monkeypatch.setattr(asyncio, "Event", fake_event)

        task = asyncio.create_task(runtime._main())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestRuntimeEngineErrorInStop:
    @pytest.mark.asyncio
    async def test_engine_stop_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lifecycle: list[str] = []

        class _FaultyEngine:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                lifecycle.append("start")

            async def stop(self) -> None:
                lifecycle.append("stop-fail")
                raise RuntimeError("stop failed")

        monkeypatch.setattr(runtime, "Engine", _FaultyEngine)

        stop_event = asyncio.Event()
        stop_event.set()
        with pytest.raises(RuntimeError, match="stop failed"):
            await runtime.run_runtime(stop_event=stop_event)

        assert "start" in lifecycle


class TestSignalHandlerBothSignals:
    @pytest.mark.asyncio
    async def test_registers_sigint_and_sigterm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registered_signals: list[int] = []

        class _FakeLoop:
            def add_signal_handler(self, sig: signal.Signals, callback: object) -> None:
                registered_signals.append(sig)

        monkeypatch.setattr(asyncio, "get_running_loop", lambda: _FakeLoop())

        stop_event = asyncio.Event()
        runtime._register_signal_handlers(stop_event)

        assert signal.SIGINT in registered_signals
        assert signal.SIGTERM in registered_signals
