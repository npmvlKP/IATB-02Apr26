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
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from iatb.core.enums import Exchange, OrderSide, OrderStatus, OrderType
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
    Price,
    Quantity,
    Timestamp,
    create_price,
    create_quantity,
    create_timestamp,
)

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

    async def _replay_single_event(
        self,
        event: PersistedEvent,
        callback: Any,
        delay_ms: int,
    ) -> bool:
        """Replay a single event with optional delay.

        Args:
            event: Event to replay.
            callback: Callback function to receive the event.
            delay_ms: Delay in milliseconds.

        Returns:
            True if replay succeeded, False otherwise.
        """
        try:
            event_obj = self._deserialize_event(event.event_data)

            if asyncio.iscoroutinefunction(callback):
                await callback(event_obj)
            else:
                callback(event_obj)

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)

            return True
        except Exception as exc:
            logger.error("Error replaying event %s: %s", event.event_id, exc)
            return False

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
            if await self._replay_single_event(event, callback, delay_ms):
                replayed_count += 1

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
            result = event.model_dump()
            if isinstance(result, dict):
                result["_event_type"] = event.__class__.__name__
                return result
            return {"data": str(result), "_event_type": event.__class__.__name__}
        elif isinstance(event, dict):
            return event
        elif hasattr(event, "__dict__"):
            result = event.__dict__
            if isinstance(result, dict):
                result["_event_type"] = event.__class__.__name__
                return result
            return {"data": str(event), "_event_type": event.__class__.__name__}
        else:
            return {"data": str(event), "_event_type": "unknown"}

    def _deserialize_event(self, event_data: dict[str, Any]) -> Any:
        """Deserialize event from dictionary.

        Args:
            event_data: Serialized event data.

        Returns:
            Deserialized event object.
        """
        if "_event_type" in event_data:
            event_type = event_data.pop("_event_type")
        elif "filled_quantity" in event_data and "order_id" in event_data:
            event_type = "OrderUpdateEvent"
        elif "strategy_id" in event_data and "confidence" in event_data:
            event_type = "SignalEvent"
        elif "regime_type" in event_data:
            event_type = "RegimeChangeEvent"
        elif "total_candidates" in event_data:
            event_type = "ScanUpdateEvent"
        elif "trade_pnl" in event_data:
            event_type = "PnLUpdateEvent"
        elif "bid_price" in event_data and "ask_price" in event_data:
            event_type = "MarketTickEvent"
        else:
            return event_data

        if event_type == "MarketTickEvent":
            return self._deserialize_market_tick_event(event_data)
        if event_type == "OrderUpdateEvent":
            return self._deserialize_order_update_event(event_data)
        if event_type == "SignalEvent":
            return self._deserialize_signal_event(event_data)
        if event_type == "RegimeChangeEvent":
            return self._deserialize_regime_change_event(event_data)
        if event_type == "ScanUpdateEvent":
            return self._deserialize_scan_update_event(event_data)
        if event_type == "PnLUpdateEvent":
            return self._deserialize_pnl_update_event(event_data)
        return event_data

    def _to_uuid(self, value: Any) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(value)

    def _to_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        msg = f"Cannot convert {type(value)} to datetime"
        raise TypeError(msg)

    def _to_decimal(self, value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def _to_price(self, value: Any) -> Price:
        if isinstance(value, str):
            return create_price(value)
        return create_price(str(value))

    def _to_quantity(self, value: Any) -> Quantity:
        if isinstance(value, str):
            return create_quantity(value)
        return create_quantity(str(value))

    def _to_timestamp(self, value: Any) -> Timestamp:
        if isinstance(value, datetime):
            return create_timestamp(value)
        dt = self._to_datetime(value)
        return create_timestamp(dt)

    def _deserialize_market_tick_event(self, data: dict[str, Any]) -> MarketTickEvent:
        return MarketTickEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            exchange=Exchange(data["exchange"]) if data.get("exchange") else Exchange.NSE,
            symbol=data.get("symbol", "UNKNOWN"),
            price=self._to_price(data["price"])
            if data.get("price") is not None
            else create_price("0.0"),
            quantity=self._to_quantity(data["quantity"])
            if data.get("quantity") is not None
            else create_quantity("0.0"),
            volume=self._to_quantity(data["volume"])
            if data.get("volume") is not None
            else create_quantity("0.0"),
            bid_price=self._to_price(data["bid_price"])
            if data.get("bid_price") is not None
            else None,
            ask_price=self._to_price(data["ask_price"])
            if data.get("ask_price") is not None
            else None,
        )

    def _deserialize_order_update_event(self, data: dict[str, Any]) -> OrderUpdateEvent:
        return OrderUpdateEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            order_id=data.get("order_id", "UNKNOWN_ORDER"),
            exchange=Exchange(data["exchange"]) if data.get("exchange") else Exchange.NSE,
            symbol=data.get("symbol", "UNKNOWN"),
            side=OrderSide(data["side"]) if data.get("side") else OrderSide.BUY,
            order_type=OrderType(data["order_type"])
            if data.get("order_type")
            else OrderType.MARKET,
            quantity=self._to_quantity(data["quantity"])
            if data.get("quantity") is not None
            else create_quantity("0.0"),
            price=self._to_price(data["price"]) if data.get("price") is not None else None,
            filled_quantity=self._to_quantity(data["filled_quantity"])
            if data.get("filled_quantity") is not None
            else create_quantity("0.0"),
            avg_price=self._to_price(data["avg_price"])
            if data.get("avg_price") is not None
            else None,
            status=OrderStatus(data["status"]) if data.get("status") else OrderStatus.PENDING,
        )

    def _deserialize_signal_event(self, data: dict[str, Any]) -> SignalEvent:
        return SignalEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            strategy_id=data.get("strategy_id", "UNKNOWN_STRATEGY"),
            exchange=Exchange(data["exchange"]) if data.get("exchange") else Exchange.NSE,
            symbol=data.get("symbol", "UNKNOWN"),
            side=OrderSide(data["side"]) if data.get("side") else OrderSide.BUY,
            quantity=self._to_quantity(data["quantity"])
            if data.get("quantity") is not None
            else create_quantity("0.0"),
            price=self._to_price(data["price"]) if data.get("price") is not None else None,
            confidence=self._to_decimal(data.get("confidence"))
            if data.get("confidence") is not None
            else Decimal("0.0"),
        )

    def _deserialize_regime_change_event(self, data: dict[str, Any]) -> RegimeChangeEvent:
        return RegimeChangeEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            regime_type=data.get("regime_type", "UNSPECIFIED"),
            description=data.get("description", "UNSPECIFIED"),
            confidence=self._to_decimal(data.get("confidence"))
            if data.get("confidence") is not None
            else Decimal("0.0"),
            metadata=data.get("metadata", {}),
        )

    def _deserialize_scan_update_event(self, data: dict[str, Any]) -> ScanUpdateEvent:
        return ScanUpdateEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            total_candidates=data.get("total_candidates", 0),
            approved_candidates=data.get("approved_candidates", 0),
            trades_executed=data.get("trades_executed", 0),
            duration_ms=data.get("duration_ms", 0),
            errors=data.get("errors", []),
        )

    def _deserialize_pnl_update_event(self, data: dict[str, Any]) -> PnLUpdateEvent:
        return PnLUpdateEvent(
            event_id=self._to_uuid(data["event_id"]),
            timestamp=self._to_timestamp(data["timestamp"]),
            order_id=data.get("order_id", "UNKNOWN"),
            symbol=data.get("symbol", "UNKNOWN"),
            side=data.get("side", "UNKNOWN"),
            quantity=self._to_quantity(data["quantity"])
            if data.get("quantity") is not None
            else create_quantity("0.0"),
            price=self._to_price(data["price"])
            if data.get("price") is not None
            else create_price("0.0"),
            trade_pnl=self._to_decimal(data.get("trade_pnl"))
            if data.get("trade_pnl") is not None
            else Decimal("0.0"),
            cumulative_pnl=self._to_decimal(data.get("cumulative_pnl"))
            if data.get("cumulative_pnl") is not None
            else Decimal("0.0"),
        )
