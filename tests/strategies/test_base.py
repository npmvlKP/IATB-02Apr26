from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
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
