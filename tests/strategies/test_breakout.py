from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyContext
from iatb.strategies.breakout import BreakoutInputs, BreakoutStrategy


def _context() -> StrategyContext:
    return StrategyContext(
        exchange=Exchange.NSE,
        symbol="TCS",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.7"),
            regime=MarketRegime.BULL,
            adx=Decimal("32"),
            volume_ratio=Decimal("1.8"),
            volatility_atr_pct=Decimal("0.03"),
        ),
    )


def test_breakout_strategy_emits_buy_signal_when_breakout_confirmed() -> None:
    strategy = BreakoutStrategy()
    signal = strategy.on_breakout(
        _context(),
        BreakoutInputs(
            close_price=Decimal("4020"),
            donchian_high=Decimal("4000"),
            donchian_low=Decimal("3900"),
            squeeze_active=True,
            volume_ratio=Decimal("2.4"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.BUY


def test_breakout_strategy_emits_sell_signal_when_breakdown_confirmed() -> None:
    strategy = BreakoutStrategy()
    signal = strategy.on_breakout(
        _context(),
        BreakoutInputs(
            close_price=Decimal("3880"),
            donchian_high=Decimal("4000"),
            donchian_low=Decimal("3900"),
            squeeze_active=True,
            volume_ratio=Decimal("2.3"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.SELL


def test_breakout_strategy_blocks_without_squeeze_or_volume() -> None:
    strategy = BreakoutStrategy()
    without_squeeze = strategy.on_breakout(
        _context(),
        BreakoutInputs(
            close_price=Decimal("4020"),
            donchian_high=Decimal("4000"),
            donchian_low=Decimal("3900"),
            squeeze_active=False,
            volume_ratio=Decimal("2.5"),
        ),
    )
    low_volume = strategy.on_breakout(
        _context(),
        BreakoutInputs(
            close_price=Decimal("4020"),
            donchian_high=Decimal("4000"),
            donchian_low=Decimal("3900"),
            squeeze_active=True,
            volume_ratio=Decimal("1.5"),
        ),
    )
    assert without_squeeze is None
    assert low_volume is None
