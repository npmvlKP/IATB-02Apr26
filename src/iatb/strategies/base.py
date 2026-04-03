"""
Strategy base contract with market-strength pre-trade gate.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer


@dataclass(frozen=True)
class StrategyContext:
    exchange: Exchange
    symbol: str
    side: OrderSide
    strength_inputs: StrengthInputs


class StrategyBase:
    """Base class that enforces market-strength tradability gates."""

    def __init__(self, strength_scorer: StrengthScorer | None = None) -> None:
        self._strength_scorer = strength_scorer or StrengthScorer()

    def is_tradable(self, exchange: Exchange, inputs: StrengthInputs) -> bool:
        return self._strength_scorer.is_tradable(exchange, inputs)

    def can_emit_signal(self, context: StrategyContext) -> bool:
        if not context.symbol.strip():
            return False
        return self.is_tradable(context.exchange, context.strength_inputs)

    @staticmethod
    def neutral_strength_inputs() -> StrengthInputs:
        return StrengthInputs(
            breadth_ratio=Decimal("1.0"),
            regime=MarketRegime.SIDEWAYS,
            adx=Decimal("20"),
            volume_ratio=Decimal("1.0"),
            volatility_atr_pct=Decimal("0.03"),
        )
