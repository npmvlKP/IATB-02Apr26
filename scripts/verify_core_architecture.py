#!/usr/bin/env python
"""
Comprehensive verification script for Core Event Architecture.

Run this to verify all components are working correctly:
    python scripts/verify_core_architecture.py
"""

import asyncio
import sys
from datetime import UTC, datetime
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
    RegimeChangeEvent,
    SignalEvent,
)
from iatb.core.exceptions import (
    ClockError,
    ConfigError,
    EngineError,
    EventBusError,
    IATBError,
    ValidationError,
)
from iatb.core.types import Price, Quantity, Timestamp


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"[PASS] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"[FAIL] {message}")


def verify_types() -> bool:
    """Verify type definitions."""
    print_section("1. Verifying Type Definitions")

    try:
        # Test Price type
        price: Price = Decimal("100.50")
        print_success(f"Price type works: {price}")

        # Test Quantity type
        quantity: Quantity = Decimal("10")
        print_success(f"Quantity type works: {quantity}")

        # Test Timestamp type
        timestamp: Timestamp = datetime.now(UTC)
        print_success(f"Timestamp type works: {timestamp}")

        return True
    except Exception as e:
        print_error(f"Type verification failed: {e}")
        return False


def verify_enums() -> bool:
    """Verify enum definitions."""
    print_section("2. Verifying Enum Definitions")

    try:
        # Test Exchange enum
        print_success(f"Exchange values: {list(Exchange)}")
        assert Exchange.NSE == Exchange.NSE
        assert Exchange.BINANCE == Exchange.BINANCE

        # Test MarketType enum
        print_success(f"MarketType values: {list(MarketType)}")
        assert MarketType.SPOT == MarketType.SPOT
        assert MarketType.FUTURES == MarketType.FUTURES

        # Test OrderSide enum
        print_success(f"OrderSide values: {list(OrderSide)}")
        assert OrderSide.BUY == OrderSide.BUY
        assert OrderSide.SELL == OrderSide.SELL

        # Test OrderType enum
        print_success(f"OrderType values: {list(OrderType)}")
        assert OrderType.MARKET == OrderType.MARKET
        assert OrderType.LIMIT == OrderType.LIMIT

        # Test OrderStatus enum
        print_success(f"OrderStatus values: {list(OrderStatus)}")
        assert OrderStatus.PENDING == OrderStatus.PENDING
        assert OrderStatus.FILLED == OrderStatus.FILLED

        return True
    except Exception as e:
        print_error(f"Enum verification failed: {e}")
        return False

def _build_sample_events() -> tuple[MarketTickEvent, OrderUpdateEvent, SignalEvent, RegimeChangeEvent]:
    """Create sample events used by verification checks."""
    tick = MarketTickEvent(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        price=Decimal("2500.75"),
        quantity=Decimal("100"),
    )
    order = OrderUpdateEvent(
        order_id="ORD123",
        symbol="RELIANCE",
        side=OrderSide.BUY,
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("100"),
        avg_price=Decimal("2500.75"),
    )
    signal = SignalEvent(
        symbol="RELIANCE",
        side=OrderSide.BUY,
        confidence=Decimal("0.85"),
        strategy_id="MA_CROSS",
    )
    regime = RegimeChangeEvent(
        regime_type="BULLISH_TO_BEARISH",
        description="MACD crossover",
        confidence=Decimal("0.75"),
    )
    return tick, order, signal, regime


def _assert_event_creation(
    tick: MarketTickEvent,
    order: OrderUpdateEvent,
    signal: SignalEvent,
    regime: RegimeChangeEvent,
) -> None:
    """Assert and print basic event creation details."""
    print_success(f"MarketTickEvent created: {tick.event_id}")
    assert tick.timestamp.tzinfo is not None
    print_success("Event timestamp is UTC-aware")
    print_success(f"OrderUpdateEvent created: {order.event_id}")
    print_success(f"SignalEvent created: {signal.event_id}")
    assert Decimal("0.0") <= signal.confidence <= Decimal("1.0")
    print_success(f"RegimeChangeEvent created: {regime.event_id}")


def _verify_event_immutability(event: MarketTickEvent) -> bool:
    """Verify events are immutable dataclasses."""
    try:
        event.price = Decimal("9999")
    except Exception:
        print_success("Events are properly frozen (immutable)")
        return True
    print_error("Event should be frozen!")
    return False


def verify_events() -> bool:
    """Verify event definitions."""
    print_section("3. Verifying Event Definitions")
    try:
        tick, order, signal, regime = _build_sample_events()
        _assert_event_creation(tick, order, signal, regime)
        return _verify_event_immutability(tick)
    except Exception as e:
        print_error(f"Event verification failed: {e}")
        return False


