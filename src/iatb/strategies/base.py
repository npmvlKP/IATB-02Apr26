"""
Strategy contracts with market-strength pre-trade gate.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from iatb.core.enums import Exchange, OrderSide, OrderType
from iatb.core.event_bus import EventBus
from iatb.core.events import MarketTickEvent, SignalEvent
from iatb.core.types import Quantity, create_price, create_quantity
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer


@dataclass(frozen=True)
class StrategyContext:
    exchange: Exchange
    symbol: str
    side: OrderSide
    strength_inputs: StrengthInputs
    composite_score: Decimal | None = None
    selection_rank: int | None = None


@dataclass(frozen=True)
class StrategyOrder:
    exchange: Exchange
    symbol: str
    side: OrderSide
    quantity: Quantity
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = None


@runtime_checkable
class Strategy(Protocol):
    def on_tick(self, context: StrategyContext, tick: MarketTickEvent) -> SignalEvent | None:
        ...

    def on_bar(self, context: StrategyContext, tick: MarketTickEvent) -> SignalEvent | None:
        ...

    def on_signal(self, context: StrategyContext, signal: SignalEvent) -> StrategyOrder | None:
        ...


class StrategyBase:
    """Base class that enforces market-strength tradability gates."""

    def __init__(
        self,
        strategy_id: str = "base_strategy",
        strength_scorer: StrengthScorer | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._strength_scorer = strength_scorer or StrengthScorer()

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    def is_tradable(self, exchange: Exchange, inputs: StrengthInputs) -> bool:
        return self._strength_scorer.is_tradable(exchange, inputs)

    def can_emit_signal(self, context: StrategyContext) -> bool:
        if not context.symbol.strip():
            return False
        if not self.is_tradable(context.exchange, context.strength_inputs):
            return False
        if context.selection_rank is not None and context.selection_rank < 1:
            return False
        return True

    def on_tick(self, context: StrategyContext, tick: MarketTickEvent) -> SignalEvent | None:
        _ = (context, tick)
        return None

    def on_bar(self, context: StrategyContext, tick: MarketTickEvent) -> SignalEvent | None:
        _ = (context, tick)
        return None

    def on_signal(self, context: StrategyContext, signal: SignalEvent) -> StrategyOrder | None:
        if not self.can_emit_signal(context):
            return None
        if signal.exchange != context.exchange or signal.symbol != context.symbol:
            return None
        return StrategyOrder(
            exchange=signal.exchange,
            symbol=signal.symbol,
            side=signal.side,
            quantity=signal.quantity,
            price=signal.price,
        )

    def build_signal(
        self,
        context: StrategyContext,
        side: OrderSide,
        confidence: Decimal,
        *,
        price: Decimal | None = None,
        quantity: Decimal = Decimal("1"),
    ) -> SignalEvent:
        bounded_confidence = max(Decimal("0"), min(Decimal("1"), confidence))
        event_price = create_price(price) if price is not None else None
        event_quantity = create_quantity(quantity)
        return SignalEvent(
            strategy_id=self.strategy_id,
            exchange=context.exchange,
            symbol=context.symbol,
            side=side,
            quantity=event_quantity,
            price=event_price,
            confidence=bounded_confidence,
        )

    async def emit_signal(self, event_bus: EventBus, signal: SignalEvent) -> None:
        await event_bus.publish("signal", signal)

    @staticmethod
    def neutral_strength_inputs() -> StrengthInputs:
        return StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.SIDEWAYS,
            adx=Decimal("20"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.03"),
        )
