#!/usr/bin/env python
"""
Usage Examples for Core Event Architecture

Run this to see practical usage examples:
    python scripts/usage_examples.py
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from iatb.core.clock import Clock, TradingSessions
from iatb.core.config import Config
from iatb.core.engine import Engine
from iatb.core.enums import Exchange, MarketType, OrderSide, OrderStatus, OrderType
from iatb.core.event_bus import EventBus
from iatb.core.events import (
    MarketTickEvent,
    OrderUpdateEvent,
    SignalEvent,
)
from iatb.core.exceptions import EngineError, ValidationError
from iatb.core.types import Price, Quantity


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")

def create_market_tick(symbol: str, price: str, quantity: str = "100") -> MarketTickEvent:
    """Create a demo market tick event."""
    return MarketTickEvent(
        exchange=Exchange.NSE,
        symbol=symbol,
        price=Decimal(price),
        quantity=Decimal(quantity),
    )


def create_signal(
    symbol: str,
    side: OrderSide,
    confidence: str | Decimal,
    strategy_id: str,
    quantity: str = "100",
) -> SignalEvent:
    """Create a demo signal event."""
    return SignalEvent(
        strategy_id=strategy_id,
        exchange=Exchange.NSE,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        confidence=Decimal(str(confidence)),
    )


def create_order_update() -> OrderUpdateEvent:
    """Create a demo order update event."""
    return OrderUpdateEvent(
        order_id="ORD-2024-001",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("50"),
        price=Decimal("2450.50"),
        filled_quantity=Decimal("50"),
        avg_price=Decimal("2450.50"),
        status=OrderStatus.FILLED,
    )


def print_market_tick(tick: MarketTickEvent) -> None:
    """Print market tick event details."""
    print("\nMarket Tick Event:")
    print(f"  Event ID: {tick.event_id}")
    print(f"  Timestamp: {tick.timestamp.isoformat()}")
    print(f"  Symbol: {tick.symbol}")
    print(f"  Price: ₹{tick.price}")
    print(f"  Quantity: {tick.quantity}")


def print_order_update(order: OrderUpdateEvent) -> None:
    """Print order update event details."""
    print("\nOrder Update Event:")
    print(f"  Order ID: {order.order_id}")
    print(f"  Status: {order.status.name}")
    print(f"  Filled: {order.filled_quantity} @ ₹{order.avg_price}")
    print(f"  Side: {order.side.name}")


def print_signal(signal: SignalEvent) -> None:
    """Print signal event details."""
    print("\nSignal Event:")
    print(f"  Strategy: {signal.strategy_id}")
    print(f"  Action: {signal.side.name}")
    print(f"  Confidence: {signal.confidence:.2%}")
    print(f"  Quantity: {signal.quantity}")


def example_1_types_and_enums() -> None:
    """Example 1: Using types and enums."""
    print_section("Example 1: Types and Enums")

    # Type-safe price and quantity
    entry_price: Price = Decimal("2450.50")
    quantity: Quantity = Decimal("50")

    print("\nTrade Setup:")
    print(f"  Entry Price: ₹{entry_price}")
    print(f"  Quantity: {quantity} shares")
    print(f"  Position Value: ₹{entry_price * quantity}")

    # Using enums
    print("\nOrder Details:")
    print(f"  Exchange: {Exchange.NSE.name}")
    print(f"  Market Type: {MarketType.SPOT.name}")
    print(f"  Order Side: {OrderSide.BUY.name}")
    print(f"  Order Type: {OrderType.LIMIT.name}")

    # Calculate target and stop loss
    target_price = entry_price * Decimal("1.05")  # 5% target
    stop_loss = entry_price * Decimal("0.98")     # 2% stop loss

    print("\nRisk Management:")
    print(f"  Target Price: ₹{target_price:.2f}")
    print(f"  Stop Loss: ₹{stop_loss:.2f}")
    print(f"  Risk per Share: ₹{entry_price - stop_loss:.2f}")
    print(f"  Total Risk: ₹{(entry_price - stop_loss) * quantity:.2f}")


def example_2_creating_events() -> None:
    """Example 2: Creating and using events."""
    print_section("Example 2: Creating Events")
    tick = create_market_tick(symbol="RELIANCE", price="2450.75")
    order = create_order_update()
    signal = create_signal(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        confidence=Decimal("0.87"),
        strategy_id="MA_CROSSOVER",
        quantity="50",
    )
    print_market_tick(tick)
    print_order_update(order)
    print_signal(signal)


async def example_3_event_bus() -> None:
    """Example 3: Using the event bus."""
    print_section("Example 3: Event Bus (Pub/Sub)")
    bus = EventBus()
    await bus.start()
    try:
        print("\nSetting up topic queues...")
        tick_queue = await bus.subscribe("market.ticks.NSE")
        signal_queue = await bus.subscribe("signals.trading")
        print("\nPublishing events...")
        await bus.publish("market.ticks.NSE", create_market_tick("RELIANCE", "2450.75"))
        await bus.publish(
            "signals.trading",
            create_signal("RELIANCE", OrderSide.BUY, Decimal("0.85"), "MA_CROSSOVER"),
        )
        received_tick = await asyncio.wait_for(tick_queue.get(), timeout=1.0)
        received_signal = await asyncio.wait_for(signal_queue.get(), timeout=1.0)
        print("\nResults:")
        print(f"  Tick received: {received_tick.symbol} @ ₹{received_tick.price}")
        print(
            f"  Signal received: {received_signal.side.name} {received_signal.symbol} "
            f"(confidence: {received_signal.confidence:.2%})"
        )
    finally:
        await bus.stop()


async def example_4_engine() -> None:
    """Example 4: Using the engine orchestrator."""
    print_section("Example 4: Engine Orchestrator")

    engine = Engine()

    print("\nStarting engine...")
    await engine.start()
    print(f"  Engine running: {engine.is_running}")
    print(f"  Event bus ready: {engine.event_bus._running}")

    # Subscribe to events
    events = []

    async def event_handler(event: MarketTickEvent) -> None:
        events.append(event)

    await engine.event_bus.subscribe("market.*", event_handler)

    # Run a task
    print("\nRunning background task...")

    async def data_feed_task() -> None:
        """Simulate data feed."""
        for i in range(3):
            tick = MarketTickEvent(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                price=Decimal(str(2450.0 + i * 10)),
                quantity=Decimal("100"),
            )
            await engine.event_bus.publish("market.ticks", tick)
            await asyncio.sleep(0.01)

    await engine.run_task(data_feed_task())
    await asyncio.sleep(0.1)

    print(f"  Events received: {len(events)}")

    print("\nStopping engine...")
    await engine.stop()
    print(f"  Engine running: {engine.is_running}")


def example_5_clock_and_sessions() -> None:
    """Example 5: Using clock and session helpers."""
    print_section("Example 5: Clock and Market Sessions")

    clock = Clock()

    # Get current UTC time
    utc_now = Clock.now()
    print(f"\nCurrent Time (UTC): {utc_now.isoformat()}")

    # Check market sessions
    print("\nMarket Sessions:")

    for exchange in [Exchange.NSE, Exchange.MCX, Exchange.CDS]:
        is_active = TradingSessions.is_market_open(utc_now, exchange)

        # Get session times
        if exchange == Exchange.NSE:
            open_time = "09:15"
            close_time = "15:30"
        elif exchange == Exchange.MCX:
            open_time = "09:00"
            close_time = "23:30"
        elif exchange == Exchange.CDS:
            open_time = "09:00"
            close_time = "17:00"
        else:
            open_time = "N/A"
            close_time = "N/A"

        status = "🟢 OPEN" if is_active else "🔴 CLOSED"
        print(f"\n  {exchange.name}:")
        print(f"    Session: {open_time} - {close_time} IST")
        print(f"    Status: {status}")


def example_6_configuration() -> None:
    """Example 6: Using configuration."""
    print_section("Example 6: Configuration")

    config = Config()

    print("\nCurrent Configuration:")
    print(f"  Log Level: {config.log_level}")
    print(f"  Timezone: {config.timezone}")
    print(f"  Event Bus Queue Size: {config.event_bus_queue_size}")
    print(f"  Engine Max Tasks: {config.engine_max_tasks}")
    print(f"  Clock Update Interval: {config.clock_update_interval}s")

    print("\nEnvironment-based configuration can be set via .env file:")
    print("  IATB_LOG_LEVEL=DEBUG")
    print("  IATB_TIMEZONE=UTC")
    print("  IATB_EVENT_BUS_QUEUE_SIZE=1000")


def example_7_error_handling() -> None:
    """Example 7: Error handling."""
    print_section("Example 7: Error Handling")

    print("\nValidation Error Example:")
    try:
        # Simulate validation error
        if Decimal("-1.0") < Decimal("0"):
            raise ValidationError("Price cannot be negative")
    except ValidationError as e:
        print(f"  Caught ValidationError: {e.message}")

    print("\nEngine Error Example:")
    try:
        # Try to use engine without starting
        raise EngineError("Engine not running")
    except EngineError as e:
        print(f"  Caught EngineError: {e.message}")

    print("\nProper error handling pattern:")
    print("""
    try:
        price = validate_price(input_price)
        create_order(symbol, price, quantity)
    except ValidationError as e:
        logger.error(f"Invalid input: {e.message}")
        # Handle validation error
    except EngineError as e:
        logger.error(f"System error: {e.message}")
        # Handle system error
    """)


async def example_8_complete_workflow() -> None:
    """Example 8: Complete trading workflow."""
    print_section("Example 8: Complete Workflow")
    print("\nInitializing trading system...")
    engine = Engine()
    await engine.start()
    signal_queue = await engine.event_bus.subscribe("signals.trading")
    is_open = TradingSessions.is_market_open(Clock.now(), Exchange.NSE)
    print(f"  Market Status: {'OPEN' if is_open else 'CLOSED'}")
    await engine.run_task(publish_workflow_signals(engine))
    first_signal = await asyncio.wait_for(signal_queue.get(), timeout=1.0)
    second_signal = await asyncio.wait_for(signal_queue.get(), timeout=1.0)
    print_signal_summary(first_signal)
    print_signal_summary(second_signal)
    print("\n  Signals generated: 2")
    await engine.stop()
    print("\n  System shutdown complete")


async def publish_workflow_signals(engine: Engine) -> None:
    """Publish two demo workflow signals."""
    buy_signal = create_signal("RELIANCE", OrderSide.BUY, Decimal("0.85"), "MA_CROSSOVER")
    await engine.event_bus.publish("signals.trading", buy_signal)
    await asyncio.sleep(0.02)
    sell_signal = create_signal("TCS", OrderSide.SELL, Decimal("0.78"), "RSI_OVERBOUGHT")
    await engine.event_bus.publish("signals.trading", sell_signal)


def print_signal_summary(signal: SignalEvent) -> None:
    """Print a compact signal summary line block."""
    print(f"\n  📊 Signal: {signal.side.name} {signal.symbol}")
    print(f"     Confidence: {signal.confidence:.2%}")
    print(f"     Strategy: {signal.strategy_id}")


def main() -> None:
    """Run all examples."""
    print("\n" + "=" * 70)
    print("  CORE EVENT ARCHITECTURE - USAGE EXAMPLES")
    print("=" * 70)

    # Synchronous examples
    example_1_types_and_enums()
    example_2_creating_events()
    example_5_clock_and_sessions()
    example_6_configuration()
    example_7_error_handling()

    # Async examples
    asyncio.run(example_3_event_bus())
    asyncio.run(example_4_engine())
    asyncio.run(example_8_complete_workflow())

    print_section("Examples Complete")
    print("\n✅ All examples executed successfully!")
    print("\nFor more information, see:")
    print("  - scripts/verify_core_architecture.py - Verification script")
    print("  - scripts/run_quality_gates.py - Quality gates check")
    print("  - scripts/VERIFICATION_GUIDE.md - Verification guide")


if __name__ == "__main__":
    main()
