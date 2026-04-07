from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.event_bus import EventBus
from iatb.core.events import SignalEvent
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyBase, StrategyContext


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
