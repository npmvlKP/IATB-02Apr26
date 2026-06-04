"""Tests for iatb.core.runtime module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from iatb.core.runtime import _idle_loop, _register_signal_handlers, run_runtime


@pytest.fixture()
def mock_engine() -> MagicMock:
    """Create a mock Engine with async start/stop and health_status."""
    engine = MagicMock()
    engine.start = AsyncMock()
    engine.stop = AsyncMock()
    engine.is_running = True
    engine.health_status.return_value = {
        "engine": "running",
        "event_bus": "ok",
        "config": "paper",
    }
    return engine


class TestRunRuntime:
    """Tests for run_runtime function."""

    async def test_run_runtime_starts_and_stops(self, mock_engine: MagicMock) -> None:
        """Engine starts, logs mode, then stops when event is set."""
        mock_config = MagicMock()
        mock_config.execution_mode = "paper"
        with patch("iatb.core.engine.Engine", return_value=mock_engine):
            with patch("iatb.core.config.get_config", return_value=mock_config):
                stop_event = asyncio.Event()

                async def _delayed_stop() -> None:
                    await asyncio.sleep(0.1)
                    stop_event.set()

                task = asyncio.create_task(_delayed_stop())
                await run_runtime(stop_event=stop_event)
                await task
                mock_engine.start.assert_awaited_once()
                mock_engine.stop.assert_awaited_once()

    async def test_run_runtime_paper_mode_log(
        self, mock_engine: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Runtime logs the execution mode on startup."""
        mock_config = MagicMock()
        mock_config.execution_mode = "paper"
        with patch("iatb.core.engine.Engine", return_value=mock_engine):
            with patch("iatb.core.config.get_config", return_value=mock_config):
                stop_event = asyncio.Event()
                stop_event.set()
                await run_runtime(stop_event=stop_event)
                assert "paper" in caplog.text


class TestIdleLoop:
    """Tests for _idle_loop function."""

    async def test_idle_loop_exits_on_stop(self, mock_engine: MagicMock) -> None:
        """Idle loop exits immediately when stop event is already set."""
        stop_event = asyncio.Event()
        stop_event.set()
        await _idle_loop(stop_event, mock_engine, heartbeat_seconds=5)
        mock_engine.health_status.assert_not_called()

    async def test_idle_loop_heartbeat(self, mock_engine: MagicMock) -> None:
        """Idle loop emits heartbeat after heartbeat_seconds elapsed."""
        stop_event = asyncio.Event()

        async def _stop_after_delay() -> None:
            await asyncio.sleep(2.5)
            stop_event.set()

        task = asyncio.create_task(_stop_after_delay())
        await _idle_loop(stop_event, mock_engine, heartbeat_seconds=1)
        await task
        assert mock_engine.health_status.call_count >= 1

    async def test_idle_loop_no_heartbeat_before_interval(
        self, mock_engine: MagicMock
    ) -> None:
        """Idle loop does not emit heartbeat before interval."""
        stop_event = asyncio.Event()

        async def _stop_quickly() -> None:
            await asyncio.sleep(0.5)
            stop_event.set()

        task = asyncio.create_task(_stop_quickly())
        await _idle_loop(stop_event, mock_engine, heartbeat_seconds=60)
        await task
        mock_engine.health_status.assert_not_called()


class TestRegisterSignalHandlers:
    """Tests for _register_signal_handlers function."""

    def test_register_signal_handlers_sets_handler(self) -> None:
        """Signal handlers are registered without error."""

        async def _test() -> None:
            stop_event = asyncio.Event()
            _register_signal_handlers(stop_event)

        asyncio.run(_test())
