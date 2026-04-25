"""
Event bus implementation for IATB.

Provides asynchronous publish-subscribe functionality with topic-based
routing and batch publishing capabilities using pluggable backends.
"""

import asyncio
import logging
from typing import Any

from iatb.core.event_validation import validate_event
from iatb.core.exceptions import EventBusError
from iatb.core.queue import EventBusBackend, InProcessBackend

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus with pluggable backends and topic-based routing."""

    def __init__(self, backend: EventBusBackend | None = None) -> None:
        """Initialize the event bus.

        Args:
            backend: Optional backend instance. Defaults to InProcessBackend.
        """
        self._backend = backend if backend else InProcessBackend()

    async def start(self) -> None:
        """Start the event bus and underlying backend."""
        await self._backend.start()
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the event bus and underlying backend."""
        await self._backend.stop()
        logger.info("Event bus stopped")

    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        """Subscribe to a topic and return a queue for receiving events."""
        return await self._backend.subscribe(topic)

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a queue from a topic."""
        await self._backend.unsubscribe(topic, queue)

    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to a topic."""
        self._validate_runtime_event(event)
        await self._backend.publish(topic, event)

    async def publish_batch(self, topic: str, events: list[Any]) -> None:
        """Publish multiple events to a topic in batch."""
        if not events:
            return

        for event in events:
            self._validate_runtime_event(event)

        await self._backend.publish_batch(topic, events)

    @property
    def is_running(self) -> bool:
        """Check if the event bus is running."""
        return self._backend.is_running

    @staticmethod
    def _validate_runtime_event(event: Any) -> None:
        """Validate runtime event payload fail-closed before publish."""
        try:
            validate_event(event)
        except Exception as exc:
            msg = f"Event validation failed: {exc}"
            raise EventBusError(msg) from exc
