"""
Tests for refactored event bus with backend support.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from iatb.core.event_bus import EventBus
from iatb.core.event_persistence import EventPersistence
from iatb.core.events import MarketTickEvent, OrderUpdateEvent
from iatb.core.exceptions import EventBusError
from iatb.core.queue import InProcessBackend, RedisStreamBackend


class TestEventBusRefactored:
    """Tests for refactored EventBus with backend support."""

    @pytest.mark.asyncio
    async def test_init_with_default_backend(self) -> None:
        """Test EventBus initialization with default backend."""
        bus = EventBus()
        assert isinstance(bus._backend, InProcessBackend)

    @pytest.mark.asyncio
    async def test_init_with_custom_backend(self) -> None:
        """Test EventBus initialization with custom backend."""
        custom_backend = InProcessBackend()
        bus = EventBus(backend=custom_backend)
        assert bus._backend is custom_backend

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test EventBus start and stop lifecycle."""
        bus = EventBus()
        assert not bus.is_running

        await bus.start()
        assert bus.is_running

        await bus.start()  # Should be idempotent
        assert bus.is_running

        await bus.stop()
        assert not bus.is_running

        await bus.stop()  # Should be idempotent
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self) -> None:
        """Test subscribe and unsubscribe functionality."""
        bus = EventBus()
        await bus.start()

        queue = await bus.subscribe("test_topic")
        assert queue is not None

        await bus.unsubscribe("test_topic", queue)

        await bus.stop()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self) -> None:
        """Test publishing and receiving events."""
        bus = EventBus()
        await bus.start()

        queue = await bus.subscribe("test_topic")

        # Create a proper event object
        test_event = MarketTickEvent(symbol="RELIANCE")

        await bus.publish("test_topic", test_event)

        received = await queue.get()
        assert received.symbol == "RELIANCE"
        assert isinstance(received, MarketTickEvent)

        await bus.stop()

    @pytest.mark.asyncio
    async def test_publish_validation(self) -> None:
        """Test that events are validated before publishing."""
        bus = EventBus()
        await bus.start()

        # Invalid event - plain dict without proper structure
        invalid_event = {"invalid": "data"}

        with pytest.raises(EventBusError, match="Event validation failed"):
            await bus.publish("test_topic", invalid_event)

        # Valid event should work
        valid_event = MarketTickEvent(symbol="TCS")
        await bus.publish("test_topic", valid_event)  # Should not raise

        await bus.stop()

    @pytest.mark.asyncio
    async def test_publish_not_running(self) -> None:
        """Test publishing when bus is not running."""
        bus = EventBus()
        # Don't start the bus

        test_event = MarketTickEvent(symbol="INFY")

        with pytest.raises(EventBusError, match="Event bus backend is not running"):
            await bus.publish("test_topic", test_event)

    @pytest.mark.asyncio
    async def test_publish_batch(self) -> None:
        """Test batch publishing."""
        bus = EventBus()
        await bus.start()

        queue = await bus.subscribe("test_topic")

        # Create proper event objects
        events = [
            MarketTickEvent(symbol=f"STOCK{i}", price=Decimal(f"{100 + i}.50")) for i in range(5)
        ]

        await bus.publish_batch("test_topic", events)

        received_events = []
        for _ in range(len(events)):
            received_events.append(await queue.get())

        assert len(received_events) == 5
        for i, event in enumerate(received_events):
            assert isinstance(event, MarketTickEvent)
            assert event.symbol == f"STOCK{i}"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_publish_batch_empty(self) -> None:
        """Test batch publishing with empty list."""
        bus = EventBus()
        await bus.start()

        # Should not raise error
        await bus.publish_batch("test_topic", [])

        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        """Test multiple subscribers receive same event."""
        bus = EventBus()
        await bus.start()

        queue1 = await bus.subscribe("test_topic")
        queue2 = await bus.subscribe("test_topic")
        queue3 = await bus.subscribe("test_topic")

        test_event = OrderUpdateEvent(order_id="ORD-12345", symbol="RELIANCE")
        await bus.publish("test_topic", test_event)

        received1 = await queue1.get()
        received2 = await queue2.get()
        received3 = await queue3.get()

        # All should receive the same event object
        assert isinstance(received1, OrderUpdateEvent)
        assert isinstance(received2, OrderUpdateEvent)
        assert isinstance(received3, OrderUpdateEvent)
        assert received1.order_id == "ORD-12345"
        assert received2.order_id == "ORD-12345"
        assert received3.order_id == "ORD-12345"

        await bus.stop()

    @pytest.mark.skip(reason="Redis lazy import mocking is complex, requires actual Redis package")
    @pytest.mark.asyncio
    async def test_with_redis_backend(self) -> None:
        """Test EventBus with Redis backend."""
        import builtins

        # Create mock Redis class and client
        mock_redis_class = MagicMock()
        mock_client = AsyncMock()
        mock_redis_class.Redis.return_value = mock_client

        # Configure async methods
        mock_client.ping = AsyncMock()
        mock_client.xadd = AsyncMock()
        mock_client.xread = AsyncMock(return_value=[])
        mock_client.close = AsyncMock()

        # Create mock redis.asyncio module
        mock_redis_asyncio = MagicMock()
        mock_redis_asyncio.Redis = mock_redis_class.Redis

        # Patch builtins.__import__ to return mock redis
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "redis.asyncio":
                return mock_redis_asyncio
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            backend = RedisStreamBackend()
            bus = EventBus(backend=backend)

            await bus.start()
            assert bus.is_running

            # Test publish (will use mocked Redis)
            test_event = MarketTickEvent(symbol="TEST")
            await bus.publish("test_topic", test_event)

            assert mock_client.xadd.called

            await bus.stop()
            assert not bus.is_running

    @pytest.mark.asyncio
    async def test_is_running_property(self) -> None:
        """Test is_running property reflects backend state."""
        bus = EventBus()
        assert not bus.is_running

        await bus.start()
        assert bus.is_running

        await bus.stop()
        assert not bus.is_running


