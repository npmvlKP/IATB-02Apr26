"""
Tests for PaperTradingRuntime.
"""

import asyncio

import pytest
from iatb.core.paper_runtime import (
    PaperTradingRuntime,
    _register_signal_handlers,
)


@pytest.mark.asyncio
async def test_start_and_stop(tmp_path) -> None:
    runtime = PaperTradingRuntime(audit_db_path=tmp_path / "audit.sqlite")
    await runtime.start()
    assert runtime._running is True
    await runtime.stop()
    assert runtime._running is False


@pytest.mark.asyncio
async def test_run_scan_cycle(tmp_path) -> None:
    runtime = PaperTradingRuntime(audit_db_path=tmp_path / "audit.sqlite")
    await runtime.run_scan_cycle()


@pytest.mark.asyncio
async def test_run_continuous_stops_on_flag(tmp_path) -> None:
    runtime = PaperTradingRuntime(
        scan_interval_seconds=0.01,
        audit_db_path=tmp_path / "audit.sqlite",
    )
    await runtime.start()
    task = asyncio.create_task(runtime.run_continuous())
    await asyncio.sleep(0.05)
    runtime._stop_event.set()
    await task


@pytest.mark.asyncio
async def test_run_full_lifecycle(tmp_path) -> None:
    runtime = PaperTradingRuntime(
        scan_interval_seconds=0.01,
        audit_db_path=tmp_path / "audit.sqlite",
    )
    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.05)
    runtime._stop_event.set()
    await task


@pytest.mark.asyncio
async def test_register_signal_handlers_windows_fallback() -> None:
    stop_event = asyncio.Event()
    _register_signal_handlers(stop_event)
    assert not stop_event.is_set()


@pytest.mark.asyncio
async def test_main_entrypoint(monkeypatch) -> None:
    from iatb.core import paper_runtime

    called: list[str] = []

    def _fake_run(coro: object) -> None:
        called.append("asyncio.run")
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[union-attr]

    monkeypatch.setattr(asyncio, "run", _fake_run)
    import logging as stdlib_logging

    monkeypatch.setattr(stdlib_logging, "basicConfig", lambda **kw: None)
    paper_runtime.main()
    assert "asyncio.run" in called
