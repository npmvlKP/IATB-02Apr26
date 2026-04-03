"""
Breakout strategy using Donchian channels and squeeze confirmation.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.base import StrategyBase, StrategyContext


@dataclass(frozen=True)
class BreakoutInputs:
    close_price: Decimal
    donchian_high: Decimal
    donchian_low: Decimal
    squeeze_active: bool
    volume_ratio: Decimal


class BreakoutStrategy(StrategyBase):
    """Breakout strategy gated by squeeze and volume-expansion conditions."""

    def __init__(self, *, min_volume_ratio: Decimal = Decimal("2.0")) -> None:
        super().__init__(strategy_id="breakout")
        self._min_volume_ratio = min_volume_ratio

    def on_breakout(
        self,
        context: StrategyContext,
        inputs: BreakoutInputs,
    ) -> SignalEvent | None:
        if not self.can_emit_signal(context):
            return None
        if not inputs.squeeze_active or inputs.volume_ratio < self._min_volume_ratio:
            return None
        side = self._resolve_side(inputs)
        if side is None:
            return None
        confidence = self._confidence(inputs)
        return self.build_signal(
            context,
            side,
            confidence,
            price=inputs.close_price,
        )

    @staticmethod
    def _resolve_side(inputs: BreakoutInputs) -> OrderSide | None:
        if inputs.close_price > inputs.donchian_high:
            return OrderSide.BUY
        if inputs.close_price < inputs.donchian_low:
            return OrderSide.SELL
        return None

    @staticmethod
    def _confidence(inputs: BreakoutInputs) -> Decimal:
        reference = (
            inputs.donchian_high
            if inputs.close_price >= inputs.donchian_high
            else inputs.donchian_low
        )
        breakout_distance = abs(inputs.close_price - reference)
        baseline = max(abs(reference), Decimal("1"))
        distance_factor = min(Decimal("0.6"), breakout_distance / baseline)
        volume_factor = min(Decimal("0.4"), inputs.volume_ratio / Decimal("5"))
        return max(Decimal("0.2"), min(Decimal("1"), distance_factor + volume_factor))
