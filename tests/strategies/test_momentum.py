from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyContext
from iatb.strategies.momentum import MomentumInputs, MomentumStrategy


def _context(*, regime: MarketRegime = MarketRegime.BULL) -> StrategyContext:
    return StrategyContext(
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.6"),
            regime=regime,
            adx=Decimal("30"),
            volume_ratio=Decimal("1.6"),
            volatility_atr_pct=Decimal("0.03"),
        ),
    )


def test_momentum_strategy_emits_buy_signal() -> None:
    strategy = MomentumStrategy()
    signal = strategy.on_indicators(
        _context(),
        MomentumInputs(
            fast_ma=Decimal("2505"),
            slow_ma=Decimal("2475"),
            rsi=Decimal("62"),
            adx=Decimal("28"),
            close_price=Decimal("2510"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.BUY


def test_momentum_strategy_emits_sell_signal() -> None:
    strategy = MomentumStrategy()
    signal = strategy.on_indicators(
        _context(),
        MomentumInputs(
            fast_ma=Decimal("2450"),
            slow_ma=Decimal("2480"),
            rsi=Decimal("38"),
            adx=Decimal("27"),
            close_price=Decimal("2448"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.SELL


def test_momentum_strategy_blocks_low_adx_or_untradable_context() -> None:
    strategy = MomentumStrategy()
    low_adx = strategy.on_indicators(
        _context(),
        MomentumInputs(
            fast_ma=Decimal("2510"),
            slow_ma=Decimal("2480"),
            rsi=Decimal("60"),
            adx=Decimal("10"),
            close_price=Decimal("2512"),
        ),
    )
    untradable = strategy.on_indicators(
        _context(regime=MarketRegime.BEAR),
        MomentumInputs(
            fast_ma=Decimal("2510"),
            slow_ma=Decimal("2480"),
            rsi=Decimal("60"),
            adx=Decimal("35"),
            close_price=Decimal("2512"),
        ),
    )
    assert low_adx is None
    assert untradable is None
