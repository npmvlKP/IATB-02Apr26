"""
Tests for engine orchestrator.
"""

import asyncio
import random

import numpy as np
import pytest
import torch
from iatb.core.engine import Engine
from iatb.core.event_bus import EventBus
from iatb.core.exceptions import EngineError

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestEngineLifecycle:
    """Test engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping engine."""
        engine = Engine()
        assert not engine.is_running

        await engine.start()
        assert engine.is_running

        await engine.stop()
        assert not engine.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """Test that start can be called multiple times."""
        engine = Engine()
        await engine.start()
        await engine.start()  # Should not raise
        assert engine.is_running
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Test that stop can be called multiple times."""
        engine = Engine()
        await engine.start()
        await engine.stop()
        await engine.stop()  # Should not raise
        assert not engine.is_running


class TestEngineEventBus:
    """Test engine event bus integration."""

    @pytest.mark.asyncio
    async def test_event_bus_property(self) -> None:
        """Test that engine has event bus."""
        engine = Engine()
        assert isinstance(engine.event_bus, EventBus)

    @pytest.mark.asyncio
    async def test_event_bus_started_on_engine_start(self) -> None:
        """Test that event bus starts when engine starts."""
        engine = Engine()
        assert not engine.event_bus._running

        await engine.start()
        assert engine.event_bus._running

        await engine.stop()


class TestEngineTasks:
    """Test engine task management."""

    @pytest.mark.asyncio
    async def test_run_task(self) -> None:
        """Test running a task in engine."""
        engine = Engine()
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
        engine = Engine()

        async def dummy_task() -> None:
            pass

        coro = dummy_task()
        with pytest.raises(EngineError, match="Engine not running"):
            await engine.run_task(coro)

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_stop(self) -> None:
        """Test that tasks are cancelled when engine stops."""
        engine = Engine()
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
        engine = Engine()
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
