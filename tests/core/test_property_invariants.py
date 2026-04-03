"""
Deterministic property tests for core event and clock invariants.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from iatb.core.clock import Clock, TradingSessions
from iatb.core.enums import Exchange
from iatb.core.event_bus import EventBus
from iatb.core.events import MarketTickEvent
from iatb.core.types import create_price, create_quantity

SESSION_EXCHANGES = (Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS)
PRICE_STRATEGY = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _build_tick(index: int, price: Decimal) -> MarketTickEvent:
    """Build a valid market tick for deterministic tests."""
    return MarketTickEvent(
        symbol=f"SYMBOL{index}",
        price=create_price(price),
        quantity=create_quantity("1"),
        volume=create_quantity("1"),
    )


@settings(max_examples=25, deadline=None, derandomize=True)
@given(prices=st.lists(PRICE_STRATEGY, min_size=1, max_size=20))
def test_property_event_ordering_preserved(prices: list[Decimal]) -> None:
    """Publishing batches preserves order for each subscriber queue."""

    async def _run() -> None:
        bus = EventBus()
        await bus.start()
        queue = await bus.subscribe("market.ticks")
        events = [_build_tick(index, price) for index, price in enumerate(prices)]
        await bus.publish_batch("market.ticks", events)
        received_symbols = [(await queue.get()).symbol for _ in range(len(events))]
        await bus.stop()
        assert received_symbols == [event.symbol for event in events]

    asyncio.run(_run())


@settings(max_examples=20, deadline=None, derandomize=True)
@given(
    subscriber_count=st.integers(min_value=1, max_value=4),
    event_count=st.integers(min_value=1, max_value=12),
)
def test_property_bus_delivery_to_all_subscribers(subscriber_count: int, event_count: int) -> None:
    """Every subscriber receives every published event in order."""

    async def _run() -> None:
        bus = EventBus()
        await bus.start()
        queues = [await bus.subscribe("signals.trading") for _ in range(subscriber_count)]
        events = [_build_tick(index, Decimal(index + 1)) for index in range(event_count)]

        for event in events:
            await bus.publish("signals.trading", event)

        expected_ids = [event.event_id for event in events]
        for queue in queues:
            received_ids = [(await queue.get()).event_id for _ in range(event_count)]
            assert received_ids == expected_ids
        await bus.stop()

    asyncio.run(_run())


def _next_session_date(exchange: Exchange, start_date: date) -> date:
    """Find the next date with an active session."""
    probe = start_date
    for _ in range(31):
        if TradingSessions.calendar.session_for(exchange, probe) is not None:
            return probe
        probe += timedelta(days=1)
    msg = f"No active session found within 31 days for {exchange.value}"
    raise AssertionError(msg)


@settings(max_examples=30, deadline=None, derandomize=True)
@given(
    exchange=st.sampled_from(SESSION_EXCHANGES),
    day_offset=st.integers(min_value=0, max_value=30),
    minute_offset=st.integers(min_value=-120, max_value=120),
)
def test_property_clock_session_boundaries(
    exchange: Exchange,
    day_offset: int,
    minute_offset: int,
) -> None:
    """Session open/closed state remains consistent near boundaries."""
    session_date = _next_session_date(exchange, date(2026, 1, 1) + timedelta(days=day_offset))
    session = TradingSessions.calendar.session_for(exchange, session_date)
    assert session is not None

    probe_ist = datetime.combine(session_date, session.open_time) + timedelta(minutes=minute_offset)
    probe_utc = Clock.ist_to_utc(probe_ist)
    assert probe_utc.tzinfo == UTC

    expected_session = TradingSessions.calendar.session_for(exchange, probe_ist.date())
    expected_is_open = (
        expected_session is not None
        and expected_session.open_time <= probe_ist.time() < expected_session.close_time
    )
    assert TradingSessions.is_market_open(probe_utc, exchange) is expected_is_open
