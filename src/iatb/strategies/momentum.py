"""
Momentum strategy using dual moving averages with RSI and ADX filters.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.events import SignalEvent
from iatb.strategies.base import StrategyBase, StrategyContext


@dataclass(frozen=True)
class MomentumInputs:
    fast_ma: Decimal
    slow_ma: Decimal
    rsi: Decimal
    adx: Decimal
    close_price: Decimal


class MomentumStrategy(StrategyBase):
    """Trend-following strategy with market-strength and trend confirmation gates."""

    def __init__(
        self,
        *,
        min_adx: Decimal = Decimal("20"),
        buy_rsi: Decimal = Decimal("55"),
        sell_rsi: Decimal = Decimal("45"),
    ) -> None:
        super().__init__(strategy_id="momentum")
        self._min_adx = min_adx
        self._buy_rsi = buy_rsi
        self._sell_rsi = sell_rsi

    def on_indicators(
        self,
        context: StrategyContext,
        inputs: MomentumInputs,
    ) -> SignalEvent | None:
        if not self.can_emit_signal(context) or inputs.adx < self._min_adx:
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

    def _resolve_side(self, inputs: MomentumInputs) -> OrderSide | None:
        bullish = inputs.fast_ma > inputs.slow_ma and inputs.rsi >= self._buy_rsi
        bearish = inputs.fast_ma < inputs.slow_ma and inputs.rsi <= self._sell_rsi
        if bullish:
            return OrderSide.BUY
        if bearish:
            return OrderSide.SELL
        return None

    @staticmethod
    def _confidence(inputs: MomentumInputs) -> Decimal:
        spread = abs(inputs.fast_ma - inputs.slow_ma)
        baseline = max(abs(inputs.slow_ma), Decimal("1"))
        spread_factor = min(Decimal("0.6"), spread / baseline)
        trend_factor = min(Decimal("0.4"), inputs.adx / Decimal("100"))
        return max(Decimal("0.1"), min(Decimal("1"), spread_factor + trend_factor))
