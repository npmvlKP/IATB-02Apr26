from decimal import Decimal

from iatb.core.enums import Exchange, OrderSide
from iatb.core.events import SignalEvent
from iatb.core.types import create_price, create_quantity
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.strategies.base import StrategyContext
from iatb.strategies.ensemble import EnsembleStrategy, WeightedSignal


def _context() -> StrategyContext:
    return StrategyContext(
        exchange=Exchange.NSE,
        symbol="INFY",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.7"),
            regime=MarketRegime.BULL,
            adx=Decimal("31"),
            volume_ratio=Decimal("1.8"),
            volatility_atr_pct=Decimal("0.02"),
        ),
    )


def _signal(
    strategy_id: str,
    side: OrderSide,
    confidence: Decimal,
    price: Decimal,
) -> SignalEvent:
    return SignalEvent(
        strategy_id=strategy_id,
        exchange=Exchange.NSE,
        symbol="INFY",
        side=side,
        quantity=create_quantity("1"),
        price=create_price(price),
        confidence=confidence,
    )


def test_ensemble_strategy_emits_weighted_majority_signal() -> None:
    strategy = EnsembleStrategy()
    signal = strategy.on_signals(
        _context(),
        [
            WeightedSignal(
                _signal("momentum", OrderSide.BUY, Decimal("0.8"), Decimal("1510")), Decimal("0.5")
            ),
            WeightedSignal(
                _signal("breakout", OrderSide.BUY, Decimal("0.7"), Decimal("1512")), Decimal("0.3")
            ),
            WeightedSignal(
                _signal("mean_reversion", OrderSide.SELL, Decimal("0.6"), Decimal("1508")),
                Decimal("0.2"),
            ),
        ],
    )
    assert signal is not None
    assert signal.side == OrderSide.BUY
    assert signal.price is not None


def test_ensemble_strategy_blocks_when_vote_threshold_not_met() -> None:
    strategy = EnsembleStrategy(vote_threshold=Decimal("0.8"))
    signal = strategy.on_signals(
        _context(),
        [
            WeightedSignal(
                _signal("momentum", OrderSide.BUY, Decimal("0.6"), Decimal("1510")), Decimal("0.5")
            ),
            WeightedSignal(
                _signal("breakout", OrderSide.SELL, Decimal("0.55"), Decimal("1507")),
                Decimal("0.5"),
            ),
        ],
    )
    assert signal is None


def test_ensemble_strategy_blocks_on_tie() -> None:
    strategy = EnsembleStrategy(vote_threshold=Decimal("0.5"))
    signal = strategy.on_signals(
        _context(),
        [
            WeightedSignal(
                _signal("momentum", OrderSide.BUY, Decimal("0.7"), Decimal("1510")), Decimal("0.5")
            ),
            WeightedSignal(
                _signal("breakout", OrderSide.SELL, Decimal("0.7"), Decimal("1507")), Decimal("0.5")
            ),
        ],
    )
    assert signal is None
