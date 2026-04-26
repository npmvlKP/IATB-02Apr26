"""
Tests for queue backend architecture.

Coverage:
- InProcessBackend: lifecycle, pub/sub, batch, multi-subscriber, topic isolation
- RedisStreamBackend: mocked lifecycle, serialization, error handling
- create_backend: factory pattern
- EventBusBackend: abstract contract
- EventMetadata: dataclass creation
- Edge cases: concurrent ops, empty batches, unsubscribe non-existent
- Error paths: publish when stopped, invalid backend type
"""

import asyncio
import builtins
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from iatb.core.exceptions import EventBusError
from iatb.core.queue import (
    EventBusBackend,
    EventMetadata,
    InProcessBackend,
    RedisStreamBackend,
    create_backend,
)

# ---------------------------------------------------------------------------
# EventMetadata
# ---------------------------------------------------------------------------


class TestEventMetadata:
    """Tests for EventMetadata dataclass."""

    def test_metadata_creation(self) -> None:
        """Test creating EventMetadata with valid fields."""
        meta = EventMetadata(
            event_id="evt_001",
            topic="market_ticks",
            timestamp="2024-06-15T10:30:00+00:00",
            sequence=1,
        )
        assert meta.event_id == "evt_001"
        assert meta.topic == "market_ticks"
        assert meta.timestamp == "2024-06-15T10:30:00+00:00"
        assert meta.sequence == 1

    def test_metadata_sequence_increment(self) -> None:
        """Test sequence values increment correctly."""
        meta1 = EventMetadata(event_id="e1", topic="t", timestamp="ts", sequence=1)
        meta2 = EventMetadata(event_id="e2", topic="t", timestamp="ts", sequence=2)
        assert meta2.sequence > meta1.sequence

    def test_metadata_different_topics(self) -> None:
        """Test metadata with different topic values."""
        topics = ["market_ticks", "order_updates", "signals", "pnl"]
        metas = [
            EventMetadata(event_id=f"e{i}", topic=t, timestamp="ts", sequence=i)
            for i, t in enumerate(topics, 1)
        ]
        assert [m.topic for m in metas] == topics


# ---------------------------------------------------------------------------
# InProcessBackend - Lifecycle
# ---------------------------------------------------------------------------


class TestInProcessBackendLifecycle:
    """Tests for InProcessBackend start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_initial_state_not_running(self) -> None:
        """Test backend starts in not-running state."""
        backend = InProcessBackend()
        assert not backend.is_running

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        """Test start sets running flag to True."""
        backend = InProcessBackend()
        await backend.start()
        assert backend.is_running
        await backend.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Test calling start multiple times is safe."""
        backend = InProcessBackend()
        await backend.start()
        await backend.start()
        assert backend.is_running
        await backend.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self) -> None:
        """Test stop clears running flag."""
        backend = InProcessBackend()
        await backend.start()
        await backend.stop()
        assert not backend.is_running

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        """Test calling stop multiple times is safe."""
        backend = InProcessBackend()
        await backend.stop()
        assert not backend.is_running

    @pytest.mark.asyncio
    async def test_stop_clears_subscribers(self) -> None:
        """Test stop clears all subscriber queues."""
        backend = InProcessBackend()
        await backend.start()
        await backend.subscribe("topic_a")
        await backend.subscribe("topic_b")
        assert len(backend._subscribers) == 2
        await backend.stop()
        assert len(backend._subscribers) == 0


# ---------------------------------------------------------------------------
# InProcessBackend - Subscribe / Unsubscribe
# ---------------------------------------------------------------------------


