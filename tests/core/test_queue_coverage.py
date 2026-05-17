"""Comprehensive coverage tests for src/iatb/core/queue.py.

This test module targets the remaining uncovered branches and lines
identified in the coverage analysis of queue.py, focusing on:
- InProcessBackend edge branches
- Factory function edge cases
- Error handling paths

NOTE: RedisStreamBackend tests are skipped because Redis is not installed in the
test environment. To run Redis tests, install redis package with:
    poetry add redis
"""

from __future__ import annotations

import asyncio

import pytest
from iatb.core.exceptions import EventBusError
from iatb.core.queue import (
    InProcessBackend,
    RedisStreamBackend,
    create_backend,
)

# ---------------------------------------------------------------------------
# InProcessBackend - Edge Branches
# ---------------------------------------------------------------------------


class TestInProcessBackendEdgeBranches:
    """Tests for uncovered edge branches in InProcessBackend."""

    @pytest.mark.asyncio()
    async def test_unsubscribe_queue_not_in_internal_queues(self) -> None:
        """Cover branch 126->128: queue not in _queues."""
        backend = InProcessBackend()
        await backend.start()
        q1 = await backend.subscribe("topic")
        # Manually remove from _queues to trigger branch
        backend._queues.remove(q1)
        # This should not raise and cover the branch
        await backend.unsubscribe("topic", q1)
        await backend.stop()

    @pytest.mark.asyncio()
    async def test_publish_batch_no_subscribers_no_raise(self) -> None:
        """Cover line 167: publish_batch when topic has no subscribers."""
        backend = InProcessBackend()
        await backend.start()
        q = await backend.subscribe("topic")
        await backend.unsubscribe("topic", q)
        await backend.publish_batch("topic", [{"data": 1}])
        await backend.stop()

    @pytest.mark.asyncio()
    async def test_publish_batch_empty_subscribers_list(self) -> None:
        """Cover lines 173-176: publish_batch iterates over empty queues."""
        backend = InProcessBackend()
        await backend.start()
        q = await backend.subscribe("topic")
        backend._subscribers["topic"].remove(q)
        backend._queues.remove(q)
        await backend.publish_batch("topic", [{"data": 1}])
        await backend.stop()

    @pytest.mark.asyncio()
    async def test_publish_empty_subscribers_list(self) -> None:
        """Cover publish when subscribers list is empty (line 138-139 branch)."""
        backend = InProcessBackend()
        await backend.start()
        q = await backend.subscribe("topic")
        backend._subscribers["topic"].remove(q)
        backend._queues.remove(q)
        await backend.publish("topic", {"data": 1})
        await backend.stop()


# ---------------------------------------------------------------------------
# Factory and Edge Cases
# ---------------------------------------------------------------------------


class TestCreateBackendCoverage:
    """Additional factory tests to ensure full coverage."""

    def test_create_backend_inprocess(self) -> None:
        backend = create_backend("inprocess")
        assert isinstance(backend, InProcessBackend)

    def test_create_backend_redis(self) -> None:
        backend = create_backend("redis", host="custom")
        assert isinstance(backend, RedisStreamBackend)

    def test_create_backend_invalid(self) -> None:
        with pytest.raises(EventBusError, match="Invalid backend type"):
            create_backend("unknown")

    def test_create_backend_default(self) -> None:
        backend = create_backend()
        assert isinstance(backend, InProcessBackend)


class TestMaxQueueSize:
    """Tests for max_queue_size validation (line 81-84)."""

    def test_max_queue_size_zero(self) -> None:
        with pytest.raises(EventBusError, match="positive"):
            InProcessBackend(max_queue_size=0)

    def test_max_queue_size_negative(self) -> None:
        with pytest.raises(EventBusError, match="positive"):
            InProcessBackend(max_queue_size=-5)

    def test_max_queue_size_positive(self) -> None:
        backend = InProcessBackend(max_queue_size=100)
        assert backend._max_queue_size == 100

    def test_default_max_queue_size(self) -> None:
        backend = InProcessBackend()
        assert backend._max_queue_size == 10000


class TestBackendNotRunningErrors:
    """Tests for _validate_running error paths."""

    @pytest.mark.asyncio()
    async def test_inprocess_subscribe_not_running(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.subscribe("topic")

    @pytest.mark.asyncio()
    async def test_inprocess_unsubscribe_not_running(self) -> None:
        backend = InProcessBackend()
        q: asyncio.Queue[object] = asyncio.Queue()
        with pytest.raises(EventBusError, match="not running"):
            await backend.unsubscribe("topic", q)

    @pytest.mark.asyncio()
    async def test_inprocess_publish_not_running(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish("topic", {"data": 1})

    @pytest.mark.asyncio()
    async def test_inprocess_publish_batch_not_running(self) -> None:
        backend = InProcessBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish_batch("topic", [{"data": 1}])

    @pytest.mark.asyncio()
    async def test_redis_subscribe_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.subscribe("topic")

    @pytest.mark.asyncio()
    async def test_redis_unsubscribe_not_running(self) -> None:
        backend = RedisStreamBackend()
        q: asyncio.Queue[object] = asyncio.Queue()
        with pytest.raises(EventBusError, match="not running"):
            await backend.unsubscribe("topic", q)

    @pytest.mark.asyncio()
    async def test_redis_publish_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish("topic", {"data": 1})

    @pytest.mark.asyncio()
    async def test_redis_publish_batch_not_running(self) -> None:
        backend = RedisStreamBackend()
        with pytest.raises(EventBusError, match="not running"):
            await backend.publish_batch("topic", [{"data": 1}])


class TestInProcessBackendConcurrency:
    """Additional concurrency tests for edge coverage."""

    @pytest.mark.asyncio()
    async def test_concurrent_pub_sub(self) -> None:
        """Test concurrent publish and subscribe."""
        backend = InProcessBackend()
        await backend.start()
        queue = await backend.subscribe("topic")

        async def publisher(count: int) -> None:
            for i in range(count):
                await backend.publish("topic", {"i": i})

        await asyncio.gather(publisher(10), publisher(10))
        total = 0
        while not queue.empty():
            await queue.get()
            total += 1
        assert total == 20
        await backend.stop()

    @pytest.mark.asyncio()
    async def test_publish_to_topic_no_subscribers(self) -> None:
        """Test publish to a topic with no subscribers at all."""
        backend = InProcessBackend()
        await backend.start()
        await backend.publish("empty_topic", {"data": 1})
        await backend.stop()

    @pytest.mark.asyncio()
    async def test_publish_batch_to_topic_no_subscribers(self) -> None:
        """Test batch publish to a topic with no subscribers at all."""
        backend = InProcessBackend()
        await backend.start()
        await backend.publish_batch("empty_topic", [{"data": 1}])
        await backend.stop()
