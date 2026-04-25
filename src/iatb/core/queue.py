"""
Queue backend architecture for event bus.

Supports pluggable backends for in-process and external message queues.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from iatb.core.exceptions import EventBusError

logger = logging.getLogger(__name__)


@dataclass
class EventMetadata:
    """Metadata for persisted events."""

    event_id: str
    topic: str
    timestamp: str
    sequence: int


class EventBusBackend(ABC):
    """Abstract base class for event bus backends."""

    def __init__(self) -> None:
        """Initialize the backend."""
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start the backend."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the backend and clean up resources."""

    @abstractmethod
    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        """Subscribe to a topic and return a queue for receiving events."""

    @abstractmethod
    async def unsubscribe(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a queue from a topic."""

    @abstractmethod
    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to a topic."""

    @abstractmethod
    async def publish_batch(self, topic: str, events: list[Any]) -> None:
        """Publish multiple events to a topic in batch."""

    @property
    def is_running(self) -> bool:
        """Check if backend is running."""
        return self._running

    def _validate_running(self) -> None:
        """Validate backend is running, fail-closed."""
        if not self._running:
            msg = "Event bus backend is not running"
            raise EventBusError(msg)


class InProcessBackend(EventBusBackend):
    """In-memory asyncio queue backend for single-machine deployment."""

    def __init__(self) -> None:
        """Initialize the in-process backend."""
        super().__init__()
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = {}
        self._queues: list[asyncio.Queue[Any]] = []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the in-process backend."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            logger.info("In-process backend started")

    async def stop(self) -> None:
        """Stop the in-process backend and clean up resources."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            self._subscribers.clear()
            self._queues.clear()
            logger.info("In-process backend stopped")

    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        """Subscribe to a topic and return a queue for receiving events."""
        self._validate_running()
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
        self._validate_running()
        async with self._lock:
            if topic in self._subscribers:
                if queue in self._subscribers[topic]:
                    self._subscribers[topic].remove(queue)
                    if queue in self._queues:
                        self._queues.remove(queue)
                    logger.debug(f"Unsubscribed from topic: {topic}")

    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to a topic."""
        self._validate_running()
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
            logger.debug(
                "Published event to %s subscribers on topic: %s",
                len(queues),
                topic,
            )

    async def publish_batch(self, topic: str, events: list[Any]) -> None:
        """Publish multiple events to a topic in batch."""
        self._validate_running()

        if not events:
            return

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


class RedisStreamBackend(EventBusBackend):
    """Redis Streams backend for distributed event bus."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        max_stream_length: int = 10000,
    ) -> None:
        """Initialize the Redis Streams backend.

        Args:
            host: Redis host address.
            port: Redis port.
            db: Redis database number.
            password: Redis password.
            max_stream_length: Maximum stream length before trimming.
        """
        super().__init__()
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._max_stream_length = max_stream_length
        self._client: Any = None
        self._subscribers: dict[str, list[asyncio.Queue[Any]]] = {}
        self._listener_tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the Redis backend and initialize connection."""
        async with self._lock:
            if self._running:
                return

            try:
                # Lazy import to avoid hard dependency
                import redis.asyncio as redis  # type: ignore

                self._client = redis.Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    decode_responses=True,
                )
                await self._client.ping()
                self._running = True
                logger.info(f"Redis backend started on {self._host}:{self._port}")
            except ImportError as exc:
                msg = "Redis package not installed. Install with: pip install redis"
                raise EventBusError(msg) from exc
            except Exception as exc:
                msg = f"Failed to connect to Redis: {exc}"
                raise EventBusError(msg) from exc

    async def stop(self) -> None:
        """Stop the Redis backend and clean up resources."""
        async with self._lock:
            if not self._running:
                return

            # Cancel all listener tasks
            for task in self._listener_tasks.values():
                task.cancel()
            self._listener_tasks.clear()

            # Close Redis connection
            if self._client:
                await self._client.close()
                self._client = None

            self._subscribers.clear()
            self._running = False
            logger.info("Redis backend stopped")

    async def subscribe(self, topic: str) -> asyncio.Queue[Any]:
        """Subscribe to a topic and return a queue for receiving events."""
        self._validate_running()
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
                # Start listener for this topic
                self._listener_tasks[topic] = asyncio.create_task(
                    self._listen_to_stream(topic),
                )

            queue: asyncio.Queue[Any] = asyncio.Queue()
            self._subscribers[topic].append(queue)
            logger.debug(f"Subscribed to Redis stream: {topic}")
            return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a queue from a topic."""
        self._validate_running()
        async with self._lock:
            if topic in self._subscribers:
                if queue in self._subscribers[topic]:
                    self._subscribers[topic].remove(queue)
                    logger.debug(f"Unsubscribed from Redis stream: {topic}")

                # Stop listener if no more subscribers
                if not self._subscribers[topic]:
                    if topic in self._listener_tasks:
                        self._listener_tasks[topic].cancel()
                        del self._listener_tasks[topic]
                    del self._subscribers[topic]

    async def publish(self, topic: str, event: Any) -> None:
        """Publish an event to a Redis stream."""
        self._validate_running()

        if not self._client:
            msg = "Redis client not initialized"
            raise EventBusError(msg)

        try:
            # Serialize event to JSON
            event_data = self._serialize_event(event)
            await self._client.xadd(
                f"stream:{topic}",
                event_data,
                maxlen=self._max_stream_length,
            )
            logger.debug(f"Published event to Redis stream: {topic}")
        except Exception as exc:
            logger.error("Error publishing to Redis: %s", exc)
            msg = f"Failed to publish event to Redis stream '{topic}'"
            raise EventBusError(msg) from exc

    async def publish_batch(self, topic: str, events: list[Any]) -> None:
        """Publish multiple events to a Redis stream in batch."""
        self._validate_running()

        if not events:
            return

        if not self._client:
            msg = "Redis client not initialized"
            raise EventBusError(msg)

        try:
            # Use pipeline for batch publishing
            pipeline = self._client.pipeline()
            for event in events:
                event_data = self._serialize_event(event)
                pipeline.xadd(
                    f"stream:{topic}",
                    event_data,
                    maxlen=self._max_stream_length,
                )
            await pipeline.execute()
            logger.debug(
                "Published %s events to Redis stream: %s",
                len(events),
                topic,
            )
        except Exception as exc:
            logger.error("Error publishing batch to Redis: %s", exc)
            msg = f"Failed to publish batch to Redis stream '{topic}'"
            raise EventBusError(msg) from exc

    async def _listen_to_stream(self, topic: str) -> None:
        """Listen to a Redis stream and forward events to subscribers."""
        stream_key = f"stream:{topic}"
        last_id = "0"

        while self._running:
            try:
                # Read new messages from stream
                messages = await self._client.xread(
                    {stream_key: last_id},
                    count=10,
                    block=1000,
                )

                if messages:
                    for _, stream_messages in messages:
                        for message_id, data in stream_messages:
                            last_id = message_id
                            event = self._deserialize_event(data)

                            # Forward to all subscribers
                            async with self._lock:
                                if topic in self._subscribers:
                                    for queue in self._subscribers[topic]:
                                        try:
                                            await queue.put(event)
                                        except Exception as exc:
                                            logger.error(
                                                "Error forwarding event: %s",
                                                exc,
                                            )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error listening to stream %s: %s", topic, exc)
                await asyncio.sleep(1)

    def _serialize_event(self, event: Any) -> dict[str, str]:
        """Serialize event to Redis-compatible format."""
        if hasattr(event, "model_dump"):
            # Pydantic model
            return {"data": json.dumps(event.model_dump())}
        return {"data": json.dumps(event)}

    def _deserialize_event(self, data: dict[str, str]) -> Any:
        """Deserialize event from Redis format."""
        event_json = data.get("data", "{}")
        return json.loads(event_json)


def create_backend(backend_type: str = "inprocess", **kwargs: Any) -> EventBusBackend:
    """Factory function to create event bus backends.

    Args:
        backend_type: Type of backend ("inprocess" or "redis").
        **kwargs: Additional arguments for backend initialization.

    Returns:
        Configured event bus backend instance.

    Raises:
        EventBusError: If backend type is invalid.
    """
    if backend_type == "inprocess":
        return InProcessBackend()
    elif backend_type == "redis":
        return RedisStreamBackend(**kwargs)
    else:
        msg = f"Invalid backend type: {backend_type}. Use 'inprocess' or 'redis'"
        raise EventBusError(msg)
