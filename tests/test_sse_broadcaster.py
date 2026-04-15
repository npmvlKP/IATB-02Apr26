"""
Tests for SSE broadcaster functionality.

Tests cover:
- SSE broadcaster initialization and lifecycle
- Event subscription and forwarding
- Client connection management
- SSE message formatting
- Error handling and fallback
"""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.event_bus import EventBus
from iatb.core.events import PnLUpdateEvent, ScanUpdateEvent
from iatb.core.sse_broadcaster import SSEBroadcaster, get_broadcaster
from iatb.core.types import create_price, create_quantity

# Module-level broadcaster instance for tests
_test_broadcaster: SSEBroadcaster | None = None


async def _get_test_broadcaster() -> SSEBroadcaster:
    """Get or create test broadcaster instance.

    This is a helper for tests that need a broadcaster instance.

    Returns:
        SSE broadcaster instance.
    """
    global _test_broadcaster
    if _test_broadcaster is None:
        _test_broadcaster = SSEBroadcaster()
    return _test_broadcaster


@pytest.fixture
async def event_bus() -> EventBus:
    """Create an event bus instance for testing."""
    bus = EventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
async def broadcaster(event_bus: EventBus) -> SSEBroadcaster:
    """Create and start a broadcaster instance."""
    b = SSEBroadcaster()
    await b.start(event_bus)
    yield b
    await b.stop()


@pytest.fixture
def sample_scan_event() -> ScanUpdateEvent:
    """Create a sample scan update event."""
    return ScanUpdateEvent(
        total_candidates=10,
        approved_candidates=5,
        trades_executed=3,
        duration_ms=1500,
        errors=[],
    )


@pytest.fixture
def sample_pnl_event() -> PnLUpdateEvent:
    """Create a sample PnL update event."""
    return PnLUpdateEvent(
        order_id="TEST123",
        symbol="RELIANCE",
        side="BUY",
        quantity=create_quantity("10"),
        price=create_price("2500.50"),
        trade_pnl=Decimal("100.00"),
        cumulative_pnl=Decimal("1000.00"),
    )


