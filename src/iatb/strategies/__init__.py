"""
Strategy abstractions and pre-trade gates.
"""

from iatb.strategies.base import Strategy, StrategyBase, StrategyContext, StrategyOrder
from iatb.strategies.breakout import BreakoutInputs, BreakoutStrategy
from iatb.strategies.ensemble import EnsembleStrategy, WeightedSignal
from iatb.strategies.mean_reversion import MeanReversionInputs, MeanReversionStrategy
from iatb.strategies.momentum import MomentumInputs, MomentumStrategy
from iatb.strategies.sentiment_driven import SentimentDrivenInputs, SentimentDrivenStrategy

__all__ = [
    "Strategy",
    "StrategyBase",
    "StrategyContext",
    "StrategyOrder",
    "MomentumInputs",
    "MomentumStrategy",
    "MeanReversionInputs",
    "MeanReversionStrategy",
    "BreakoutInputs",
    "BreakoutStrategy",
    "SentimentDrivenInputs",
    "SentimentDrivenStrategy",
    "WeightedSignal",
    "EnsembleStrategy",
]