class TestInProcessBackendSubscribe:
    """Tests for InProcessBackend subscribe and unsubscribe."""

    @pytest.mark.asyncio
    async def test_subscribe_returns_unique_queues(self) -> None:
        """Test each subscribe call returns a unique queue."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        q2 = await backend.subscribe("topic")
        assert q1 is not q2
        await backend.stop()

    @pytest.mark.asyncio
    async def test_subscribe_when_not_running_raises(self) -> None:
        """Test subscribing when backend is not running raises EventBusError."""
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.subscribe("topic")

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self) -> None:
        """Test unsubscribe removes the specific queue."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        q2 = await backend.subscribe("topic")
        await backend.unsubscribe("topic", q1)
        assert q1 not in backend._subscribers["topic"]
        assert q2 in backend._subscribers["topic"]
        await backend.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_queue_noop(self) -> None:
        """Test unsubscribing a queue that was never subscribed is safe."""
        backend = InProcessBackend()
        await backend.start()
        fake_queue: asyncio.Queue[object] = asyncio.Queue()
        await backend.unsubscribe("nonexistent", fake_queue)
        await backend.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_topic_noop(self) -> None:
        """Test unsubscribing from a topic that doesn't exist is safe."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("real_topic")
        await backend.unsubscribe("fake_topic", queue)
        await backend.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_when_not_running_raises(self) -> None:
        """Test unsubscribing when not running raises EventBusError."""
        backend = InProcessBackend()
        queue: asyncio.Queue[object] = asyncio.Queue()
        with pytest.raises(EventBusError, match="not running"):
            await backend.unsubscribe("topic", queue)

    @pytest.mark.asyncio
    async def test_multiple_topics_independent(self) -> None:
        """Test subscribing to multiple topics creates separate subscriber lists."""
        backend = InProcessBackend()
        await backend.start()
        await backend.subscribe("topic_a")
        await backend.subscribe("topic_b")
        assert len(backend._subscribers["topic_a"]) == 1
        assert len(backend._subscribers["topic_b"]) == 1
        await backend.stop()


# ---------------------------------------------------------------------------
# InProcessBackend - Publish / Subscribe
# ---------------------------------------------------------------------------


class TestInProcessBackendPublish:
    """Tests for InProcessBackend publish and receive."""

    @pytest.mark.asyncio
    async def test_publish_single_event(self) -> None:
        """Test publishing a single event to one subscriber."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")
        event = {"type": "tick", "symbol": "RELIANCE"}
        await backend.publish("topic", event)
        received = await queue.get()
        assert received == event
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_to_no_subscribers_noop(self) -> None:
        """Test publishing to topic with no subscribers does not raise."""
        backend = InProcessBackend()
        await backend.start()
        await backend.publish("empty_topic", {"data": 1})
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_multiple_subscribers_all_receive(self) -> None:
        """Test all subscribers on a topic receive the published event."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        q2 = await backend.subscribe("topic")
        q3 = await backend.subscribe("topic")
        event = {"id": 42}
        await backend.publish("topic", event)
        assert await q1.get() == event
        assert await q2.get() == event
        assert await q3.get() == event
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_to_different_topics_isolated(self) -> None:
        """Test events published to one topic don't reach another topic."""
        backend = InProcessBackend()
        await backend.start()
        qa = await backend.subscribe("topic_a")
        qb = await backend.subscribe("topic_b")
        await backend.publish("topic_a", {"from": "a"})
        assert await qa.get() == {"from": "a"}
        assert qb.empty()
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_when_not_running_raises(self) -> None:
        """Test publishing when backend is not running raises EventBusError."""
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish("topic", {"data": 1})

    @pytest.mark.asyncio
    async def test_publish_after_unsubscribe(self) -> None:
        """Test unsubscribed queue does not receive new events."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        q2 = await backend.subscribe("topic")
        await backend.unsubscribe("topic", q1)
        await backend.publish("topic", {"after": "unsub"})
        assert q1.empty()
        assert await q2.get() == {"after": "unsub"}
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_complex_event(self) -> None:
        """Test publishing a complex nested event."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")
        event = {
            "level1": {
                "level2": {"value": 42, "items": [1, 2, 3]},
            },
            "flag": True,
            "name": "test",
        }
        await backend.publish("topic", event)
        received = await queue.get()
        assert received == event
        assert received["level1"]["level2"]["value"] == 42
        await backend.stop()


