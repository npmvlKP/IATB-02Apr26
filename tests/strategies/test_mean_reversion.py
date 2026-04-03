from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyContext
from iatb.strategies.mean_reversion import MeanReversionInputs, MeanReversionStrategy


def _context() -> StrategyContext:
    return StrategyContext(
        exchange=Exchange.NSE,
        symbol="HDFCBANK",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.5"),
            regime=MarketRegime.SIDEWAYS,
            adx=Decimal("24"),
            volume_ratio=Decimal("1.4"),
            volatility_atr_pct=Decimal("0.02"),
        ),
    )


def test_mean_reversion_strategy_emits_buy_signal_on_lower_band_touch() -> None:
    strategy = MeanReversionStrategy()
    signal = strategy.on_bands(
        _context(),
        MeanReversionInputs(
            close_price=Decimal("1520"),
            upper_band=Decimal("1580"),
            lower_band=Decimal("1520"),
            basis=Decimal("1550"),
            volume_ratio=Decimal("1.5"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.BUY


def test_mean_reversion_strategy_emits_sell_signal_on_upper_band_touch() -> None:
    strategy = MeanReversionStrategy()
    signal = strategy.on_bands(
        _context(),
        MeanReversionInputs(
            close_price=Decimal("1585"),
            upper_band=Decimal("1580"),
            lower_band=Decimal("1520"),
            basis=Decimal("1550"),
            volume_ratio=Decimal("1.6"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.SELL


def test_mean_reversion_strategy_blocks_without_volume_confirmation() -> None:
    strategy = MeanReversionStrategy()
    signal = strategy.on_bands(
        _context(),
        MeanReversionInputs(
            close_price=Decimal("1520"),
            upper_band=Decimal("1580"),
            lower_band=Decimal("1520"),
            basis=Decimal("1550"),
            volume_ratio=Decimal("1.0"),
        ),
    )
    assert signal is None
