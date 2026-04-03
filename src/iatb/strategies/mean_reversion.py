"""
Mean-reversion strategy using Bollinger bands and volume confirmation.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.base import StrategyBase, StrategyContext


@dataclass(frozen=True)
class MeanReversionInputs:
    close_price: Decimal
    upper_band: Decimal
    lower_band: Decimal
    basis: Decimal
    volume_ratio: Decimal


class MeanReversionStrategy(StrategyBase):
    """Reversion strategy that enters only with supportive volume."""

    def __init__(self, *, min_volume_ratio: Decimal = Decimal("1.2")) -> None:
        super().__init__(strategy_id="mean_reversion")
        self._min_volume_ratio = min_volume_ratio

    def on_bands(
        self,
        context: StrategyContext,
        inputs: MeanReversionInputs,
    ) -> SignalEvent | None:
        if not self.can_emit_signal(context):
            return None
        if inputs.volume_ratio < self._min_volume_ratio:
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
    def _resolve_side(inputs: MeanReversionInputs) -> OrderSide | None:
        if inputs.close_price <= inputs.lower_band:
            return OrderSide.BUY
        if inputs.close_price >= inputs.upper_band:
            return OrderSide.SELL
        return None

    @staticmethod
    def _confidence(inputs: MeanReversionInputs) -> Decimal:
        distance = abs(inputs.close_price - inputs.basis)
        basis = max(abs(inputs.basis), Decimal("1"))
        reversion_factor = min(Decimal("0.7"), distance / basis)
        volume_factor = min(Decimal("0.3"), inputs.volume_ratio / Decimal("5"))
        return max(Decimal("0.1"), min(Decimal("1"), reversion_factor + volume_factor))
