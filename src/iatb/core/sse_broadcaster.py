"""
Server-Sent Events (SSE) broadcaster for real-time dashboard updates.

Provides a singleton broadcaster that subscribes to event bus topics
and pushes events to connected SSE clients via FastAPI streaming responses.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from iatb.core.event_bus import EventBus
from iatb.core.events import (
    PnLUpdateEvent,
    ScanUpdateEvent,
)

_LOGGER = logging.getLogger(__name__)


_SSE_QUEUE_MAXSIZE = 1000


class SSEBroadcaster:
    """Manages SSE client connections and event broadcasting."""

    def __init__(self) -> None:
        """Initialize the SSE broadcaster."""
        self._event_bus: EventBus | None = None
        self._subscribers: list[asyncio.Queue[dict[str, str] | None]] = []
        self._forwarding_tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self, event_bus: EventBus) -> None:
        """Start the broadcaster and subscribe to event bus topics.

        Args:
            event_bus: The event bus instance to subscribe to.

        Raises:
            RuntimeError: If broadcaster is already running.
        """
        if self._running:
            return

        self._event_bus = event_bus

        # Subscribe to scan updates
        scan_queue = await event_bus.subscribe("scan")
        task1 = asyncio.create_task(self._forward_events("scan", scan_queue))
        self._forwarding_tasks.append(task1)

        # Subscribe to PnL updates
        pnl_queue = await event_bus.subscribe("pnl")
        task2 = asyncio.create_task(self._forward_events("pnl", pnl_queue))
        self._forwarding_tasks.append(task2)

        self._running = True
        _LOGGER.info("SSE broadcaster started")

    async def stop(self) -> None:
        """Stop the broadcaster and cleanup."""
        if not self._running:
            return

        self._running = False

        # Cancel all forwarding tasks
        for task in self._forwarding_tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

        self._forwarding_tasks.clear()

        async with self._lock:
            # Close all subscriber queues
            for queue in self._subscribers:
                try:
                    queue.put_nowait(None)  # Signal to close
                except Exception as exc:
                    _LOGGER.debug("Failed to signal queue close: %s", exc)
            self._subscribers.clear()
        _LOGGER.info("SSE broadcaster stopped")

    async def _forward_events(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        """Forward events from event bus topic to all SSE subscribers.

        Args:
            topic: The event bus topic name.
            queue: The event queue for this topic.
        """
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                if event is None:
                    break

                # Convert event to SSE format
                event_data = self._event_to_sse(topic, event)

                # Broadcast to all subscribers
                async with self._lock:
                    dead_subscribers = []
                    for subscriber in self._subscribers:
                        try:
                            subscriber.put_nowait(event_data)
                        except Exception as exc:
                            _LOGGER.warning("Failed to send event to subscriber: %s", exc)
                            dead_subscribers.append(subscriber)

                    # Remove dead subscribers
                    for dead in dead_subscribers:
                        self._subscribers.remove(dead)

                queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.error("Error forwarding events from %s: %s", topic, exc)

    def _event_to_sse(self, topic: str, event: Any) -> dict[str, str]:
        """Convert an event to SSE-compatible format.

        Args:
            topic: The event topic.
            event: The event object.

        Returns:
            Dictionary with 'event' and 'data' keys for SSE format.
        """
        event_type = topic
        data = {}

        if isinstance(event, ScanUpdateEvent):
            data = {
                "event_type": "scan_update",
                "timestamp": str(event.timestamp),
                "total_candidates": event.total_candidates,
                "approved_candidates": event.approved_candidates,
                "trades_executed": event.trades_executed,
                "duration_ms": event.duration_ms,
                "errors": event.errors,
            }
        elif isinstance(event, PnLUpdateEvent):
            data = {
                "event_type": "pnl_update",
                "timestamp": str(event.timestamp),
                "order_id": event.order_id,
                "symbol": event.symbol,
                "side": event.side,
                "quantity": str(event.quantity),
                "price": str(event.price),
                "trade_pnl": str(event.trade_pnl),
                "cumulative_pnl": str(event.cumulative_pnl),
            }
        else:
            # Generic event handling
            data = {
                "event_type": topic,
                "timestamp": str(getattr(event, "timestamp", "")),
                "data": str(event),
            }

        return {
            "event": event_type,
            "data": json.dumps(data, default=str),
        }

    async def subscribe(self) -> AsyncIterator[str]:
        """Create a new SSE subscription.

        Yields:
            Server-Sent Event formatted strings.

        Example:
            >>> async for message in broadcaster.subscribe():
            ...     _LOGGER.info("Message: %s", message)
        """
        queue: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=_SSE_QUEUE_MAXSIZE)

        async with self._lock:
            self._subscribers.append(queue)

        try:
            # Send initial connection event
            yield self._format_sse("connection", json.dumps({"status": "connected"}))

            # Stream events
            while self._running:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if event_data is None:
                        break

                    yield self._format_sse(event_data["event"], event_data["data"])
                    queue.task_done()
                except asyncio.TimeoutError:
                    # Send keepalive comment every 30 seconds
                    yield ": keepalive\n\n"
                    continue
                except asyncio.CancelledError:
                    break
        finally:
            # Unsubscribe on exit
            async with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    def _format_sse(self, event: str, data: str) -> str:
        """Format event data as SSE message.

        Args:
            event: The event name.
            data: The JSON-encoded data.

        Returns:
            Formatted SSE string.
        """
        return f"event: {event}\ndata: {data}\n\n"


# Module-level singleton state (created lazily in async context)
_broadcaster: SSEBroadcaster | None = None
_broadcaster_lock: asyncio.Lock | None = None


def _get_broadcaster_lock() -> asyncio.Lock:
    """Get or create the module-level lock in the current event loop.

    This ensures the lock is created inside a running event loop,
    avoiding the deprecation warning in Python 3.12+.

    Returns:
        The module-level asyncio.Lock.
    """
    global _broadcaster_lock
    if _broadcaster_lock is None:
        _broadcaster_lock = asyncio.Lock()
    return _broadcaster_lock


async def get_broadcaster() -> SSEBroadcaster:
    """Get the singleton SSE broadcaster instance.

    This function uses async locks to ensure thread-safe singleton
    initialization in concurrent asyncio contexts. The lock is created
    lazily inside the running event loop to avoid Python 3.12+
    deprecation warnings.

    Returns:
        The SSE broadcaster instance.
    """
    global _broadcaster

    lock = _get_broadcaster_lock()

    async with lock:
        if _broadcaster is None:
            _broadcaster = SSEBroadcaster()
        return _broadcaster
