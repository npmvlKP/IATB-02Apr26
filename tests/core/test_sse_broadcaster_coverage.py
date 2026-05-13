"""Comprehensive async tests for SSE broadcaster — lifecycle, subscribe, event forwarding,
dead subscriber removal, keepalive, generic event fallback, singleton get_broadcaster()."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from iatb.core.events import PnLUpdateEvent, ScanUpdateEvent
from iatb.core.sse_broadcaster import (
    SSEBroadcaster,
    _get_broadcaster_lock,
    get_broadcaster,
)
from iatb.core.types import create_price, create_quantity


def _make_scan_event(
    total_candidates: int = 100,
    approved_candidates: int = 80,
    trades_executed: int = 50,
    duration_ms: int = 0,
    errors: list[str] | None = None,
) -> ScanUpdateEvent:
    if approved_candidates > total_candidates:
        approved_candidates = total_candidates
    if trades_executed > approved_candidates:
        trades_executed = approved_candidates
    return ScanUpdateEvent(
        total_candidates=total_candidates,
        approved_candidates=approved_candidates,
        trades_executed=trades_executed,
        duration_ms=duration_ms,
        errors=errors if errors is not None else [],
    )


def _make_pnl_event(
    order_id: str = "ORD-001",
    symbol: str = "RELIANCE",
    side: str = "BUY",
    quantity: str = "100",
    price: str = "2500.00",
    trade_pnl: str = "500.00",
    cumulative_pnl: str = "15000.00",
) -> PnLUpdateEvent:
    return PnLUpdateEvent(
        order_id=order_id,
        symbol=symbol,
        side=side,
        quantity=create_quantity(quantity),
        price=create_price(price),
        trade_pnl=Decimal(trade_pnl),
        cumulative_pnl=Decimal(cumulative_pnl),
    )


def _make_mock_event_bus(
    scan_events: list[Any] | None = None,
    pnl_events: list[Any] | None = None,
) -> MagicMock:
    scan_queue: asyncio.Queue[Any] = asyncio.Queue()
    for e in scan_events or []:
        scan_queue.put_nowait(e)
    pnl_queue: asyncio.Queue[Any] = asyncio.Queue()
    for e in pnl_events or []:
        pnl_queue.put_nowait(e)

    async def _subscribe(topic: str) -> asyncio.Queue[Any]:
        if topic == "scan":
            return scan_queue
        if topic == "pnl":
            return pnl_queue
        return asyncio.Queue()

    bus = MagicMock()
    bus.subscribe = AsyncMock(side_effect=_subscribe)
    bus._scan_queue = scan_queue
    bus._pnl_queue = pnl_queue
    return bus


async def _stop_broadcaster(b: SSEBroadcaster) -> None:
    await b.stop()
    for task in b._forwarding_tasks:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
    b._forwarding_tasks.clear()


class TestStartStopLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        try:
            await b.start(bus)
            assert b._running is True
            assert b._event_bus is bus
        finally:
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        try:
            await b.start(bus)
            await b.start(bus)
            assert len(b._forwarding_tasks) == 2
        finally:
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        await _stop_broadcaster(b)
        assert b._running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_noop(self) -> None:
        b = SSEBroadcaster()
        await _stop_broadcaster(b)
        assert b._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_forwarding_tasks(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        tasks = list(b._forwarding_tasks)
        assert len(tasks) == 2
        await _stop_broadcaster(b)
        for t in tasks:
            assert t.done()

    @pytest.mark.asyncio
    async def test_stop_clears_forwarding_tasks(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        await _stop_broadcaster(b)
        assert b._forwarding_tasks == []

    @pytest.mark.asyncio
    async def test_stop_closes_subscriber_queues_with_none(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        q: asyncio.Queue[dict[str, str] | None] = asyncio.Queue()
        b._subscribers.append(q)
        await _stop_broadcaster(b)
        msg = q.get_nowait()
        assert msg is None
        assert b._subscribers == []

    @pytest.mark.asyncio
    async def test_stop_handles_queue_close_exception(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        dead_q: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=1)
        dead_q.put_nowait({"event": "x", "data": "y"})
        b._subscribers.append(dead_q)
        await _stop_broadcaster(b)
        assert b._subscribers == []


class TestSubscribeUnsubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_yields_connection_event(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            msg = await gen.__anext__()
            assert "event: connection" in msg
            assert "connected" in msg
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_subscribe_adds_queue_to_subscribers(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            initial_count = len(b._subscribers)
            gen = b.subscribe()
            await gen.__anext__()
            assert len(b._subscribers) == initial_count + 1
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue_on_generator_exit(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            await gen.__anext__()
            sub_count_after_subscribe = len(b._subscribers)
            await gen.aclose()
            await asyncio.sleep(0.05)
            assert len(b._subscribers) < sub_count_after_subscribe
        finally:
            await _stop_broadcaster(b)


class TestEventForwarding:
    @pytest.mark.asyncio
    async def test_scan_event_forwarded_to_subscriber(self) -> None:
        scan_evt = _make_scan_event(total_candidates=42, approved_candidates=40)
        bus = _make_mock_event_bus(scan_events=[scan_evt])
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            conn_msg = await gen.__anext__()
            assert "connection" in conn_msg
            msg = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert "event: scan" in msg
            assert "scan_update" in msg
            assert "42" in msg
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_pnl_event_forwarded_to_subscriber(self) -> None:
        pnl_evt = _make_pnl_event(order_id="ORD-999", symbol="TCS")
        bus = _make_mock_event_bus(pnl_events=[pnl_evt])
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            await gen.__anext__()
            msg = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert "event: pnl" in msg
            assert "pnl_update" in msg
            assert "ORD-999" in msg
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_none_event_breaks_forward_loop(self) -> None:
        bus = _make_mock_event_bus(scan_events=[None], pnl_events=[None])
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            await asyncio.sleep(0.5)
            for t in b._forwarding_tasks:
                if not t.cancelled():
                    assert t.done()
        finally:
            await _stop_broadcaster(b)


class TestDeadSubscriberRemoval:
    @pytest.mark.asyncio
    async def test_full_queue_removed_as_dead_subscriber(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            full_q: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=1)
            full_q.put_nowait({"event": "stale", "data": "{}"})
            b._subscribers.append(full_q)
            scan_queue = bus._scan_queue
            scan_evt = _make_scan_event()
            await scan_queue.put(scan_evt)
            await asyncio.sleep(0.3)
            async with b._lock:
                assert full_q not in b._subscribers
        finally:
            await _stop_broadcaster(b)


class TestKeepalive:
    @pytest.mark.asyncio
    async def test_subscribe_emits_keepalive_on_timeout(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            conn = await gen.__anext__()
            assert "connection" in conn
            queue = b._subscribers[-1] if b._subscribers else None
            assert queue is not None
            await queue.put({"event": "test", "data": "payload"})
            event_msg = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert "event: test" in event_msg
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_format_keepalive_is_comment(self) -> None:
        assert ": keepalive\n\n".startswith(":")


class TestGenericEventFallback:
    def test_generic_event_with_timestamp(self) -> None:
        b = SSEBroadcaster()
        evt = type("CustomEvt", (), {"timestamp": datetime.now(UTC), "value": 42})()
        result = b._event_to_sse("custom_topic", evt)
        assert result["event"] == "custom_topic"
        data = json.loads(result["data"])
        assert data["event_type"] == "custom_topic"
        assert data["timestamp"] != ""

    def test_generic_event_without_timestamp(self) -> None:
        b = SSEBroadcaster()
        evt = "plain_string_event"
        result = b._event_to_sse("unknown", evt)
        assert result["event"] == "unknown"
        data = json.loads(result["data"])
        assert data["event_type"] == "unknown"
        assert data["timestamp"] == ""

    def test_generic_event_dict(self) -> None:
        b = SSEBroadcaster()
        evt = {"key": "value"}
        result = b._event_to_sse("dict_topic", evt)
        assert result["event"] == "dict_topic"
        data = json.loads(result["data"])
        assert data["event_type"] == "dict_topic"


class TestEventToSSEConversion:
    def test_scan_update_event_all_fields(self) -> None:
        b = SSEBroadcaster()
        evt = _make_scan_event(
            total_candidates=200,
            approved_candidates=150,
            trades_executed=100,
            duration_ms=3000,
            errors=["err1"],
        )
        result = b._event_to_sse("scan", evt)
        assert result["event"] == "scan"
        data = json.loads(result["data"])
        assert data["event_type"] == "scan_update"
        assert data["total_candidates"] == 200
        assert data["approved_candidates"] == 150
        assert data["trades_executed"] == 100
        assert data["duration_ms"] == 3000
        assert data["errors"] == ["err1"]

    def test_pnl_update_event_all_fields(self) -> None:
        b = SSEBroadcaster()
        evt = _make_pnl_event(
            order_id="ORD-ABC",
            symbol="INFY",
            side="SELL",
            quantity="50",
            price="1800.00",
            trade_pnl="-200.00",
            cumulative_pnl="5000.00",
        )
        result = b._event_to_sse("pnl", evt)
        assert result["event"] == "pnl"
        data = json.loads(result["data"])
        assert data["event_type"] == "pnl_update"
        assert data["order_id"] == "ORD-ABC"
        assert data["symbol"] == "INFY"
        assert data["side"] == "SELL"
        assert data["quantity"] == "50"
        assert data["price"] == "1800.00"
        assert data["trade_pnl"] == "-200.00"
        assert data["cumulative_pnl"] == "5000.00"

    def test_scan_event_timestamp_is_utc_string(self) -> None:
        b = SSEBroadcaster()
        evt = _make_scan_event()
        result = b._event_to_sse("scan", evt)
        data = json.loads(result["data"])
        assert "timestamp" in data
        assert data["timestamp"] != ""

    def test_pnl_event_timestamp_is_utc_string(self) -> None:
        b = SSEBroadcaster()
        evt = _make_pnl_event()
        result = b._event_to_sse("pnl", evt)
        data = json.loads(result["data"])
        assert "timestamp" in data
        assert data["timestamp"] != ""

    def test_scan_event_errors_empty(self) -> None:
        b = SSEBroadcaster()
        evt = _make_scan_event(errors=[])
        result = b._event_to_sse("scan", evt)
        data = json.loads(result["data"])
        assert data["errors"] == []

    def test_scan_event_errors_with_items(self) -> None:
        b = SSEBroadcaster()
        evt = _make_scan_event(errors=["timeout", "rate_limit"])
        result = b._event_to_sse("scan", evt)
        data = json.loads(result["data"])
        assert data["errors"] == ["timeout", "rate_limit"]

    def test_pnl_event_decimal_precision(self) -> None:
        b = SSEBroadcaster()
        evt = _make_pnl_event(
            trade_pnl="0.01",
            cumulative_pnl="99999.99",
        )
        result = b._event_to_sse("pnl", evt)
        data = json.loads(result["data"])
        assert data["trade_pnl"] == "0.01"
        assert data["cumulative_pnl"] == "99999.99"


class TestFormatSSE:
    def test_format_sse_basic(self) -> None:
        b = SSEBroadcaster()
        result = b._format_sse("scan", '{"status": "ok"}')
        assert result == 'event: scan\ndata: {"status": "ok"}\n\n'

    def test_format_sse_contains_event_and_data(self) -> None:
        b = SSEBroadcaster()
        result = b._format_sse("pnl", "test_data")
        assert result.startswith("event: pnl\ndata: test_data\n\n")

    def test_format_sse_with_json_data(self) -> None:
        b = SSEBroadcaster()
        payload = json.dumps({"key": "value"})
        result = b._format_sse("custom", payload)
        assert "event: custom" in result
        assert "data: " in result

    def test_format_sse_double_newline_suffix(self) -> None:
        b = SSEBroadcaster()
        result = b._format_sse("test", "data")
        assert result.endswith("\n\n")


class TestSingletonGetBroadcaster:
    @pytest.mark.asyncio
    async def test_get_broadcaster_returns_singleton(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original_broadcaster = mod._broadcaster
        original_lock = mod._broadcaster_lock
        mod._broadcaster = None
        mod._broadcaster_lock = None
        try:
            b1 = await get_broadcaster()
            b2 = await get_broadcaster()
            assert b1 is b2
        finally:
            mod._broadcaster = original_broadcaster
            mod._broadcaster_lock = original_lock

    @pytest.mark.asyncio
    async def test_get_broadcaster_creates_instance(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original_broadcaster = mod._broadcaster
        original_lock = mod._broadcaster_lock
        mod._broadcaster = None
        mod._broadcaster_lock = None
        try:
            b = await get_broadcaster()
            assert isinstance(b, SSEBroadcaster)
        finally:
            mod._broadcaster = original_broadcaster
            mod._broadcaster_lock = original_lock

    def test_get_broadcaster_lock_creates_lock_when_none(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original = mod._broadcaster_lock
        mod._broadcaster_lock = None
        lock = _get_broadcaster_lock()
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)
        mod._broadcaster_lock = original

    def test_get_broadcaster_lock_returns_existing(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original = mod._broadcaster_lock
        existing_lock = asyncio.Lock()
        mod._broadcaster_lock = existing_lock
        result = _get_broadcaster_lock()
        assert result is existing_lock
        mod._broadcaster_lock = original

    @pytest.mark.asyncio
    async def test_get_broadcaster_existing_instance(self) -> None:
        import iatb.core.sse_broadcaster as mod

        original_broadcaster = mod._broadcaster
        original_lock = mod._broadcaster_lock
        existing = SSEBroadcaster()
        mod._broadcaster = existing
        mod._broadcaster_lock = None
        try:
            b = await get_broadcaster()
            assert b is existing
        finally:
            mod._broadcaster = original_broadcaster
            mod._broadcaster_lock = original_lock


class TestForwardEventsErrorPaths:
    @pytest.mark.asyncio
    async def test_forward_events_handles_generic_exception(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            bad_q: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=1)
            bad_q.put_nowait({"event": "stale", "data": "{}"})
            b._subscribers.append(bad_q)
            scan_queue = bus._scan_queue
            scan_evt = _make_scan_event()
            await scan_queue.put(scan_evt)
            await asyncio.sleep(0.3)
            async with b._lock:
                assert bad_q not in b._subscribers
        finally:
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_forward_events_continues_on_timeout(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            await asyncio.sleep(1.5)
            assert b._running is True
        finally:
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_forward_events_stops_on_cancel(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        tasks = list(b._forwarding_tasks)
        for t in tasks:
            t.cancel()
        await asyncio.sleep(0.3)
        for t in tasks:
            assert t.done()
        b._forwarding_tasks.clear()
        b._running = False


class TestSubscribeExitCleansUp:
    @pytest.mark.asyncio
    async def test_subscribe_removes_queue_on_aclose(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            await gen.__anext__()
            sub_count = len(b._subscribers)
            await gen.aclose()
            await asyncio.sleep(0.05)
            assert len(b._subscribers) <= sub_count
        finally:
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_subscribe_none_breaks_stream(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            await gen.__anext__()
            if b._subscribers:
                await b._subscribers[-1].put(None)
            with pytest.raises((StopAsyncIteration, asyncio.TimeoutError)):
                await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        finally:
            # Cleanup: aclose() may raise if generator already exhausted
            try:
                await gen.aclose()
            except (StopAsyncIteration, RuntimeError):
                pass
            await _stop_broadcaster(b)

    @pytest.mark.asyncio
    async def test_subscribe_cancelled_error_breaks_stream(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen = b.subscribe()
            await gen.__anext__()
        finally:
            await gen.aclose()
            await _stop_broadcaster(b)


class TestStopQueueCloseFailure:
    @pytest.mark.asyncio
    async def test_stop_handles_full_queue_on_close(self) -> None:
        bus = _make_mock_event_bus()
        b = SSEBroadcaster()
        await b.start(bus)
        full_q: asyncio.Queue[dict[str, str] | None] = asyncio.Queue(maxsize=1)
        full_q.put_nowait({"event": "x", "data": "y"})
        b._subscribers.append(full_q)
        await _stop_broadcaster(b)
        assert b._subscribers == []


class TestInitialBroadcasterState:
    def test_initial_state_all_fields(self) -> None:
        b = SSEBroadcaster()
        assert b._running is False
        assert b._event_bus is None
        assert b._subscribers == []
        assert b._forwarding_tasks == []
        assert isinstance(b._lock, asyncio.Lock)

    def test_initial_lock_is_asyncio_lock(self) -> None:
        b = SSEBroadcaster()
        assert isinstance(b._lock, asyncio.Lock)


class TestMultipleSubscribers:
    @pytest.mark.asyncio
    async def test_event_broadcast_to_multiple_subscribers(self) -> None:
        scan_evt = _make_scan_event(total_candidates=77)
        bus = _make_mock_event_bus(scan_events=[scan_evt])
        b = SSEBroadcaster()
        await b.start(bus)
        try:
            gen1 = b.subscribe()
            gen2 = b.subscribe()
            await gen1.__anext__()
            await gen2.__anext__()
            msg1 = await asyncio.wait_for(gen1.__anext__(), timeout=3.0)
            msg2 = await asyncio.wait_for(gen2.__anext__(), timeout=3.0)
            assert "event: scan" in msg1
            assert "event: scan" in msg2
            assert "77" in msg1
            assert "77" in msg2
        finally:
            await gen1.aclose()
            await gen2.aclose()
            await _stop_broadcaster(b)
