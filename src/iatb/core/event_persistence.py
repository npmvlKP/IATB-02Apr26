"""
Event persistence layer for replay capability.

Provides storage and retrieval of events for debugging, testing,
and replay scenarios.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iatb.core.exceptions import EventBusError
from iatb.core.types import create_timestamp

logger = logging.getLogger(__name__)


@dataclass
class PersistedEvent:
    """Persisted event with metadata."""

    event_id: str
    topic: str
    timestamp: str
    event_data: dict[str, Any]
    sequence: int


def _parse_event_file(
    event_file: Path,
    start_sequence: int,
    end_sequence: int | None,
) -> PersistedEvent | None:
    try:
        with event_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        persisted = PersistedEvent(
            event_id=data["event_id"],
            topic=data["topic"],
            timestamp=data["timestamp"],
            event_data=data["event_data"],
            sequence=data["sequence"],
        )
        if persisted.sequence < start_sequence:
            return None
        if end_sequence is not None and persisted.sequence > end_sequence:
            return None
        return persisted
    except Exception as exc:
        logger.error("Error loading event file %s: %s", event_file, exc)
        return None


class EventPersistence:
    """Event persistence manager for storage and replay."""

    def __init__(self, storage_dir: str | Path = "data/events") -> None:
        """Initialize the event persistence manager.

        Args:
            storage_dir: Directory for event storage.
        """
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._sequence_counter = 0

    async def save_event(self, topic: str, event: Any) -> PersistedEvent:
        """Save an event to persistent storage.

        Args:
            topic: Event topic.
            event: Event object to persist.

        Returns:
            PersistedEvent instance with metadata.
        """
        try:
            self._sequence_counter += 1
            ts_ms = int(create_timestamp(datetime.now(UTC)).timestamp() * 1000)
            event_id = f"{topic}_{self._sequence_counter}_{ts_ms}"

            # Serialize event
            event_data = self._serialize_event(event)

            # Create persisted event
            persisted = PersistedEvent(
                event_id=event_id,
                topic=topic,
                timestamp=datetime.now(UTC).isoformat(),
                event_data=event_data,
                sequence=self._sequence_counter,
            )

            # Save to file
            topic_dir = self._storage_dir / topic
            topic_dir.mkdir(exist_ok=True)

            event_file = topic_dir / f"{event_id}.json"
            with event_file.open("w", encoding="utf-8") as f:
                json.dump(persisted.__dict__, f, indent=2, default=str)

            logger.debug(f"Saved event to persistence: {event_id}")
            return persisted

        except Exception as exc:
            logger.error("Error saving event to persistence: %s", exc)
            msg = f"Failed to save event for topic '{topic}'"
            raise EventBusError(msg) from exc

    async def load_events(
        self,
        topic: str,
        start_sequence: int = 0,
        end_sequence: int | None = None,
    ) -> list[PersistedEvent]:
        """Load events from persistent storage.

        Args:
            topic: Event topic to load.
            start_sequence: Starting sequence number (inclusive).
            end_sequence: Ending sequence number (inclusive). If None, loads all.

        Returns:
            List of PersistedEvent instances.
        """
        try:
            topic_dir = self._storage_dir / topic
            if not topic_dir.exists():
                logger.warning(f"No events found for topic: {topic}")
                return []
            events = [
                parsed
                for f in sorted(topic_dir.glob("*.json"))
                if (parsed := _parse_event_file(f, start_sequence, end_sequence)) is not None
            ]
            logger.info(f"Loaded {len(events)} events from persistence for topic: {topic}")
            return events
        except Exception as exc:
            logger.error("Error loading events from persistence: %s", exc)
            msg = f"Failed to load events for topic '{topic}'"
            raise EventBusError(msg) from exc

    async def replay_events(
        self,
        topic: str,
        callback: Any,
        start_sequence: int = 0,
        end_sequence: int | None = None,
        delay_ms: int = 0,
    ) -> int:
        """Replay events from persistent storage.

        Args:
            topic: Event topic to replay.
            callback: Async callback function to receive each event.
            start_sequence: Starting sequence number.
            end_sequence: Ending sequence number.
            delay_ms: Delay between events in milliseconds.

        Returns:
            Number of events replayed.
        """
        events = await self.load_events(topic, start_sequence, end_sequence)

        if not events:
            logger.info(f"No events to replay for topic: {topic}")
            return 0

        replayed_count = 0
        for event in events:
            try:
                # Deserialize event
                event_obj = self._deserialize_event(event.event_data)

                # Call callback
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_obj)
                else:
                    callback(event_obj)

                replayed_count += 1

                # Apply delay if specified
                if delay_ms > 0:
                    await asyncio.sleep(delay_ms / 1000)

            except Exception as exc:
                logger.error("Error replaying event %s: %s", event.event_id, exc)
                continue

        logger.info(f"Replayed {replayed_count} events for topic: {topic}")
        return replayed_count

    async def clear_events(self, topic: str | None = None) -> int:
        """Clear persisted events.

        Args:
            topic: Specific topic to clear. If None, clears all topics.

        Returns:
            Number of events deleted.
        """
        try:
            deleted_count = 0

            if topic:
                # Clear specific topic
                topic_dir = self._storage_dir / topic
                if topic_dir.exists():
                    for event_file in topic_dir.glob("*.json"):
                        event_file.unlink()
                        deleted_count += 1
                    logger.info(f"Cleared {deleted_count} events for topic: {topic}")
            else:
                # Clear all topics
                for topic_dir in self._storage_dir.iterdir():
                    if topic_dir.is_dir():
                        for event_file in topic_dir.glob("*.json"):
                            event_file.unlink()
                            deleted_count += 1
                logger.info(f"Cleared {deleted_count} events from all topics")

            return deleted_count

        except Exception as exc:
            logger.error("Error clearing events: %s", exc)
            msg = "Failed to clear events from persistence"
            raise EventBusError(msg) from exc

    async def get_event_count(self, topic: str) -> int:
        """Get count of persisted events for a topic.

        Args:
            topic: Event topic.

        Returns:
            Number of persisted events.
        """
        try:
            topic_dir = self._storage_dir / topic

            if not topic_dir.exists():
                return 0

            return len(list(topic_dir.glob("*.json")))

        except Exception as exc:
            logger.error("Error getting event count: %s", exc)
            return 0

    def _serialize_event(self, event: Any) -> dict[str, Any]:
        """Serialize event to dictionary.

        Args:
            event: Event object.

        Returns:
            Serialized event data.
        """
        if hasattr(event, "model_dump"):
            # Pydantic model
            result = event.model_dump()
            return result if isinstance(result, dict) else {"data": str(result)}
        elif isinstance(event, dict):
            return event
        elif hasattr(event, "__dict__"):
            # Fallback: use __dict__ if available
            return event.__dict__ if isinstance(event.__dict__, dict) else {"data": str(event)}
        else:
            return {"data": str(event)}

    def _deserialize_event(self, event_data: dict[str, Any]) -> Any:
        """Deserialize event from dictionary.

        Args:
            event_data: Serialized event data.

        Returns:
            Deserialized event object.
        """
        # Return as dictionary; caller should handle reconstruction
        return event_data
