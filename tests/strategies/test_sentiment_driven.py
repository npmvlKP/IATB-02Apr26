import random
from decimal import Decimal

import numpy as np
import torch
from iatb.core.enums import Exchange, OrderSide
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.sentiment.aggregator import SentimentGateResult
from iatb.sentiment.base import SentimentScore
from iatb.strategies.base import StrategyContext
from iatb.strategies.sentiment_driven import SentimentDrivenInputs, SentimentDrivenStrategy

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _StubAggregator:
    def __init__(self, result: SentimentGateResult) -> None:
        self._result = result

    def evaluate_instrument(self, text: str, volume_ratio: Decimal) -> SentimentGateResult:
        _ = (text, volume_ratio)
        return self._result


def _context(*, regime: MarketRegime = MarketRegime.BULL) -> StrategyContext:
    return StrategyContext(
        exchange=Exchange.NSE,
        symbol="SBIN",
        side=OrderSide.BUY,
        strength_inputs=StrengthInputs(
            breadth_ratio=Decimal("1.8"),
            regime=regime,
            adx=Decimal("30"),
            volume_ratio=Decimal("1.7"),
            volatility_atr_pct=Decimal("0.02"),
        ),
    )


def _gate_result(score: Decimal, tradable: bool = True) -> SentimentGateResult:
    return SentimentGateResult(
        composite=SentimentScore(
            source="ensemble",
            score=score,
            confidence=Decimal("0.82"),
            label="POSITIVE" if score > 0 else "NEGATIVE",
        ),
        very_strong=True,
        volume_confirmed=True,
        tradable=tradable,
        component_scores={"finbert": score},
    )


def test_sentiment_strategy_emits_buy_for_positive_very_strong_signal() -> None:
    strategy = SentimentDrivenStrategy(
        sentiment_aggregator=_StubAggregator(_gate_result(Decimal("0.8")))
    )
    signal = strategy.on_sentiment(
        _context(),
        SentimentDrivenInputs(
            text="PSU banks rally after credit growth surprise.",
            volume_ratio=Decimal("1.9"),
            reference_price=Decimal("785"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.BUY


def test_sentiment_strategy_emits_sell_for_negative_very_strong_signal() -> None:
    strategy = SentimentDrivenStrategy(
        sentiment_aggregator=_StubAggregator(_gate_result(Decimal("-0.81")))
    )
    signal = strategy.on_sentiment(
        _context(),
        SentimentDrivenInputs(
            text="Auto stocks slide after weak volume guidance.",
            volume_ratio=Decimal("1.8"),
            reference_price=Decimal("1310"),
        ),
    )
    assert signal is not None
    assert signal.side == OrderSide.SELL


def test_sentiment_strategy_blocks_on_untradable_sentiment_or_strength() -> None:
    blocked_sentiment = SentimentDrivenStrategy(
        sentiment_aggregator=_StubAggregator(_gate_result(Decimal("0.8"), tradable=False))
    )
    sentiment_signal = blocked_sentiment.on_sentiment(
        _context(),
        SentimentDrivenInputs(
            text="Mixed outlook in overnight market wrap.",
            volume_ratio=Decimal("1.7"),
        ),
    )
    blocked_strength = SentimentDrivenStrategy(
        sentiment_aggregator=_StubAggregator(_gate_result(Decimal("0.8")))
    )
    strength_signal = blocked_strength.on_sentiment(
        _context(regime=MarketRegime.BEAR),
        SentimentDrivenInputs(
            text="Strong positive surprise in earnings.",
            volume_ratio=Decimal("1.9"),
        ),
    )
    assert sentiment_signal is None
    assert strength_signal is None