class TestSSEBroadcaster:
    """Test suite for SSE broadcaster."""

    @pytest.mark.asyncio
    async def test_broadcaster_singleton(self) -> None:
        """Test that broadcaster is a singleton via async factory."""
        b1 = await get_broadcaster()
        b2 = await get_broadcaster()
        assert b1 is b2

    @pytest.mark.asyncio
    async def test_concurrent_singleton_access(self) -> None:
        """Test that concurrent access to get_broadcaster is thread-safe."""

        # Create multiple coroutines that call get_broadcaster concurrently
        async def get_and_check() -> SSEBroadcaster:
            """Get broadcaster and verify it's the same instance."""
            broadcaster = await get_broadcaster()
            assert isinstance(broadcaster, SSEBroadcaster)
            return broadcaster

        # Run multiple concurrent calls
        tasks = [get_and_check() for _ in range(10)]
        broadcasters = await asyncio.gather(*tasks)

        # All should be the same instance
        first = broadcasters[0]
        for b in broadcasters[1:]:
            assert b is first

    @pytest.mark.asyncio
    async def test_lock_created_in_event_loop(self) -> None:
        """Test that the lock is created lazily inside the event loop."""
        from iatb.core.sse_broadcaster import _broadcaster_lock, _get_broadcaster_lock

        # Get the lock (may already be created by other tests)
        lock1 = _get_broadcaster_lock()
        assert _broadcaster_lock is not None
        assert lock1 is _broadcaster_lock

        # Subsequent calls should return the same lock
        lock2 = _get_broadcaster_lock()
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_broadcaster_lifecycle(self, event_bus: EventBus) -> None:
        """Test broadcaster start and stop."""
        b = SSEBroadcaster()
        assert not b._running

        await b.start(event_bus)
        assert b._running

        await b.stop()
        assert not b._running

    @pytest.mark.asyncio
    async def test_subscribe_creates_queue(self, broadcaster: SSEBroadcaster) -> None:
        """Test that subscribing creates a queue for the client."""
        assert len(broadcaster._subscribers) == 0

        # Subscribe and consume one event to initialize
        gen = broadcaster.subscribe()
        try:
            # Get the connection event
            await anext(gen)
            assert len(broadcaster._subscribers) == 1
        finally:
            # Close the generator to unsubscribe
            await gen.aclose()

        # Queue should be removed after closing
        await asyncio.sleep(0.1)
        assert len(broadcaster._subscribers) == 0

    @pytest.mark.asyncio
    async def test_scan_event_forwarding(
        self,
        event_bus: EventBus,
        sample_scan_event: ScanUpdateEvent,
    ) -> None:
        """Test that scan events are forwarded to subscribers."""
        b = SSEBroadcaster()
        await b.start(event_bus)

        # Subscribe and get the connection event
        gen = b.subscribe()
        try:
            await anext(gen)  # Skip connection event

            # Publish scan event
            await event_bus.publish("scan", sample_scan_event)

            # Receive the forwarded event
            message = await asyncio.wait_for(anext(gen), timeout=2.0)

            assert "event: scan" in message
            assert "event_type" in message
            assert "total_candidates" in message
        finally:
            await b.stop()
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_pnl_event_forwarding(
        self,
        event_bus: EventBus,
        sample_pnl_event: PnLUpdateEvent,
    ) -> None:
        """Test that PnL events are forwarded to subscribers."""
        b = SSEBroadcaster()
        await b.start(event_bus)

        # Subscribe and get the connection event
        gen = b.subscribe()
        try:
            await anext(gen)  # Skip connection event

            # Publish PnL event
            await event_bus.publish("pnl", sample_pnl_event)

            # Receive the forwarded event
            message = await asyncio.wait_for(anext(gen), timeout=2.0)

            assert "event: pnl" in message
            assert "event_type" in message
            assert "order_id" in message
            assert "symbol" in message
        finally:
            await b.stop()
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(
        self,
        event_bus: EventBus,
        sample_scan_event: ScanUpdateEvent,
    ) -> None:
        """Test that events are forwarded to all subscribers."""
        b = SSEBroadcaster()
        await b.start(event_bus)

        # Subscribe multiple clients
        gen1 = b.subscribe()
        gen2 = b.subscribe()
        gen3 = b.subscribe()

        try:
            # Skip connection events
            await anext(gen1)
            await anext(gen2)
            await anext(gen3)

            # Publish event
            await event_bus.publish("scan", sample_scan_event)

            # All subscribers should receive the event
            msg1 = await asyncio.wait_for(anext(gen1), timeout=2.0)
            msg2 = await asyncio.wait_for(anext(gen2), timeout=2.0)
            msg3 = await asyncio.wait_for(anext(gen3), timeout=2.0)

            assert "event: scan" in msg1
            assert "event: scan" in msg2
            assert "event: scan" in msg3
        finally:
            await b.stop()
            await gen1.aclose()
            await gen2.aclose()
            await gen3.aclose()

    @pytest.mark.asyncio
    async def test_dead_subscriber_removal(
        self,
        event_bus: EventBus,
        sample_scan_event: ScanUpdateEvent,
    ) -> None:
        """Test that dead subscribers are removed."""
        b = SSEBroadcaster()
        await b.start(event_bus)

        # Subscribe and close immediately (simulate dead subscriber)
        gen = b.subscribe()
        await anext(gen)  # Skip connection event

        # Manually close the queue
        await gen.aclose()
        await asyncio.sleep(0.1)

        # Publish event - should not fail
        await event_bus.publish("scan", sample_scan_event)
        await asyncio.sleep(0.1)

        # Subscriber should be removed
        assert len(b._subscribers) == 0

        await b.stop()

    @pytest.mark.asyncio
    async def test_sse_format_scan_event(self, broadcaster: SSEBroadcaster) -> None:
        """Test SSE formatting for scan events."""
        event = ScanUpdateEvent(
            total_candidates=20,
            approved_candidates=10,
            trades_executed=5,
            duration_ms=2000,
            errors=["test error"],
        )

        result = broadcaster._event_to_sse("scan", event)

        assert result["event"] == "scan"
        data = json.loads(result["data"])
        assert data["event_type"] == "scan_update"
        assert data["total_candidates"] == 20
        assert data["approved_candidates"] == 10
        assert data["trades_executed"] == 5
        assert data["duration_ms"] == 2000
        assert data["errors"] == ["test error"]

    @pytest.mark.asyncio
    async def test_sse_format_pnl_event(self, broadcaster: SSEBroadcaster) -> None:
        """Test SSE formatting for PnL events."""
        event = PnLUpdateEvent(
            order_id="ORDER1",
            symbol="TCS",
            side="SELL",
            quantity=create_quantity("5"),
            price=create_price("3500.75"),
            trade_pnl=Decimal("500.00"),
            cumulative_pnl=Decimal("2500.00"),
        )

        result = broadcaster._event_to_sse("pnl", event)

        assert result["event"] == "pnl"
        data = json.loads(result["data"])
        assert data["event_type"] == "pnl_update"
        assert data["order_id"] == "ORDER1"
        assert data["symbol"] == "TCS"
        assert data["side"] == "SELL"
        assert data["quantity"] == "5"  # Decimal string representation
        assert data["price"] == "3500.75"
        assert data["trade_pnl"] == "500.00"
        assert data["cumulative_pnl"] == "2500.00"

    @pytest.mark.asyncio
    async def test_sse_format_generic_event(self, broadcaster: SSEBroadcaster) -> None:
        """Test SSE formatting for generic events."""
        # Mock a generic event with timestamp
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(UTC)

        result = broadcaster._event_to_sse("generic", mock_event)

        assert result["event"] == "generic"
        data = json.loads(result["data"])
        assert data["event_type"] == "generic"
        assert "timestamp" in data

    def test_format_sse_message(self, broadcaster: SSEBroadcaster) -> None:
        """Test SSE message formatting."""
        message = broadcaster._format_sse("test-event", '{"key":"value"}')

        assert message == 'event: test-event\ndata: {"key":"value"}\n\n'

    @pytest.mark.asyncio
    async def test_keepalive_message(self, broadcaster: SSEBroadcaster) -> None:
        """Test that keepalive messages are sent."""
        gen = broadcaster.subscribe()
        try:
            # Skip connection event
            await anext(gen)

            # Wait for keepalive (timeout is 1 second in subscribe)
            keepalive = await asyncio.wait_for(anext(gen), timeout=2.0)

            assert keepalive.startswith(": keepalive")
            assert keepalive.endswith("\n\n")
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_cleanup(self, event_bus: EventBus) -> None:
        """Test cleanup of multiple subscriptions."""
        b = SSEBroadcaster()
        await b.start(event_bus)

        # Create multiple subscriptions
        gens = []
        for _ in range(5):
            gen = b.subscribe()
            await anext(gen)  # Skip connection event
            gens.append(gen)

        assert len(b._subscribers) == 5

        # Close all subscriptions
        for gen in gens:
            await gen.aclose()

        await asyncio.sleep(0.1)
        assert len(b._subscribers) == 0

        await b.stop()


class TestFastAPISSEEndpoint:
    """Test suite for FastAPI SSE endpoint integration."""

    @pytest.mark.asyncio
    async def test_events_stream_response(self) -> None:
        """Test that events stream returns proper response."""
        from iatb.fastapi_app import events_stream

        # This is a basic test - integration testing would require
        # a running FastAPI test client
        response = await events_stream()
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        assert response.headers["X-Accel-Buffering"] == "no"

    @pytest.mark.asyncio
    async def test_broadcaster_initialization_on_startup(self) -> None:
        """Test that broadcaster is available after app startup."""
        from iatb.fastapi_app import get_broadcaster

        broadcaster = await get_broadcaster()
        assert isinstance(broadcaster, SSEBroadcaster)
