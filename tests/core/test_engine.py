"""
Tests for engine orchestrator.
"""

import asyncio
import random
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch
from iatb.core.config import Config
from iatb.core.engine import Engine
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError
from iatb.core.sse_broadcaster import SSEBroadcaster

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestEngineLifecycle:
    """Test engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping engine."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        assert not engine.is_running

        await engine.start()
        assert engine.is_running
        mock_bus.start.assert_called_once()
        mock_sse.start.assert_called_once_with(mock_bus)

        await engine.stop()
        assert not engine.is_running
        mock_sse.stop.assert_called_once()
        mock_bus.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """Test that start can be called multiple times."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()
        await engine.start()  # Should not raise
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Test that stop can be called multiple times."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()
        await engine.stop()
        await engine.stop()  # Should not raise
        assert not engine.is_running


class TestEngineEventBus:
    """Test engine event bus integration."""

    @pytest.mark.asyncio
    async def test_event_bus_property(self) -> None:
        """Test that engine has event bus."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        assert engine.event_bus is mock_bus

    @pytest.mark.asyncio
    async def test_event_bus_started_on_engine_start(self) -> None:
        """Test that event bus starts when engine starts."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()
        mock_bus.start.assert_called_once()

        await engine.stop()


class TestEngineTasks:
    """Test engine task management."""

    @pytest.mark.asyncio
    async def test_run_task(self) -> None:
        """Test running a task in engine."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()

        task_completed = False

        async def dummy_task() -> None:
            nonlocal task_completed
            await asyncio.sleep(0.01)
            task_completed = True

        await engine.run_task(dummy_task())
        await asyncio.sleep(0.02)  # Wait for task to complete

        assert task_completed
        await engine.stop()

    @pytest.mark.asyncio
    async def test_run_task_not_running_raises_error(self) -> None:
        """Test that running task when engine not started raises error."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )

        async def dummy_task() -> None:
            pass

        coro = dummy_task()
        with pytest.raises(EngineError, match="Engine not running"):
            await engine.run_task(coro)

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_stop(self) -> None:
        """Test that tasks are cancelled when engine stops."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()

        task_cancelled = False

        async def long_running_task() -> None:
            nonlocal task_cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                task_cancelled = True
                raise

        await engine.run_task(long_running_task())
        await asyncio.sleep(0.01)  # Let task start

        await engine.stop()
        await asyncio.sleep(0.01)  # Let cancellation propagate

        assert task_cancelled

    @pytest.mark.asyncio
    async def test_multiple_tasks(self) -> None:
        """Test running multiple tasks."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "paper"

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )
        await engine.start()

        completed_tasks = []

        async def task(n: int) -> None:
            await asyncio.sleep(0.01)
            completed_tasks.append(n)

        for i in range(3):
            await engine.run_task(task(i))

        await asyncio.sleep(0.02)  # Wait for all tasks

        assert len(completed_tasks) == 3
        await engine.stop()


class TestEngineProperties:
    """Test engine properties."""

    def test_instrument_scorer_property(self) -> None:
        """Test instrument_scorer property."""
        from iatb.selection.instrument_scorer import InstrumentScorer

        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)

        scorer = InstrumentScorer()
        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            instrument_scorer=scorer,
        )

        assert engine.instrument_scorer is scorer

    def test_health_status(self) -> None:
        """Test health status aggregation."""
        mock_bus = MagicMock(spec=EventBus)
        mock_bus.is_running = False
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )

        status = engine.health_status()
        assert status["engine"] == "stopped"
        assert status["sse_broadcaster"] == "stopped"

        # Mock running state
        engine._running = True
        mock_bus.is_running = True

        status = engine.health_status()
        assert status["engine"] == "running"
        assert status["sse_broadcaster"] == "ok"
        assert status["event_bus"] == "ok"

    @pytest.mark.asyncio
    async def test_preflight_check_live_mode(self) -> None:
        """Test preflight check for live mode."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_conf.execution_mode = "live"
        mock_conf.live_trading_enabled = False

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
        )

        with pytest.raises(EngineError, match="Live trading enabled"):
            await engine.start()

    @pytest.mark.asyncio
    async def test_kill_switch_methods(self) -> None:
        """Test kill switch engage/disengage methods."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_ks = MagicMock()

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            kill_switch=mock_ks,
        )

        # Test engage
        engine.engage_kill_switch("test reason")
        mock_ks.engage.assert_called_once()
        assert mock_ks.engage.call_args[0][0] == "test reason"
        assert mock_ks.engage.call_args[0][1].tzinfo is not None

        # Test disengage
        engine.disengage_kill_switch()
        mock_ks.disengage.assert_called_once()

    def test_kill_switch_property(self) -> None:
        """Test kill_switch property."""
        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_ks = MagicMock()

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            kill_switch=mock_ks,
        )

        assert engine.kill_switch is mock_ks

    def test_data_provider_property(self) -> None:
        """Test data_provider property."""
        from iatb.data.base import DataProvider

        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_dp = MagicMock(spec=DataProvider)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            data_provider=mock_dp,
        )

        assert engine.data_provider is mock_dp

    def test_order_manager_property(self) -> None:
        """Test order_manager property."""
        from iatb.execution.order_manager import OrderManager

        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_om = MagicMock(spec=OrderManager)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            order_manager=mock_om,
        )

        assert engine.order_manager is mock_om

    def test_instrument_scanner_property(self) -> None:
        """Test instrument_scanner property."""
        from iatb.scanner.instrument_scanner import InstrumentScanner

        mock_bus = MagicMock(spec=EventBus)
        mock_sse = MagicMock(spec=SSEBroadcaster)
        mock_conf = MagicMock(spec=Config)
        mock_scanner = MagicMock(spec=InstrumentScanner)

        engine = Engine(
            event_bus=mock_bus,
            sse_broadcaster=mock_sse,
            config=mock_conf,
            instrument_scanner=mock_scanner,
        )

        assert engine.instrument_scanner is mock_scanner
