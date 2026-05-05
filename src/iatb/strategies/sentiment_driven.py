"""
Sentiment-driven strategy using VERY_STRONG sentiment and volume confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from iatb.core.enums import OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.base import StrategyBase, StrategyContext

if TYPE_CHECKING:
    from iatb.sentiment.aggregator import SentimentAggregator


@dataclass(frozen=True)
class SentimentDrivenInputs:
    text: str
    volume_ratio: Decimal
    reference_price: Decimal | None = None


class SentimentDrivenStrategy(StrategyBase):
    """Directional strategy based on tradable VERY_STRONG sentiment output."""

    def __init__(self, sentiment_aggregator: SentimentAggregator | None = None) -> None:
        from iatb.sentiment.aggregator import SentimentAggregator

        super().__init__(strategy_id="sentiment_driven")
        self._aggregator = sentiment_aggregator or SentimentAggregator()

    def on_sentiment(
        self,
        context: StrategyContext,
        inputs: SentimentDrivenInputs,
    ) -> SignalEvent | None:
        if not self.can_emit_signal(context):
            return None
        gate_result = self._aggregator.evaluate_instrument(inputs.text, inputs.volume_ratio)
        if not gate_result.tradable:
            return None
        side = self._resolve_side(gate_result.composite.score)
        if side is None:
            return None
        confidence = min(Decimal("1"), gate_result.composite.confidence + Decimal("0.10"))
        return self.build_signal(
            context,
            side,
            confidence,
            price=inputs.reference_price,
        )

    @staticmethod
    def _resolve_side(composite_score: Decimal) -> OrderSide | None:
        if composite_score > Decimal("0"):
            return OrderSide.BUY
        if composite_score < Decimal("0"):
            return OrderSide.SELL
        return None