class TestEventBusWithPersistence:
    """Tests for EventBus integrated with event persistence."""

    @pytest.mark.asyncio
    async def test_publish_with_persistence(self, tmp_path) -> None:
        """Test publishing events with persistence enabled."""
        bus = EventBus()
        await bus.start()

        persistence = EventPersistence(storage_dir=tmp_path / "events")

        # Subscribe and publish
        await bus.subscribe("test_topic")
        test_event = MarketTickEvent(symbol="RELIANCE", price=Decimal("2500.50"))

        await bus.publish("test_topic", test_event)

        # Persist the event
        await persistence.save_event("test_topic", test_event)

        # Verify persistence
        loaded = await persistence.load_events("test_topic")
        assert len(loaded) == 1
        assert loaded[0].event_data["symbol"] == "RELIANCE"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_replay_events_to_bus(self, tmp_path) -> None:
        """Test replaying persisted events to event bus."""
        persistence = EventPersistence(storage_dir=tmp_path / "events")

        # Save some events as dicts (persistence stores as dicts)
        events = [{"symbol": f"STOCK{i}", "price": f"{100 + i}.50"} for i in range(3)]
        for event in events:
            await persistence.save_event("test_topic", event)

        # Create event bus
        bus = EventBus()
        await bus.start()

        # Subscribe BEFORE replaying to receive events
        queue = await bus.subscribe("test_topic")
        received = []

        async def replay_callback(event_data: dict) -> None:
            # Create proper event object from dict and publish to event bus
            event_obj = MarketTickEvent(
                symbol=event_data["symbol"],
                price=Decimal(str(event_data["price"])),
            )
            await bus.publish("test_topic", event_obj)

        # Replay events to bus (subscriber already waiting)
        count = await persistence.replay_events("test_topic", replay_callback)
        assert count == 3

        # Receive replayed events
        for _ in range(3):
            received.append(await queue.get())

        assert len(received) == 3

        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_topics(self) -> None:
        """Test handling multiple topics."""
        bus = EventBus()
        await bus.start()

        # Subscribe to different topics
        queue1 = await bus.subscribe("topic1")
        queue2 = await bus.subscribe("topic2")
        queue3 = await bus.subscribe("topic3")

        # Publish to each topic
        await bus.publish("topic1", MarketTickEvent(symbol="RELIANCE"))
        await bus.publish("topic2", MarketTickEvent(symbol="TCS"))
        await bus.publish("topic3", MarketTickEvent(symbol="INFY"))

        # Verify each queue receives only its topic's events
        event1 = await queue1.get()
        event2 = await queue2.get()
        event3 = await queue3.get()

        assert event1.symbol == "RELIANCE"
        assert event2.symbol == "TCS"
        assert event3.symbol == "INFY"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_high_throughput(self) -> None:
        """Test handling high throughput of events."""
        bus = EventBus()
        await bus.start()

        queue = await bus.subscribe("test_topic")

        # Publish many events
        num_events = 100
        events = [
            MarketTickEvent(symbol=f"STOCK{i}", price=Decimal(f"{100 + i}.50"))
            for i in range(num_events)
        ]

        # Publish in batch
        await bus.publish_batch("test_topic", events)

        # Receive all events
        received = []
        for _ in range(num_events):
            received.append(await queue.get())

        assert len(received) == num_events
        for i, event in enumerate(received):
            assert event.symbol == f"STOCK{i}"

        await bus.stop()
