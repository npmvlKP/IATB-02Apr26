import random
from datetime import UTC
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange, OrderSide
from iatb.core.event_bus import EventBus
from iatb.core.events import SignalEvent
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyBase, StrategyContext

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_strategy_base_pre_trade_gate_allows_tradable_context() -> None:
    strategy = StrategyBase()
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.7"),
            regime=MarketRegime.BULL,
            adx=Decimal("31"),
            volume_ratio=Decimal("1.6"),
            volatility_atr_pct=Decimal("0.03"),
        ),
    )
    assert strategy.can_emit_signal(context)


def test_strategy_base_pre_trade_gate_blocks_invalid_symbol() -> None:
    strategy = StrategyBase()
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol=" ",
        side=OrderSide.BUY,
        strength_inputs=StrategyBase.neutral_strength_inputs(),
    )
    assert not strategy.can_emit_signal(context)


def test_strategy_base_on_signal_maps_to_strategy_order() -> None:
    strategy = StrategyBase(strategy_id="base_test")
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.7"),
            regime=MarketRegime.BULL,
            adx=Decimal("31"),
            volume_ratio=Decimal("1.6"),
            volatility_atr_pct=Decimal("0.03"),
        ),
    )
    signal = strategy.build_signal(
        context,
        OrderSide.BUY,
        Decimal("0.8"),
        price=Decimal("2500"),
    )
    order = strategy.on_signal(context, signal)
    assert order is not None
    assert order.symbol == "RELIANCE"
    assert order.side == OrderSide.BUY


@pytest.mark.asyncio
async def test_strategy_base_emit_signal_publishes_to_event_bus() -> None:
    strategy = StrategyBase(strategy_id="base_test")
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrategyBase.neutral_strength_inputs(),
    )
    signal = strategy.build_signal(context, OrderSide.BUY, Decimal("0.7"))
    bus = EventBus()
    await bus.start()
    queue = await bus.subscribe("signal")
    await strategy.emit_signal(bus, signal)
    received = await queue.get()
    await bus.stop()
    assert isinstance(received, SignalEvent)


def test_strategy_base_pre_trade_gate_blocks_bearish_strength() -> None:
    strategy = StrategyBase()
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("2.0"),
            regime=MarketRegime.BEAR,
            adx=Decimal("40"),
            volume_ratio=Decimal("2.0"),
            volatility_atr_pct=Decimal("0.02"),
        ),
    )
    assert not strategy.can_emit_signal(context)


def test_strategy_base_on_tick_returns_none() -> None:
    """Test that on_tick returns None by default."""
    strategy = StrategyBase()
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrategyBase.neutral_strength_inputs(),
    )
    from datetime import datetime

    from iatb.core.events import MarketTickEvent

    tick = MarketTickEvent(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        price=Decimal("2500"),
        quantity=Decimal("100"),
        timestamp=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    result = strategy.on_tick(context, tick)
    assert result is None


def test_strategy_base_on_bar_returns_none() -> None:
    """Test that on_bar returns None by default."""
    strategy = StrategyBase()
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrategyBase.neutral_strength_inputs(),
    )
    from datetime import datetime

    from iatb.core.events import MarketTickEvent

    tick = MarketTickEvent(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        price=Decimal("2500"),
        quantity=Decimal("100"),
        timestamp=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    result = strategy.on_bar(context, tick)
    assert result is None


def test_strategy_base_on_signal_blocks_when_not_tradable() -> None:
    """Test that on_signal returns None when context is not tradable."""
    strategy = StrategyBase(strategy_id="base_test")
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.BEAR,
            adx=Decimal("15"),
            volume_ratio=Decimal("0.8"),
            volatility_atr_pct=Decimal("0.02"),
        ),
    )
    signal = strategy.build_signal(
        context,
        OrderSide.BUY,
        Decimal("0.8"),
        price=Decimal("2500"),
    )
    order = strategy.on_signal(context, signal)
    assert order is None


def test_strategy_base_on_signal_blocks_on_symbol_mismatch() -> None:
    """Test that on_signal returns None when signal symbol doesn't match context."""
    strategy = StrategyBase(strategy_id="base_test")
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.7"),
            regime=MarketRegime.BULL,
            adx=Decimal("31"),
            volume_ratio=Decimal("1.6"),
            volatility_atr_pct=Decimal("0.03"),
        ),
    )
    # Build signal with different symbol
    signal = SignalEvent(
        strategy_id="base_test",
        exchange=Exchange.NSE,
        symbol="TCS",  # Different symbol
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("3500"),
        confidence=Decimal("0.8"),
    )
    order = strategy.on_signal(context, signal)
    assert order is None


def test_strategy_base_build_signal_binds_confidence_to_range() -> None:
    """Test that build_signal bounds confidence to [0, 1]."""
    strategy = StrategyBase(strategy_id="base_test")
    context = StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrategyBase.neutral_strength_inputs(),
    )
    # Test confidence > 1
    signal = strategy.build_signal(context, OrderSide.BUY, Decimal("1.5"))
    assert signal.confidence == Decimal("1")
    # Test confidence < 0
    signal = strategy.build_signal(context, OrderSide.BUY, Decimal("-0.5"))
    assert signal.confidence == Decimal("0")
    # Test confidence in range
    signal = strategy.build_signal(context, OrderSide.BUY, Decimal("0.7"))
    assert signal.confidence == Decimal("0.7")
