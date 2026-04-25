"""
Tests for event persistence layer.
"""

from pathlib import Path

import pytest
from iatb.core.event_persistence import EventPersistence, PersistedEvent
from iatb.core.exceptions import EventBusError


@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Path:
    """Create temporary storage directory for tests."""
    storage_dir = tmp_path / "events"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


@pytest.fixture
def persistence(temp_storage_dir: Path) -> EventPersistence:
    """Create EventPersistence instance with temporary storage."""
    return EventPersistence(storage_dir=temp_storage_dir)


class TestEventPersistence:
    """Tests for EventPersistence."""

    @pytest.mark.asyncio
    async def test_save_event(self, persistence: EventPersistence) -> None:
        """Test saving an event."""
        test_event = {"data": "test_value", "timestamp": "2024-01-01T00:00:00Z"}

        persisted = await persistence.save_event("test_topic", test_event)

        assert persisted.topic == "test_topic"
        assert persisted.event_data == test_event
        assert persisted.sequence == 1
        assert "test_topic_1_" in persisted.event_id

        # Verify file was created
        topic_dir = persistence._storage_dir / "test_topic"
        assert topic_dir.exists()
        assert len(list(topic_dir.glob("*.json"))) == 1

    @pytest.mark.asyncio
    async def test_save_multiple_events(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test saving multiple events with auto-incrementing sequence."""
        events = [{"id": i, "data": f"event_{i}"} for i in range(5)]

        persisted_events = []
        for event in events:
            persisted = await persistence.save_event("test_topic", event)
            persisted_events.append(persisted)

        assert len(persisted_events) == 5
        assert [p.sequence for p in persisted_events] == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_load_events(self, persistence: EventPersistence) -> None:
        """Test loading events from storage."""
        # Save events
        events = [{"id": i, "data": f"event_{i}"} for i in range(3)]
        for event in events:
            await persistence.save_event("test_topic", event)

        # Load events
        loaded = await persistence.load_events("test_topic")

        assert len(loaded) == 3
        assert [e.event_data for e in loaded] == events

    @pytest.mark.asyncio
    async def test_load_events_with_sequence_range(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test loading events with sequence range filtering."""
        # Save 10 events
        for i in range(10):
            await persistence.save_event("test_topic", {"id": i})

        # Load events from sequence 5 to 7
        loaded = await persistence.load_events("test_topic", start_sequence=5, end_sequence=7)

        assert len(loaded) == 3
        assert [e.sequence for e in loaded] == [5, 6, 7]

    @pytest.mark.asyncio
    async def test_load_events_nonexistent_topic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test loading events for non-existent topic."""
        loaded = await persistence.load_events("nonexistent_topic")
        assert loaded == []

    @pytest.mark.asyncio
    async def test_replay_events(self, persistence: EventPersistence) -> None:
        """Test replaying events with callback."""
        # Save events
        events = [{"id": i, "data": f"event_{i}"} for i in range(3)]
        for event in events:
            await persistence.save_event("test_topic", event)

        # Replay events
        received = []

        async def callback(event_data: dict) -> None:
            received.append(event_data)

        count = await persistence.replay_events("test_topic", callback)

        assert count == 3
        assert received == events

    @pytest.mark.asyncio
    async def test_replay_events_with_delay(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events with delay."""
        import time

        # Save events
        for i in range(3):
            await persistence.save_event("test_topic", {"id": i})

        # Replay with 100ms delay
        received = []

        async def callback(event_data: dict) -> None:
            received.append(event_data)

        start_time = time.time()
        count = await persistence.replay_events("test_topic", callback, delay_ms=100)
        elapsed = time.time() - start_time

        assert count == 3
        assert len(received) == 3
        # Should take at least 200ms (2 delays between 3 events)
        assert elapsed >= 0.2

    @pytest.mark.asyncio
    async def test_replay_events_with_range(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events with sequence range."""
        # Save 10 events
        for i in range(10):
            await persistence.save_event("test_topic", {"id": i})

        # Replay events 5-7
        received = []

        async def callback(event_data: dict) -> None:
            received.append(event_data)

        count = await persistence.replay_events(
            "test_topic",
            callback,
            start_sequence=5,
            end_sequence=7,
        )

        assert count == 3
        assert [e["id"] for e in received] == [4, 5, 6]  # 0-indexed

    @pytest.mark.asyncio
    async def test_replay_events_nonexistent_topic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events for non-existent topic."""
        count = await persistence.replay_events("nonexistent_topic", lambda x: None)
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_events_topic(self, persistence: EventPersistence) -> None:
        """Test clearing events for specific topic."""
        # Save events for two topics
        for i in range(3):
            await persistence.save_event("topic1", {"id": i})
            await persistence.save_event("topic2", {"id": i})

        # Clear topic1
        count = await persistence.clear_events("topic1")
        assert count == 3

        # Verify topic1 is empty, topic2 still has events
        assert await persistence.get_event_count("topic1") == 0
        assert await persistence.get_event_count("topic2") == 3

    @pytest.mark.asyncio
    async def test_clear_events_all(self, persistence: EventPersistence) -> None:
        """Test clearing all events."""
        # Save events for multiple topics
        for topic in ["topic1", "topic2", "topic3"]:
            for i in range(3):
                await persistence.save_event(topic, {"id": i})

        # Clear all events
        count = await persistence.clear_events()
        assert count == 9

        # Verify all topics are empty
        assert await persistence.get_event_count("topic1") == 0
        assert await persistence.get_event_count("topic2") == 0
        assert await persistence.get_event_count("topic3") == 0

    @pytest.mark.asyncio
    async def test_clear_events_nonexistent_topic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test clearing non-existent topic."""
        count = await persistence.clear_events("nonexistent_topic")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_event_count(self, persistence: EventPersistence) -> None:
        """Test getting event count for topic."""
        # Save events
        for i in range(5):
            await persistence.save_event("test_topic", {"id": i})

        count = await persistence.get_event_count("test_topic")
        assert count == 5

    @pytest.mark.asyncio
    async def test_get_event_count_nonexistent_topic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test getting event count for non-existent topic."""
        count = await persistence.get_event_count("nonexistent_topic")
        assert count == 0

    @pytest.mark.asyncio
    async def test_serialize_pydantic_model(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing Pydantic model."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            id: int
            name: str

        model = TestModel(id=1, name="test")
        serialized = persistence._serialize_event(model)

        assert isinstance(serialized, dict)
        assert serialized["id"] == 1
        assert serialized["name"] == "test"

    @pytest.mark.asyncio
    async def test_serialize_dict(self, persistence: EventPersistence) -> None:
        """Test serializing dictionary."""
        data = {"id": 1, "name": "test"}
        serialized = persistence._serialize_event(data)

        assert serialized == data

    @pytest.mark.asyncio
    async def test_serialize_generic_object(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing generic object."""

        class TestObject:
            def __init__(self) -> None:
                self.id = 1
                self.name = "test"

        obj = TestObject()
        serialized = persistence._serialize_event(obj)

        assert isinstance(serialized, dict)
        assert "id" in serialized
        assert "name" in serialized

    @pytest.mark.asyncio
    async def test_deserialize_event(self, persistence: EventPersistence) -> None:
        """Test deserializing event."""
        event_data = {"id": 1, "name": "test"}
        deserialized = persistence._deserialize_event(event_data)

        assert deserialized == event_data

    @pytest.mark.skip(reason="Platform-specific permission test not reliable on Windows")
    @pytest.mark.asyncio
    async def test_save_event_failure(self, persistence: EventPersistence) -> None:
        """Test handling save event failure."""
        import stat

        # Make storage directory read-only
        # Use platform-independent approach
        current_mode = persistence._storage_dir.stat().st_mode
        # Remove write permission for owner, group, and others
        read_only_mode = current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH

        try:
            persistence._storage_dir.chmod(read_only_mode)

            with pytest.raises(EventBusError, match="Failed to save event"):
                await persistence.save_event("test_topic", {"data": "test"})
        finally:
            # Always restore original permissions for cleanup
            # This ensures cleanup works even on Windows
            try:
                persistence._storage_dir.chmod(0o755)
            except Exception:  # noqa: S110, BLE001 - Intentionally ignore restoration errors
                # Ignore permission restoration errors
                pass

    @pytest.mark.asyncio
    async def test_load_corrupted_event(self, persistence: EventPersistence) -> None:
        """Test loading corrupted event file."""
        # Save a valid event
        await persistence.save_event("test_topic", {"id": 1})

        # Corrupt one of the event files
        topic_dir = persistence._storage_dir / "test_topic"
        event_file = next(topic_dir.glob("*.json"))
        event_file.write_text("invalid json", encoding="utf-8")

        # Should skip corrupted file and not raise error
        loaded = await persistence.load_events("test_topic")
        assert len(loaded) == 0


class TestPersistedEvent:
    """Tests for PersistedEvent dataclass."""

    def test_persisted_event_creation(self) -> None:
        """Test creating PersistedEvent."""
        event = PersistedEvent(
            event_id="test_id",
            topic="test_topic",
            timestamp="2024-01-01T00:00:00Z",
            event_data={"data": "test"},
            sequence=1,
        )

        assert event.event_id == "test_id"
        assert event.topic == "test_topic"
        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.event_data == {"data": "test"}
        assert event.sequence == 1
        # Verify event_id is a valid ID (not the builtin id() function)
        assert "test_id" in event.event_id
