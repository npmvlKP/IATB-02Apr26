"""
Multi-strategy ensemble voting strategy.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.base import StrategyBase, StrategyContext


@dataclass(frozen=True)
class WeightedSignal:
    signal: SignalEvent
    weight: Decimal


class EnsembleStrategy(StrategyBase):
    """Combine strategy signals with weighted directional voting."""

    def __init__(self, *, vote_threshold: Decimal = Decimal("0.55")) -> None:
        super().__init__(strategy_id="ensemble")
        self._vote_threshold = vote_threshold

    def on_signals(
        self,
        context: StrategyContext,
        weighted_signals: list[WeightedSignal],
    ) -> SignalEvent | None:
        if not self.can_emit_signal(context):
            return None
        if not weighted_signals:
            return None
        buy_score, sell_score, total_weight, weighted_price = self._accumulate(weighted_signals)
        if total_weight <= Decimal("0"):
            return None
        side, side_score = self._winning_side(buy_score, sell_score)
        if side is None:
            return None
        confidence = side_score / total_weight
        if confidence < self._vote_threshold:
            return None
        return self.build_signal(
            context,
            side,
            confidence,
            price=weighted_price,
        )

    @staticmethod
    def _accumulate(
        weighted_signals: list[WeightedSignal],
    ) -> tuple[Decimal, Decimal, Decimal, Decimal | None]:
        buy_score = Decimal("0")
        sell_score = Decimal("0")
        total_weight = Decimal("0")
        price_weight = Decimal("0")
        weighted_price_sum = Decimal("0")
        for candidate in weighted_signals:
            contribution = candidate.weight * candidate.signal.confidence
            total_weight += candidate.weight
            if candidate.signal.side == OrderSide.BUY:
                buy_score += contribution
            else:
                sell_score += contribution
            if candidate.signal.price is not None:
                weighted_price_sum += candidate.signal.price * candidate.weight
                price_weight += candidate.weight
        if price_weight == Decimal("0"):
            return buy_score, sell_score, total_weight, None
        return buy_score, sell_score, total_weight, weighted_price_sum / price_weight

    @staticmethod
    def _winning_side(buy_score: Decimal, sell_score: Decimal) -> tuple[OrderSide | None, Decimal]:
        if buy_score > sell_score:
            return OrderSide.BUY, buy_score
        if sell_score > buy_score:
            return OrderSide.SELL, sell_score
        return None, Decimal("0")
