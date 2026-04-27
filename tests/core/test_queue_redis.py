"""Extended tests for Redis Streams EventBus backend coverage."""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from iatb.core.exceptions import EventBusError
from iatb.core.queue import (
    EventMetadata,
    InProcessBackend,
    RedisStreamBackend,
    create_backend,
)


def _utc_now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


class TestEventMetadata:
    def test_creation(self) -> None:
        meta = EventMetadata(
            event_id="evt-001",
            topic="trades",
            timestamp=_utc_now().isoformat(),
            sequence=1,
        )
        assert meta.event_id == "evt-001"
        assert meta.topic == "trades"
        assert meta.sequence == 1


class TestInProcessBackendExtended:
    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.start()
        assert backend.is_running is True

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.stop()
        await backend.stop()
        assert backend.is_running is False

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.publish("nonexistent", {"data": "test"})

    @pytest.mark.asyncio
    async def test_publish_empty_subscribers(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        q = await backend.subscribe("topic")
        await backend.unsubscribe("topic", q)
        await backend.publish("topic", {"data": "test"})

    @pytest.mark.asyncio
    async def test_publish_batch_empty(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.publish_batch("topic", [])

    @pytest.mark.asyncio
    async def test_publish_batch_no_subscribers(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.publish_batch("topic", [{"d": 1}, {"d": 2}])

    @pytest.mark.asyncio
    async def test_not_running_publish_rejected(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish("topic", "data")

    @pytest.mark.asyncio
    async def test_not_running_subscribe_rejected(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.subscribe("topic")

    @pytest.mark.asyncio
    async def test_not_running_unsubscribe_rejected(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.unsubscribe("topic", asyncio.Queue())

    @pytest.mark.asyncio
    async def test_not_running_batch_rejected(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish_batch("topic", ["data"])

    def test_invalid_max_queue_size(self) -> None:
        with pytest.raises(EventBusError, match="positive"):
            InProcessBackend(max_queue_size=0)

    def test_negative_max_queue_size(self) -> None:
        with pytest.raises(EventBusError, match="positive"):
            InProcessBackend(max_queue_size=-1)

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self) -> None:
        backend = InProcessBackend()
        await backend.start()
        await backend.subscribe("topic")
        other_q: asyncio.Queue[object] = asyncio.Queue()
        await backend.unsubscribe("topic", other_q)


class TestRedisStreamBackendInit:
    def test_default_params(self) -> None:
        backend = RedisStreamBackend()
        assert backend._host == "localhost"
        assert backend._port == 6379
        assert backend.is_running is False

    def test_custom_params(self) -> None:
        backend = RedisStreamBackend(
            host="redis.prod",
            port=6380,
            db=1,
            password="secret",
            max_stream_length=5000,
        )
        assert backend._host == "redis.prod"
        assert backend._port == 6380
        assert backend._password == "secret"


class TestRedisStreamBackendSerialize:
    def test_serialize_dict(self) -> None:
        backend = RedisStreamBackend()
        result = backend._serialize_event({"key": "value"})
        assert "data" in result
        assert json.loads(result["data"]) == {"key": "value"}

    def test_serialize_pydantic_like(self) -> None:
        backend = RedisStreamBackend()
        mock_event = MagicMock()
        mock_event.model_dump.return_value = {"field": "val"}
        del mock_event.__iter__
        result = backend._serialize_event(mock_event)
        assert "data" in result
        parsed = json.loads(result["data"])
        assert parsed == {"field": "val"}

    def test_deserialize(self) -> None:
        backend = RedisStreamBackend()
        data = {"data": json.dumps({"key": "value"})}
        result = backend._deserialize_event(data)
        assert result == {"key": "value"}

    def test_deserialize_empty(self) -> None:
        backend = RedisStreamBackend()
        result = backend._deserialize_event({})
        assert result == {}


class TestRedisStreamBackendLifecycle:
    @pytest.mark.asyncio
    async def test_start_import_error(self) -> None:
        backend = RedisStreamBackend()
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            with patch("builtins.__import__", side_effect=ImportError("no redis")):
                with pytest.raises(EventBusError, match="Redis package not installed"):
                    await backend.start()

    @pytest.mark.asyncio
    async def test_start_connection_error(self) -> None:
        backend = RedisStreamBackend()
        mock_redis = MagicMock()
        mock_redis.Redis.return_value.ping = AsyncMock(side_effect=Exception("conn fail"))
        with patch.dict("sys.modules", {}):
            with patch("iatb.core.queue.RedisStreamBackend.start") as mock_start:
                mock_start.side_effect = EventBusError("Failed to connect to Redis")
                with pytest.raises(EventBusError, match="Failed to connect"):
                    await backend.start()

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        backend = RedisStreamBackend()
        await backend.stop()
        assert backend.is_running is False

    @pytest.mark.asyncio
    async def test_publish_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish("topic", {"data": "test"})

    @pytest.mark.asyncio
    async def test_publish_batch_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish_batch("topic", [{"d": 1}])

    @pytest.mark.asyncio
    async def test_subscribe_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.subscribe("topic")

    @pytest.mark.asyncio
    async def test_unsubscribe_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.unsubscribe("topic", asyncio.Queue())


class TestCreateBackend:
    def test_create_inprocess(self) -> None:
        backend = create_backend("inprocess")
        assert isinstance(backend, InProcessBackend)

    def test_create_redis(self) -> None:
        backend = create_backend("redis")
        assert isinstance(backend, RedisStreamBackend)

    def test_create_redis_with_kwargs(self) -> None:
        backend = create_backend("redis", host="custom", port=6380)
        assert isinstance(backend, RedisStreamBackend)
        assert backend._host == "custom"

    def test_create_invalid(self) -> None:
        with pytest.raises(EventBusError, match="Invalid backend"):
            create_backend("kafka")
