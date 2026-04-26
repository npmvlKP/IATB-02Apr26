"""
Tests for event bus implementation.
"""

import asyncio
import random

import numpy as np
import pytest
import torch
from iatb.core.event_bus import EventBus
from iatb.core.events import MarketTickEvent, OrderUpdateEvent
from iatb.core.exceptions import EventBusError
from iatb.core.types import create_price

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


@pytest.fixture
async def event_bus() -> EventBus:
    """Create an event bus instance for testing."""
    bus = EventBus()
    await bus.start()
    yield bus
    await bus.stop()


class TestEventBusLifecycle:
    """Test event bus lifecycle."""

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping event bus."""
        bus = EventBus()
        assert not bus.is_running
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """Test that start can be called multiple times."""
        bus = EventBus()
        await bus.start()
        await bus.start()  # Should not raise
        assert bus.is_running
        await bus.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """Test that stop can be called multiple times."""
        bus = EventBus()
        await bus.start()
        await bus.stop()
        await bus.stop()  # Should not raise
        assert not bus.is_running


class TestEventBusPublishSubscribe:
    """Test event bus publish and subscribe."""

    @pytest.mark.asyncio
    async def test_subscribe(self, event_bus: EventBus) -> None:
        """Test subscribing to a topic."""
        queue = await event_bus.subscribe("test.topic")
        assert isinstance(queue, asyncio.Queue)
        assert queue in event_bus._backend._queues

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus: EventBus) -> None:
        """Test unsubscribing from a topic."""
        queue = await event_bus.subscribe("test.topic")
        await event_bus.unsubscribe("test.topic", queue)
        assert queue not in event_bus._backend._queues

    @pytest.mark.asyncio
    async def test_publish_to_subscriber(self, event_bus: EventBus) -> None:
        """Test publishing an event to a subscriber."""
        queue = await event_bus.subscribe("test.topic")
        event = MarketTickEvent(symbol="TEST", price=create_price("100.0"))

        await event_bus.publish("test.topic", event)

        received = await queue.get()
        assert received.symbol == "TEST"
        assert received.price == create_price("100.0")

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self, event_bus: EventBus) -> None:
        """Test publishing to multiple subscribers."""
        queue1 = await event_bus.subscribe("test.topic")
        queue2 = await event_bus.subscribe("test.topic")

        event = MarketTickEvent(symbol="TEST", price=create_price("100.0"))
        await event_bus.publish("test.topic", event)

        received1 = await queue1.get()
        received2 = await queue2.get()
        assert received1.symbol == "TEST"
        assert received2.symbol == "TEST"

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, event_bus: EventBus) -> None:
        """Test publishing when no subscribers exist."""
        event = MarketTickEvent(symbol="TEST")
        await event_bus.publish("empty.topic", event)  # Should not raise

    @pytest.mark.asyncio
    async def test_publish_not_running(self) -> None:
        """Test publishing when event bus is not running."""
        bus = EventBus()
        event = MarketTickEvent(symbol="TEST")

        with pytest.raises(EventBusError, match="Event bus backend is not running"):
            await bus.publish("test.topic", event)

    @pytest.mark.asyncio
    async def test_publish_batch(self, event_bus: EventBus) -> None:
        """Test batch publishing events."""
        queue = await event_bus.subscribe("test.topic")

        events = [
            MarketTickEvent(symbol=f"SYMBOL{i}", price=create_price(str(i * 100))) for i in range(3)
        ]

        await event_bus.publish_batch("test.topic", events)

        for i in range(3):
            received = await queue.get()
            assert received.symbol == f"SYMBOL{i}"

    @pytest.mark.asyncio
    async def test_publish_batch_empty(self, event_bus: EventBus) -> None:
        """Test batch publishing empty list."""
        await event_bus.publish_batch("test.topic", [])  # Should not raise

    @pytest.mark.asyncio
    async def test_topic_isolation(self, event_bus: EventBus) -> None:
        """Test that different topics are isolated."""
        queue1 = await event_bus.subscribe("topic1")
        queue2 = await event_bus.subscribe("topic2")

        await event_bus.publish("topic1", MarketTickEvent(symbol="TEST1"))
        await event_bus.publish("topic2", MarketTickEvent(symbol="TEST2"))

        received1 = await queue1.get()
        received2 = await queue2.get()
        assert received1.symbol == "TEST1"
        assert received2.symbol == "TEST2"

    @pytest.mark.asyncio
    async def test_different_event_types(self, event_bus: EventBus) -> None:
        """Test publishing different event types."""
        queue = await event_bus.subscribe("mixed.topic")

        tick_event = MarketTickEvent(symbol="TEST", price=create_price("100.0"))
        order_event = OrderUpdateEvent(order_id="ORD123", symbol="TEST")

        await event_bus.publish("mixed.topic", tick_event)
        await event_bus.publish("mixed.topic", order_event)

        received1 = await queue.get()
        received2 = await queue.get()
        assert isinstance(received1, MarketTickEvent)
        assert isinstance(received2, OrderUpdateEvent)

    @pytest.mark.asyncio
    async def test_publish_invalid_event_fails_closed(self, event_bus: EventBus) -> None:
        """Test unsupported payloads are rejected by runtime validation."""
        with pytest.raises(EventBusError, match="Event validation failed"):
            await event_bus.publish("test.topic", {"symbol": "RELIANCE"})

    @pytest.mark.asyncio
    async def test_publish_batch_invalid_event_fails_closed(self, event_bus: EventBus) -> None:
        """Test batch publish rejects invalid payloads before delivery."""
        queue = await event_bus.subscribe("test.topic")
        valid_event = MarketTickEvent(symbol="TEST", price=create_price("100.0"))
        with pytest.raises(EventBusError, match="Event validation failed"):
            await event_bus.publish_batch("test.topic", [valid_event, {"order_id": "ORD-1"}])
        assert queue.empty()

    @pytest.mark.asyncio
    async def test_publish_queue_failure_raises_error(self, event_bus: EventBus) -> None:
        """Test queue put failures are surfaced as EventBusError."""

        class BrokenQueue(asyncio.Queue[MarketTickEvent]):
            async def put(self, item: MarketTickEvent) -> None:
                raise RuntimeError("queue failure")

        event_bus._backend._subscribers["broken.topic"] = [BrokenQueue()]
        with pytest.raises(EventBusError, match="Failed to publish event"):
            await event_bus.publish(
                "broken.topic",
                MarketTickEvent(symbol="TEST", price=create_price("100.0")),
            )

    @pytest.mark.asyncio
    async def test_publish_batch_queue_failure_raises_error(self, event_bus: EventBus) -> None:
        """Test batch queue put failures are surfaced as EventBusError."""

        class BrokenQueue(asyncio.Queue[MarketTickEvent]):
            async def put(self, item: MarketTickEvent) -> None:
                raise RuntimeError("queue failure")

        event_bus._backend._subscribers["broken.topic"] = [BrokenQueue()]
        with pytest.raises(EventBusError, match="Failed to publish batch"):
            await event_bus.publish_batch(
                "broken.topic",
                [MarketTickEvent(symbol="TEST", price=create_price("100.0"))],
            )
