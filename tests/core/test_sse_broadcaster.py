"""Tests for SSE broadcaster module - synchronous unit tests only."""

import json
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.sse_broadcaster import SSEBroadcaster
from iatb.core.types import create_price, create_quantity


class TestSSEFormat:
    def test_format_sse(self) -> None:
        b = SSEBroadcaster()
        result = b._format_sse("scan", '{"status": "ok"}')
        assert result == 'event: scan\ndata: {"status": "ok"}\n\n'

    def test_format_sse_event_type(self) -> None:
        b = SSEBroadcaster()
        result = b._format_sse("pnl", "test")
        assert result.startswith("event: pnl\ndata: test\n\n")


class TestEventToSSE:
    def test_scan_update_event(self) -> None:
        b = SSEBroadcaster()
        from iatb.core.events import ScanUpdateEvent

        event = ScanUpdateEvent(
            total_candidates=100,
            approved_candidates=10,
            trades_executed=5,
            duration_ms=1500,
            errors=[],
        )
        result = b._event_to_sse("scan", event)
        assert result["event"] == "scan"
        data = json.loads(result["data"])
        assert data["event_type"] == "scan_update"
        assert data["total_candidates"] == 100

    def test_pnl_update_event(self) -> None:
        b = SSEBroadcaster()
        from iatb.core.events import PnLUpdateEvent

        event = PnLUpdateEvent(
            order_id="ORD-1",
            symbol="RELIANCE",
            side="BUY",
            quantity=create_quantity("100"),
            price=create_price("2500"),
            trade_pnl=Decimal("5000"),
            cumulative_pnl=Decimal("15000"),
        )
        result = b._event_to_sse("pnl", event)
        assert result["event"] == "pnl"
        data = json.loads(result["data"])
        assert data["event_type"] == "pnl_update"
        assert data["order_id"] == "ORD-1"

    def test_generic_event(self) -> None:
        b = SSEBroadcaster()
        event = type("Fake", (), {"timestamp": datetime.now(UTC)})()
        result = b._event_to_sse("custom", event)
        assert result["event"] == "custom"
        data = json.loads(result["data"])
        assert data["event_type"] == "custom"

    def test_generic_event_no_timestamp(self) -> None:
        b = SSEBroadcaster()
        event = "simple_string"
        result = b._event_to_sse("test", event)
        assert result["event"] == "test"
        data = json.loads(result["data"])
        assert "timestamp" in data


class TestBroadcasterInit:
    def test_initial_state(self) -> None:
        b = SSEBroadcaster()
        assert b._running is False
        assert b._event_bus is None
        assert b._subscribers == []
        assert b._forwarding_tasks == []

    def test_stop_when_not_running(self) -> None:
        b = SSEBroadcaster()
        import asyncio

        asyncio.get_event_loop().run_until_complete(b.stop())
        assert b._running is False


class TestGetBroadcaster:
    def test_get_broadcaster_lock_creates_lock(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original = mod._broadcaster_lock
        mod._broadcaster_lock = None
        lock = mod._get_broadcaster_lock()
        assert lock is not None
        mod._broadcaster_lock = original

    def test_get_broadcaster_lock_returns_existing(self) -> None:
        import asyncio

        import iatb.core.sse_broadcaster as mod

        original = mod._broadcaster_lock
        lock = asyncio.Lock()
        mod._broadcaster_lock = lock
        result = mod._get_broadcaster_lock()
        assert result is lock
        mod._broadcaster_lock = original
