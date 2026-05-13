"""
Comprehensive coverage tests for event_persistence.py.

Target coverage: 15.07% for src/iatb/core/event_persistence.py (496 LOC)
Test file: tests/core/test_event_persistence_coverage.py
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
from iatb.core.event_persistence import (
    EventPersistence,
    PersistedEvent,
    _parse_event_file,
)
from iatb.core.events import (
    MarketTickEvent,
    OrderUpdateEvent,
    PnLUpdateEvent,
    RegimeChangeEvent,
    ScanUpdateEvent,
    SignalEvent,
)
from iatb.core.exceptions import EventBusError
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)


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


@pytest.fixture
def sample_market_tick_event() -> MarketTickEvent:
    """Fixture providing valid MarketTickEvent."""
    return MarketTickEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        exchange=Exchange.NSE,
        symbol="NIFTY50",
        price=create_price("22500.50"),
        quantity=create_quantity("100"),
        volume=create_quantity("1000"),
        bid_price=create_price("22500.00"),
        ask_price=create_price("22501.00"),
    )


@pytest.fixture
def sample_order_update_event() -> OrderUpdateEvent:
    """Fixture providing valid OrderUpdateEvent."""
    return OrderUpdateEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        order_id="ORD-12345",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=create_quantity("100"),
        price=create_price("100.50"),
        filled_quantity=create_quantity("100"),
        avg_price=create_price("100.50"),
        status=OrderStatus.FILLED,
    )


@pytest.fixture
def sample_signal_event() -> SignalEvent:
    """Fixture providing valid SignalEvent."""
    return SignalEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        strategy_id="STRATEGY-001",
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=create_quantity("100"),
        price=create_price("100.50"),
        confidence=Decimal("0.75"),
    )


@pytest.fixture
def sample_regime_change_event() -> RegimeChangeEvent:
    """Fixture providing valid RegimeChangeEvent."""
    return RegimeChangeEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        regime_type="VOLATILITY_SPIKE",
        description="Volatility increasing",
        confidence=Decimal("0.85"),
        metadata={"key1": "value1", "key2": "value2"},
    )


@pytest.fixture
def sample_scan_update_event() -> ScanUpdateEvent:
    """Fixture providing valid ScanUpdateEvent."""
    return ScanUpdateEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        total_candidates=100,
        approved_candidates=80,
        trades_executed=50,
        duration_ms=1000,
        errors=[],
    )


@pytest.fixture
def sample_pnl_update_event() -> PnLUpdateEvent:
    """Fixture providing valid PnLUpdateEvent."""
    return PnLUpdateEvent(
        event_id=uuid4(),
        timestamp=create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC)),
        order_id="ORD-12345",
        symbol="RELIANCE",
        side="BUY",
        quantity=create_quantity("100"),
        price=create_price("100.50"),
        trade_pnl=Decimal("-50.00"),
        cumulative_pnl=Decimal("1000.00"),
    )


class TestEventPersistenceSaveEvent:
    """Tests for EventPersistence.save_event()."""

    @pytest.mark.asyncio
    async def test_save_event_creates_json_file(
        self,
        persistence: EventPersistence,
        sample_market_tick_event: MarketTickEvent,
    ) -> None:
        """Test saving event creates JSON file with correct structure."""
        persisted = await persistence.save_event("market", sample_market_tick_event)

        assert persisted.topic == "market"
        assert persisted.sequence == 1
        assert "market_1_" in persisted.event_id

        topic_dir = persistence._storage_dir / "market"
        assert topic_dir.exists()
        event_files = list(topic_dir.glob("*.json"))
        assert len(event_files) == 1

        event_file = event_files[0]
        assert event_file.name == f"{persisted.event_id}.json"

    @pytest.mark.asyncio
    async def test_save_event_with_pydantic_model(
        self,
        persistence: EventPersistence,
        sample_market_tick_event: MarketTickEvent,
    ) -> None:
        """Test saving Pydantic model event."""
        persisted = await persistence.save_event("market", sample_market_tick_event)

        assert persisted.event_data["_event_type"] == "MarketTickEvent"
        assert persisted.event_data["symbol"] == "NIFTY50"
        assert persisted.event_data["price"] == Decimal("22500.50")

    @pytest.mark.asyncio
    async def test_save_event_with_plain_dict(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test saving plain dict event."""
        event_dict = {"key": "value", "number": 42}
        persisted = await persistence.save_event("test", event_dict)

        assert persisted.event_data == event_dict

    @pytest.mark.asyncio
    async def test_save_event_failure_raises_event_bus_error(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test save event failure raises EventBusError."""
        with patch.object(Path, "open", side_effect=PermissionError("Access denied")):
            with pytest.raises(EventBusError, match="Failed to save event"):
                await persistence.save_event("test", {"data": "test"})


class TestEventPersistenceLoadEvents:
    """Tests for EventPersistence.load_events()."""

    @pytest.mark.asyncio
    async def test_load_events_returns_sorted_by_sequence(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test loading events returns list sorted by sequence."""
        for i in range(5):
            await persistence.save_event("test", {"id": i})

        loaded = await persistence.load_events("test")

        assert len(loaded) == 5
        assert [e.sequence for e in loaded] == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_load_events_with_sequence_range_filtering(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test loading events with start_sequence/end_sequence filtering."""
        for i in range(10):
            await persistence.save_event("test", {"id": i})

        loaded = await persistence.load_events("test", start_sequence=5, end_sequence=7)

        assert len(loaded) == 3
        assert [e.sequence for e in loaded] == [5, 6, 7]

    @pytest.mark.asyncio
    async def test_load_events_nonexistent_topic_returns_empty_list(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test loading events for non-existent topic returns empty list."""
        loaded = await persistence.load_events("nonexistent_topic")
        assert loaded == []

    @pytest.mark.asyncio
    async def test_load_events_failure_raises_event_bus_error(
        self,
        persistence: EventPersistence,
        temp_storage_dir: Path,
    ) -> None:
        """Test load events failure raises EventBusError."""
        # Create topic directory first so it exists
        topic_dir = temp_storage_dir / "test"
        topic_dir.mkdir(exist_ok=True)

        # Save an event first
        await persistence.save_event("test", {"id": 1})

        # Then patch glob to raise error
        with patch.object(Path, "glob", side_effect=PermissionError("Access denied")):
            with pytest.raises(EventBusError, match="Failed to load events"):
                await persistence.load_events("test")


class TestEventPersistenceReplayEvents:
    """Tests for EventPersistence.replay_events()."""

    @pytest.mark.asyncio
    async def test_replay_events_invokes_callback_with_deserialized_objects(
        self,
        persistence: EventPersistence,
        sample_market_tick_event: MarketTickEvent,
    ) -> None:
        """Test replaying events invokes callback with deserialized event objects."""
        await persistence.save_event("market", sample_market_tick_event)

        received = []

        async def callback(event: Any) -> None:
            received.append(event)

        count = await persistence.replay_events("market", callback)

        assert count == 1
        assert len(received) == 1
        assert isinstance(received[0], MarketTickEvent)
        assert received[0].symbol == "NIFTY50"

    @pytest.mark.asyncio
    async def test_replay_events_with_delay_ms(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events with delay_ms > 0."""
        import time

        for i in range(3):
            await persistence.save_event("test", {"id": i})

        received = []

        async def callback(event: Any) -> None:
            received.append(event)

        start_time = time.time()
        count = await persistence.replay_events("test", callback, delay_ms=100)
        elapsed = time.time() - start_time

        assert count == 3
        assert len(received) == 3
        assert elapsed >= 0.2

    @pytest.mark.asyncio
    async def test_replay_single_event_failure_returns_false(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replay single event failure returns False, count not incremented."""
        await persistence.save_event("test", {"id": 1})

        async def failing_callback(event: Any) -> None:
            raise RuntimeError("Callback failed")

        count = await persistence.replay_events("test", failing_callback)

        assert count == 0


class TestEventPersistenceClearEvents:
    """Tests for EventPersistence.clear_events()."""

    @pytest.mark.asyncio
    async def test_clear_events_for_specific_topic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test clearing events for specific topic."""
        for i in range(3):
            await persistence.save_event("topic1", {"id": i})
            await persistence.save_event("topic2", {"id": i})

        count = await persistence.clear_events("topic1")

        assert count == 3
        assert await persistence.get_event_count("topic1") == 0
        assert await persistence.get_event_count("topic2") == 3

    @pytest.mark.asyncio
    async def test_clear_events_all_topics(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test clearing all events."""
        for topic in ["topic1", "topic2", "topic3"]:
            for i in range(3):
                await persistence.save_event(topic, {"id": i})

        count = await persistence.clear_events()

        assert count == 9
        assert await persistence.get_event_count("topic1") == 0
        assert await persistence.get_event_count("topic2") == 0
        assert await persistence.get_event_count("topic3") == 0


class TestEventPersistenceGetEventCount:
    """Tests for EventPersistence.get_event_count()."""

    @pytest.mark.asyncio
    async def test_get_event_count_returns_correct_count(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test get_event_count returns correct count for topic."""
        for i in range(5):
            await persistence.save_event("test", {"id": i})

        count = await persistence.get_event_count("test")
        assert count == 5


class TestSerializeEvent:
    """Tests for _serialize_event()."""

    def test_serialize_pydantic_model_with_model_dump(
        self,
        persistence: EventPersistence,
        sample_market_tick_event: MarketTickEvent,
    ) -> None:
        """Test serializing Pydantic model with model_dump."""
        serialized = persistence._serialize_event(sample_market_tick_event)

        assert isinstance(serialized, dict)
        assert serialized["_event_type"] == "MarketTickEvent"
        assert serialized["symbol"] == "NIFTY50"

    def test_serialize_plain_dict(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing plain dict."""
        data = {"key": "value", "number": 42}
        serialized = persistence._serialize_event(data)

        assert serialized == data

    def test_serialize_object_with_dict(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing object with __dict__."""

        class TestObject:
            def __init__(self) -> None:
                self.id = 1
                self.name = "test"

        obj = TestObject()
        serialized = persistence._serialize_event(obj)

        assert isinstance(serialized, dict)
        assert serialized["id"] == 1
        assert serialized["name"] == "test"
        assert serialized["_event_type"] == "TestObject"


class TestDeserializeEvent:
    """Tests for _deserialize_event()."""

    def test_deserialize_market_tick_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing MarketTickEvent."""
        event_data = {
            "_event_type": "MarketTickEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "exchange": "NSE",
            "symbol": "NIFTY50",
            "price": "22500.50",
            "quantity": "100",
            "volume": "1000",
            "bid_price": "22500.00",
            "ask_price": "22501.00",
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, MarketTickEvent)
        assert deserialized.symbol == "NIFTY50"
        assert str(deserialized.price) == "22500.50"

    def test_deserialize_order_update_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing OrderUpdateEvent."""
        event_data = {
            "_event_type": "OrderUpdateEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "order_id": "ORD-12345",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": "100",
            "price": "100.50",
            "filled_quantity": "100",
            "avg_price": "100.50",
            "status": "FILLED",
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, OrderUpdateEvent)
        assert deserialized.order_id == "ORD-12345"
        assert deserialized.status == OrderStatus.FILLED

    def test_deserialize_signal_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing SignalEvent."""
        event_data = {
            "_event_type": "SignalEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "strategy_id": "STRATEGY-001",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "100",
            "price": "100.50",
            "confidence": "0.75",
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, SignalEvent)
        assert deserialized.strategy_id == "STRATEGY-001"
        assert deserialized.confidence == Decimal("0.75")

    def test_deserialize_regime_change_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing RegimeChangeEvent."""
        event_data = {
            "_event_type": "RegimeChangeEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "regime_type": "VOLATILITY_SPIKE",
            "description": "Volatility increasing",
            "confidence": "0.85",
            "metadata": {"key1": "value1", "key2": "value2"},
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, RegimeChangeEvent)
        assert deserialized.regime_type == "VOLATILITY_SPIKE"
        assert deserialized.confidence == Decimal("0.85")

    def test_deserialize_scan_update_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing ScanUpdateEvent."""
        event_data = {
            "_event_type": "ScanUpdateEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "total_candidates": 100,
            "approved_candidates": 80,
            "trades_executed": 50,
            "duration_ms": 1000,
            "errors": [],
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, ScanUpdateEvent)
        assert deserialized.total_candidates == 100
        assert deserialized.trades_executed == 50

    def test_deserialize_pnl_update_event(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing PnLUpdateEvent."""
        event_data = {
            "_event_type": "PnLUpdateEvent",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "order_id": "ORD-12345",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "100",
            "price": "100.50",
            "trade_pnl": "-50.00",
            "cumulative_pnl": "1000.00",
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, PnLUpdateEvent)
        assert deserialized.order_id == "ORD-12345"
        assert deserialized.trade_pnl == Decimal("-50.00")

    def test_deserialize_event_without_type_returns_data(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing event without _event_type returns data as-is."""
        event_data = {"key": "value", "number": 42}
        deserialized = persistence._deserialize_event(event_data)

        assert deserialized == event_data


class TestParseEventFile:
    """Tests for _parse_event_file()."""

    def test_parse_event_file_with_invalid_json_returns_none(
        self,
        temp_storage_dir: Path,
    ) -> None:
        """Test parsing event file with invalid JSON returns None."""
        event_file = temp_storage_dir / "invalid.json"
        event_file.write_text("invalid json", encoding="utf-8")

        result = _parse_event_file(event_file, 0, None)

        assert result is None

    def test_parse_event_file_filters_by_sequence_range(
        self,
        temp_storage_dir: Path,
    ) -> None:
        """Test parsing event file filters by sequence range."""
        import json

        event_file = temp_storage_dir / "test.json"
        event_data = {
            "event_id": "test_1_1234567890",
            "topic": "test",
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
            "event_data": {"id": 1},
            "sequence": 5,
        }
        event_file.write_text(json.dumps(event_data), encoding="utf-8")

        result = _parse_event_file(event_file, 10, None)

        assert result is None

        result = _parse_event_file(event_file, 0, 10)

        assert result is not None
        assert result.sequence == 5


class TestTypeConversionHelpers:
    """Tests for type conversion helper methods."""

    def test_to_uuid_with_string(self, persistence: EventPersistence) -> None:
        """Test _to_uuid with string input."""
        test_uuid = uuid4()
        result = persistence._to_uuid(str(test_uuid))

        assert isinstance(result, UUID)
        assert result == test_uuid

    def test_to_uuid_with_uuid(self, persistence: EventPersistence) -> None:
        """Test _to_uuid with UUID input."""
        test_uuid = uuid4()
        result = persistence._to_uuid(test_uuid)

        assert result == test_uuid

    def test_to_datetime_with_string(self, persistence: EventPersistence) -> None:
        """Test _to_datetime with string input."""
        dt_str = "2024-01-01T09:30:00+00:00"
        result = persistence._to_datetime(dt_str)

        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_to_datetime_with_datetime(self, persistence: EventPersistence) -> None:
        """Test _to_datetime with datetime input."""
        dt = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        result = persistence._to_datetime(dt)

        assert result == dt

    def test_to_decimal_with_string(self, persistence: EventPersistence) -> None:
        """Test _to_decimal with string input."""
        result = persistence._to_decimal("100.50")

        assert isinstance(result, Decimal)
        assert result == Decimal("100.50")

    def test_to_decimal_with_none(self, persistence: EventPersistence) -> None:
        """Test _to_decimal with None input."""
        result = persistence._to_decimal(None)

        assert result == Decimal("0")

    def test_to_price_with_string(self, persistence: EventPersistence) -> None:
        """Test _to_price with string input."""
        result = persistence._to_price("100.50")

        assert str(result) == "100.50"

    def test_to_quantity_with_string(self, persistence: EventPersistence) -> None:
        """Test _to_quantity with string input."""
        result = persistence._to_quantity("100")

        assert str(result) == "100"

    def test_to_timestamp_with_datetime(self, persistence: EventPersistence) -> None:
        """Test _to_timestamp with datetime input."""
        dt = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        result = persistence._to_timestamp(dt)

        assert result == dt


class TestPersistedEventDataclass:
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


class TestEventPersistenceIntegration:
    """Integration tests for EventPersistence."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_save_load_replay(
        self,
        persistence: EventPersistence,
        sample_market_tick_event: MarketTickEvent,
    ) -> None:
        """Test full lifecycle: save, load, replay."""
        await persistence.save_event("market", sample_market_tick_event)

        loaded = await persistence.load_events("market")
        assert len(loaded) == 1

        received = []

        async def callback(event: Any) -> None:
            received.append(event)

        count = await persistence.replay_events("market", callback)

        assert count == 1
        assert len(received) == 1
        assert isinstance(received[0], MarketTickEvent)

    @pytest.mark.asyncio
    async def test_multiple_topics_isolation(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test that multiple topics are properly isolated."""
        await persistence.save_event("topic1", {"id": 1})
        await persistence.save_event("topic2", {"id": 2})

        topic1_events = await persistence.load_events("topic1")
        topic2_events = await persistence.load_events("topic2")

        assert len(topic1_events) == 1
        assert len(topic2_events) == 1
        assert topic1_events[0].event_data["id"] == 1
        assert topic2_events[0].event_data["id"] == 2


class TestEventPersistenceReplayEventsEdgeCases:
    """Additional tests for replay_events edge cases."""

    @pytest.mark.asyncio
    async def test_replay_events_with_synchronous_callback(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events with synchronous (non-async) callback."""
        await persistence.save_event("test", {"id": 1})

        received = []

        def sync_callback(event: Any) -> None:
            received.append(event)

        count = await persistence.replay_events("test", sync_callback)

        assert count == 1
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_replay_events_no_events_returns_zero(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test replaying events when no events exist returns 0."""
        received = []

        async def callback(event: Any) -> None:
            received.append(event)

        count = await persistence.replay_events("nonexistent", callback)

        assert count == 0
        assert len(received) == 0


class TestEventPersistenceClearEventsEdgeCases:
    """Additional tests for clear_events edge cases."""

    @pytest.mark.asyncio
    async def test_clear_events_nonexistent_topic_returns_zero(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test clearing events for non-existent topic returns 0."""
        count = await persistence.clear_events("nonexistent_topic")
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_events_empty_directory(
        self,
        persistence: EventPersistence,
        temp_storage_dir: Path,
    ) -> None:
        """Test clearing events when storage is empty."""
        # Create topic directory but no events
        topic_dir = temp_storage_dir / "empty_topic"
        topic_dir.mkdir(exist_ok=True)

        count = await persistence.clear_events()
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_events_failure_raises_event_bus_error(
        self,
        persistence: EventPersistence,
        temp_storage_dir: Path,
    ) -> None:
        """Test clear events failure raises EventBusError."""
        # Create topic directory with events
        topic_dir = temp_storage_dir / "test"
        topic_dir.mkdir(exist_ok=True)
        (topic_dir / "event.json").write_text('{"test": "data"}', encoding="utf-8")

        # Patch unlink to raise error
        with patch.object(Path, "unlink", side_effect=PermissionError("Access denied")):
            with pytest.raises(EventBusError, match="Failed to clear events"):
                await persistence.clear_events("test")


class TestEventPersistenceGetEventCountEdgeCases:
    """Additional tests for get_event_count edge cases."""

    @pytest.mark.asyncio
    async def test_get_event_count_nonexistent_topic_returns_zero(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test get_event_count for non-existent topic returns 0."""
        count = await persistence.get_event_count("nonexistent_topic")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_event_count_exception_returns_zero(
        self,
        persistence: EventPersistence,
        temp_storage_dir: Path,
    ) -> None:
        """Test get_event_count returns 0 on exception."""
        # Create topic directory
        topic_dir = temp_storage_dir / "test"
        topic_dir.mkdir(exist_ok=True)

        # Patch glob to raise error
        with patch.object(Path, "glob", side_effect=PermissionError("Access denied")):
            count = await persistence.get_event_count("test")
            assert count == 0


class TestSerializeEventEdgeCases:
    """Additional tests for _serialize_event edge cases."""

    def test_serialize_model_dump_returns_non_dict(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing when model_dump returns non-dict."""

        class NonDictModel:
            def model_dump(self) -> str:
                return "not a dict"

        obj = NonDictModel()
        serialized = persistence._serialize_event(obj)

        assert serialized == {"data": "not a dict", "_event_type": "NonDictModel"}

    def test_serialize_object_dict_returns_non_dict(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing when __dict__ returns non-dict."""

        class NonDictObject:
            @property
            def __dict__(self) -> str:  # type: ignore[override]
                return "not a dict"

        obj = NonDictObject()
        serialized = persistence._serialize_event(obj)

        assert serialized == {"data": str(obj), "_event_type": "NonDictObject"}

    def test_serialize_unknown_type_fallback(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test serializing unknown type uses fallback."""
        obj = 12345  # int has no model_dump, __dict__, or is dict
        serialized = persistence._serialize_event(obj)

        assert serialized == {"data": "12345", "_event_type": "unknown"}


class TestDeserializeEventHeuristics:
    """Tests for event type detection heuristics."""

    def test_deserialize_by_order_update_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing OrderUpdateEvent via heuristic."""
        event_data = {
            "quantity": "100",  # Add quantity to satisfy validation
            "filled_quantity": "100",
            "order_id": "ORD-12345",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, OrderUpdateEvent)
        assert deserialized.order_id == "ORD-12345"

    def test_deserialize_by_signal_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing SignalEvent via heuristic."""
        event_data = {
            "strategy_id": "STRATEGY-001",
            "confidence": "0.75",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, SignalEvent)
        assert deserialized.strategy_id == "STRATEGY-001"

    def test_deserialize_by_regime_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing RegimeChangeEvent via heuristic."""
        event_data = {
            "regime_type": "VOLATILITY_SPIKE",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, RegimeChangeEvent)
        assert deserialized.regime_type == "VOLATILITY_SPIKE"

    def test_deserialize_by_scan_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing ScanUpdateEvent via heuristic."""
        event_data = {
            "total_candidates": 100,
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, ScanUpdateEvent)
        assert deserialized.total_candidates == 100

    def test_deserialize_by_pnl_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing PnLUpdateEvent via heuristic."""
        event_data = {
            "trade_pnl": "-50.00",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, PnLUpdateEvent)
        assert deserialized.trade_pnl == Decimal("-50.00")

    def test_deserialize_by_market_tick_heuristic(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing MarketTickEvent via heuristic."""
        event_data = {
            "bid_price": "22500.00",
            "ask_price": "22501.00",
            "event_id": str(uuid4()),
            "timestamp": datetime(2024, 1, 1, 9, 30, tzinfo=UTC).isoformat(),
        }

        deserialized = persistence._deserialize_event(event_data)

        assert isinstance(deserialized, MarketTickEvent)

    def test_deserialize_unknown_event_type_fallback(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test deserializing unknown event type returns data as-is."""
        event_data = {
            "unknown_field": "value",
            "another_field": 123,
        }

        deserialized = persistence._deserialize_event(event_data)

        assert deserialized == event_data


class TestTypeConversionHelpersEdgeCases:
    """Additional tests for type conversion helper edge cases."""

    def test_to_datetime_invalid_string_raises_type_error(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_datetime with invalid string raises TypeError."""
        with pytest.raises(TypeError, match="Cannot convert"):
            persistence._to_datetime(12345)  # type: ignore[arg-type]

    def test_to_decimal_with_decimal_input(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_decimal with Decimal input."""
        dec = Decimal("100.50")
        result = persistence._to_decimal(dec)

        assert result == dec

    def test_to_decimal_with_numeric_string(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_decimal with numeric string."""
        result = persistence._to_decimal("100.50")

        assert result == Decimal("100.50")

    def test_to_price_with_price_input(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_price with Price input."""
        price = create_price("100.50")
        result = persistence._to_price(price)

        assert str(result) == "100.50"

    def test_to_quantity_with_quantity_input(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_quantity with Quantity input."""
        quantity = create_quantity("100")
        result = persistence._to_quantity(quantity)

        assert str(result) == "100"

    def test_to_timestamp_with_timestamp_input(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_timestamp with Timestamp input."""
        ts = create_timestamp(datetime(2024, 1, 1, 9, 30, tzinfo=UTC))
        result = persistence._to_timestamp(ts)

        assert result == ts

    def test_to_timestamp_with_string_input(
        self,
        persistence: EventPersistence,
    ) -> None:
        """Test _to_timestamp with string input."""
        ts_str = "2024-01-01T09:30:00+00:00"
        result = persistence._to_timestamp(ts_str)

        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1