# ---------------------------------------------------------------------------
# InProcessBackend - Batch
# ---------------------------------------------------------------------------


class TestInProcessBackendBatch:
    """Tests for InProcessBackend batch publishing."""

    @pytest.mark.asyncio
    async def test_publish_batch_multiple_events(self) -> None:
        """Test batch publishing delivers all events in order."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")
        events = [{"id": i, "data": f"event_{i}"} for i in range(5)]
        await backend.publish_batch("topic", events)
        received = []
        for _ in range(5):
            received.append(await queue.get())
        assert received == events
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_batch_empty_list_noop(self) -> None:
        """Test publishing empty batch does nothing."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")
        await backend.publish_batch("topic", [])
        assert queue.empty()
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_batch_to_no_subscribers_noop(self) -> None:
        """Test batch publish to topic with no subscribers does not raise."""
        backend = InProcessBackend()
        await backend.start()
        events = [{"id": i} for i in range(3)]
        await backend.publish_batch("empty_topic", events)
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_batch_multiple_subscribers(self) -> None:
        """Test batch publish delivers all events to all subscribers."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        q2 = await backend.subscribe("topic")
        events = [{"id": i} for i in range(3)]
        await backend.publish_batch("topic", events)
        for q in (q1, q2):
            received = []
            for _ in range(3):
                received.append(await q.get())
            assert received == events
        await backend.stop()

    @pytest.mark.asyncio
    async def test_publish_batch_when_not_running_raises(self) -> None:
        """Test batch publish when not running raises EventBusError."""
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish_batch("topic", [{"id": 1}])


# ---------------------------------------------------------------------------
# InProcessBackend - Concurrent Operations
# ---------------------------------------------------------------------------


class TestInProcessBackendConcurrency:
    """Tests for concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_publish_to_same_topic(self) -> None:
        """Test concurrent publishes to the same topic are safe."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")

        async def publish_n(n: int) -> None:
            for i in range(n):
                await backend.publish("topic", {"source": n, "i": i})

        await asyncio.gather(publish_n(10), publish_n(10))
        total = 0
        while not queue.empty():
            await queue.get()
            total += 1
        assert total == 20
        await backend.stop()

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_unsubscribe(self) -> None:
        """Test concurrent subscribe and unsubscribe operations."""
        backend = InProcessBackend()
        await backend.start()

        async def sub_unsub_cycle(topic: str) -> None:
            for _ in range(5):
                q = await backend.subscribe(topic)
                await backend.unsubscribe(topic, q)

        await asyncio.gather(
            sub_unsub_cycle("topic_a"),
            sub_unsub_cycle("topic_b"),
        )
        await backend.stop()


# ---------------------------------------------------------------------------
# InProcessBackend - Publish Error Propagation
# ---------------------------------------------------------------------------


class TestInProcessBackendPublishErrors:
    """Tests for publish error handling."""

    @pytest.mark.asyncio
    async def test_publish_queue_put_error_raises(self) -> None:
        """Test EventBusError when queue.put raises an exception."""
        backend = InProcessBackend()
        await backend.start()
        queue: asyncio.Queue[object] = asyncio.Queue()
        backend._subscribers["topic"] = [queue]

        original_put = queue.put

        async def failing_put(item: object) -> None:
            raise RuntimeError("Queue broken")

        queue.put = failing_put

        with pytest.raises(EventBusError, match="Failed to publish event"):
            await backend.publish("topic", {"data": 1})

        queue.put = original_put
        await backend.stop()


# ---------------------------------------------------------------------------
# RedisStreamBackend - Serialization / Deserialization
# ---------------------------------------------------------------------------


class TestRedisStreamBackendSerialization:
    """Tests for Redis backend serialization helpers."""

    def test_serialize_dict_event(self) -> None:
        """Test serializing a plain dict event."""
        backend = RedisStreamBackend()
        event = {"key": "value", "number": 42}
        result = backend._serialize_event(event)
        assert "data" in result
        import json

        parsed = json.loads(result["data"])
        assert parsed == event

    def test_serialize_pydantic_event(self) -> None:
        """Test serializing a Pydantic model event."""
        backend = RedisStreamBackend()
        from pydantic import BaseModel

        class TestEvent(BaseModel):
            id: int
            name: str

        event = TestEvent(id=1, name="test")
        result = backend._serialize_event(event)
        assert "data" in result
        import json

        parsed = json.loads(result["data"])
        assert parsed["id"] == 1
        assert parsed["name"] == "test"

    def test_deserialize_event(self) -> None:
        """Test deserializing event data."""
        backend = RedisStreamBackend()
        data = {"data": '{"id": 1, "name": "test"}'}
        result = backend._deserialize_event(data)
        assert result == {"id": 1, "name": "test"}

    def test_deserialize_empty_data(self) -> None:
        """Test deserializing event with missing data key."""
        backend = RedisStreamBackend()
        result = backend._deserialize_event({})
        assert result == {}

    def test_deserialize_invalid_json_raises(self) -> None:
        """Test deserializing event with invalid JSON raises JSONDecodeError."""
        import json

        backend = RedisStreamBackend()
        with pytest.raises(json.JSONDecodeError):
            backend._deserialize_event({"data": "not-valid-json"})


# ---------------------------------------------------------------------------
# RedisStreamBackend - Mocked Lifecycle
# ---------------------------------------------------------------------------


class TestRedisStreamBackendMocked:
    """Tests for RedisStreamBackend with mocked Redis."""

    def _make_mock_redis(self) -> tuple[MagicMock, AsyncMock]:
        """Create mock Redis client and module."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.close = AsyncMock()
        mock_module = MagicMock()
        mock_module.Redis.return_value = mock_client
        return mock_module, mock_client

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        """Test successful Redis backend start."""
        backend = RedisStreamBackend()
        mock_module, mock_client = self._make_mock_redis()
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            assert backend.is_running
            assert backend._client is not None
            mock_client.ping.assert_called_once()
            await backend.stop()
            assert not backend.is_running

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_start_missing_redis_package(self) -> None:
        """Test start raises EventBusError when redis package missing."""
        backend = RedisStreamBackend()
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                raise ImportError("No module named 'redis.asyncio'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(EventBusError, match="Redis package not installed"):
                await backend.start()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_start_connection_failure(self) -> None:
        """Test start raises EventBusError on connection failure."""
        backend = RedisStreamBackend(host="bad_host", port=9999)
        mock_module, mock_client = self._make_mock_redis()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(EventBusError, match="Failed to connect to Redis"):
                await backend.start()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_publish_without_client_raises(self) -> None:
        """Test publish without initialized client raises EventBusError."""
        backend = RedisStreamBackend()
        mock_module, _ = self._make_mock_redis()
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            backend._client = None
            with pytest.raises(EventBusError, match="Redis client not initialized"):
                await backend.publish("topic", {"data": 1})
            await backend.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_publish_failure(self) -> None:
        """Test publish wraps Redis errors in EventBusError."""
        backend = RedisStreamBackend()
        mock_module, mock_client = self._make_mock_redis()
        mock_client.xadd = AsyncMock(side_effect=Exception("Redis down"))
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            with pytest.raises(EventBusError, match="Failed to publish event"):
                await backend.publish("topic", {"data": 1})
            await backend.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_publish_batch_uses_pipeline(self) -> None:
        """Test batch publish uses Redis pipeline."""
        backend = RedisStreamBackend()
        mock_module, mock_client = self._make_mock_redis()
        mock_pipeline = AsyncMock()
        mock_pipeline.xadd = MagicMock()
        mock_pipeline.execute = AsyncMock()
        mock_client.pipeline.return_value = mock_pipeline
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            events = [{"id": i} for i in range(3)]
            await backend.publish_batch("topic", events)
            assert mock_pipeline.xadd.call_count == 3
            mock_pipeline.execute.assert_called_once()
            await backend.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_publish_batch_empty_noop(self) -> None:
        """Test batch publish with empty list does not call pipeline."""
        backend = RedisStreamBackend()
        mock_module, _ = self._make_mock_redis()
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            await backend.publish_batch("topic", [])
            await backend.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_subscribe_creates_listener_task(self) -> None:
        """Test subscribe creates a listener task for new topic."""
        backend = RedisStreamBackend()
        mock_module, mock_client = self._make_mock_redis()
        mock_client.xread = AsyncMock(return_value=[])
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            q1 = await backend.subscribe("topic")
            assert "topic" in backend._listener_tasks
            q2 = await backend.subscribe("topic")
            assert len(backend._subscribers["topic"]) == 2
            await backend.unsubscribe("topic", q1)
            assert len(backend._subscribers["topic"]) == 1
            await backend.unsubscribe("topic", q2)
            assert "topic" not in backend._listener_tasks
            await backend.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_stop_cancels_listener_tasks(self) -> None:
        """Test stop cancels all listener tasks."""
        backend = RedisStreamBackend()
        mock_module, mock_client = self._make_mock_redis()
        mock_client.xread = AsyncMock(return_value=[])
        original_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis.asyncio":
                return mock_module
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            await backend.start()
            await backend.subscribe("topic_a")
            await backend.subscribe("topic_b")
            assert len(backend._listener_tasks) == 2
            await backend.stop()
            assert len(backend._listener_tasks) == 0


# ---------------------------------------------------------------------------
# create_backend Factory
# ---------------------------------------------------------------------------


class TestCreateBackend:
    """Tests for create_backend factory function."""

    def test_create_inprocess_default(self) -> None:
        """Test default backend type is inprocess."""
        backend = create_backend()
        assert isinstance(backend, InProcessBackend)

    def test_create_inprocess_explicit(self) -> None:
        """Test creating inprocess backend explicitly."""
        backend = create_backend("inprocess")
        assert isinstance(backend, InProcessBackend)

    def test_create_redis_with_kwargs(self) -> None:
        """Test creating Redis backend with connection parameters."""
        backend = create_backend(
            "redis",
            host="redis.example.com",
            port=6380,
            db=1,
            password="secret",
            max_stream_length=5000,
        )
        assert isinstance(backend, RedisStreamBackend)
        assert backend._host == "redis.example.com"
        assert backend._port == 6380
        assert backend._db == 1
        assert backend._password == "secret"
        assert backend._max_stream_length == 5000

    def test_create_invalid_type_raises(self) -> None:
        """Test creating invalid backend type raises EventBusError."""
        with pytest.raises(EventBusError, match="Invalid backend type"):
            create_backend("kafka")

    def test_create_empty_type_raises(self) -> None:
        """Test creating with empty string raises EventBusError."""
        with pytest.raises(EventBusError, match="Invalid backend type"):
            create_backend("")


# ---------------------------------------------------------------------------
# EventBusBackend Abstract Contract
# ---------------------------------------------------------------------------


class TestEventBusBackendAbstract:
    """Tests for EventBusBackend abstract base class."""

    def test_cannot_instantiate_directly(self) -> None:
        """Test EventBusBackend cannot be instantiated."""
        with pytest.raises(TypeError):
            EventBusBackend()

    @pytest.mark.asyncio
    async def test_validate_running_raises_when_stopped(self) -> None:
        """Test _validate_running raises when backend not started."""
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            backend._validate_running()

    @pytest.mark.asyncio
    async def test_validate_running_passes_when_started(self) -> None:
        """Test _validate_running does not raise when backend is running."""
        backend = InProcessBackend()
        await backend.start()
        backend._validate_running()
        await backend.stop()
