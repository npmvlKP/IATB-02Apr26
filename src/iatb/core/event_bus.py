"""
Event bus implementation for IATB.

Provides asynchronous publish-subscribe functionality with topic-based
routing and batch publishing capabilities.
"""

import asyncio
import logging
from typing import Any

from iatb.core.event_validation import validate_event
from iatb.core.exceptions import EventBusError

logger = logging.getLogger(__name__)


class EventBus:
    """Async event bus with topic-based routing."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = {}
        self._queues: list[asyncio.Queue[Any]] = []
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the event bus."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop the event bus and clean up resources."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            # Clear all queues
            self._subscribers.clear()
            self._queues.clear()
            logger.info("Event bus stopped")

    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        """Subscribe to a topic and return a queue for receiving events."""
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            queue: asyncio.Queue[Any] = asyncio.Queue()
            self._subscribers[topic].append(queue)
            self._queues.append(queue)
            logger.debug(f"Subscribed to topic: {topic}")
            return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a queue from a topic."""
        async with self._lock:
            if topic in self._subscribers:
                if queue in self._subscribers[topic]:
                    self._subscribers[topic].remove(queue)
                    if queue in self._queues:
                        self._queues.remove(queue)
                    logger.debug(f"Unsubscribed from topic: {topic}")

    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to a topic."""
        if not self._running:
            msg = "Event bus is not running"
            raise EventBusError(msg)
        self._validate_runtime_event(event)

        async with self._lock:
            if topic not in self._subscribers:
                return

            queues = self._subscribers[topic]
            if not queues:
                return
            for queue in queues:
                try:
                    await queue.put(event)
                except Exception as exc:
                    logger.error("Error publishing to queue: %s", exc)
                    msg = f"Failed to publish event on topic '{topic}'"
                    raise EventBusError(msg) from exc
            logger.debug("Published event to %s subscribers on topic: %s", len(queues), topic)

    async def publish_batch(self, topic: str, events: list[Any]) -> None:
        """Publish multiple events to a topic in batch."""
        if not self._running:
            msg = "Event bus is not running"
            raise EventBusError(msg)

        if not events:
            return
        for event in events:
            self._validate_runtime_event(event)

        async with self._lock:
            if topic not in self._subscribers:
                return

            queues = self._subscribers[topic]
            if not queues:
                return
            for queue in queues:
                for event in events:
                    try:
                        await queue.put(event)
                    except Exception as exc:
                        logger.error("Error publishing batch event: %s", exc)
                        msg = f"Failed to publish batch on topic '{topic}'"
                        raise EventBusError(msg) from exc
            logger.debug(
                "Published %s events to %s subscribers on topic: %s",
                len(events),
                len(queues),
                topic,
            )

    @staticmethod
    def _validate_runtime_event(event: Any) -> None:
        """Validate runtime event payload fail-closed before publish."""
        try:
            validate_event(event)
        except Exception as exc:
            msg = f"Event validation failed: {exc}"
            raise EventBusError(msg) from exc