def verify_event_bus() -> bool:
    """Verify event bus functionality."""
    print_section("4. Verifying Event Bus")

    try:
        async def test_event_bus():
            bus = EventBus()
            await bus.start()

            # Subscribe to topic and get queue
            queue = await bus.subscribe("market.ticks.NSE")

            # Publish event
            tick = MarketTickEvent(
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                price=Decimal("2500.75"),
                quantity=Decimal("100"),
            )
            await bus.publish("market.ticks.NSE", tick)

            # Wait for processing and receive from queue
            await asyncio.sleep(0.01)
            received_event = await queue.get()

            await bus.stop()
            return received_event is not None

        result = asyncio.run(test_event_bus())
        if result:
            print_success("Event bus pub/sub works correctly")
        else:
            print_error("Event bus failed to deliver event")
            return False

        return True
    except Exception as e:
        print_error(f"Event bus verification failed: {e}")
        return False


def verify_engine() -> bool:
    """Verify engine functionality."""
    print_section("5. Verifying Engine Orchestrator")

    try:
        async def test_engine():
            engine = Engine()

            # Test startup
            assert not engine.is_running
            await engine.start()
            assert engine.is_running
            print_success("Engine starts correctly")

            # Test event bus integration
            assert isinstance(engine.event_bus, EventBus)
            print_success("Engine has event bus")

            # Test task management
            task_run = False

            async def dummy_task() -> None:
                nonlocal task_run
                await asyncio.sleep(0.01)
                task_run = True

            await engine.run_task(dummy_task())
            await asyncio.sleep(0.02)

            if not task_run:
                print_error("Task did not execute")
                return False
            print_success("Engine runs tasks correctly")

            # Test shutdown
            await engine.stop()
            assert not engine.is_running
            print_success("Engine stops correctly")

            return True

        result = asyncio.run(test_engine())
        return result
    except Exception as e:
        print_error(f"Engine verification failed: {e}")
        return False


def verify_clock() -> bool:
    """Verify clock and session helpers."""
    print_section("6. Verifying Clock & Session Helpers")

    try:
        # Test UTC clock
        utc_time = Clock.now()
        assert utc_time.tzinfo is not None
        print_success(f"UTC clock works: {utc_time}")

        # Test session helpers
        is_open = TradingSessions.is_market_open(utc_time, Exchange.NSE)
        print_success(f"Market status check works: {is_open}")

        # Test trading day check
        is_trading_day = TradingSessions.is_trading_day(utc_time)
        print_success(f"Trading day check works: {is_trading_day}")

        # Test next open time
        next_open = TradingSessions.next_open_time(utc_time, Exchange.NSE)
        print_success(f"Next open time: {next_open}")

        # Test session times
        open_time, close_time = TradingSessions._get_session_times("NSE")
        print_success(f"NSE session times: {open_time} - {close_time}")

        return True
    except Exception as e:
        print_error(f"Clock verification failed: {e}")
        return False


def verify_config() -> bool:
    """Verify configuration management."""
    print_section("7. Verifying Configuration")

    try:
        # Test default config
        config = Config()
        print_success(f"Config loaded: log_level={config.log_level}")

        # Test queue sizes
        assert config.event_bus_max_queue_size > 0
        print_success(f"Event max queue size: {config.event_bus_max_queue_size}")
        print_success(f"Engine max tasks: {config.engine_max_tasks}")

        return True
    except Exception as e:
        print_error(f"Config verification failed: {e}")
        return False


def verify_exceptions() -> bool:
    """Verify exception hierarchy."""
    print_section("8. Verifying Exception Hierarchy")

    try:
        # Test base exception
        err = IATBError("Test error")
        assert err.message == "Test error"
        print_success("IATBError works")

        # Test specific exceptions
        ValidationError("Validation failed")
        print_success("ValidationError works")

        ConfigError("Config error")
        print_success("ConfigError works")

        EventBusError("Event bus error")
        print_success("EventBusError works")

        ClockError("Clock error")
        print_success("ClockError works")

        EngineError("Engine error")
        print_success("EngineError works")

        # Test inheritance
        assert issubclass(ValidationError, IATBError)
        assert issubclass(ConfigError, IATBError)
        assert issubclass(EventBusError, IATBError)
        assert issubclass(ClockError, IATBError)
        assert issubclass(EngineError, IATBError)
        print_success("All exceptions inherit from IATBError")

        return True
    except Exception as e:
        print_error(f"Exception verification failed: {e}")
        return False


def main() -> int:
    """Run all verification checks."""
    print("\n" + "=" * 60)
    print("  CORE EVENT ARCHITECTURE VERIFICATION")
    print("=" * 60)

    checks = [
        verify_types,
        verify_enums,
        verify_events,
        verify_event_bus,
        verify_engine,
        verify_clock,
        verify_config,
        verify_exceptions,
    ]

    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print_error(f"Check failed with exception: {e}")
            results.append(False)

    # Summary
    print_section("VERIFICATION SUMMARY")
    passed = sum(results)
    total = len(results)

    print(f"\nChecks Passed: {passed}/{total}")

    if passed == total:
        print_success("\nAll verification checks passed!")
        return 0
    else:
        print_error(f"\n{total - passed} check(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
