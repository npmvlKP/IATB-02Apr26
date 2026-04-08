"""
Backtesting and forward-testing utilities.
"""

from iatb.backtesting.event_driven import EventDrivenBacktester, EventDrivenResult
from iatb.backtesting.forward_test import ForwardTestConfig, ForwardTester, ForwardTestResult
from iatb.backtesting.indian_costs import CostBreakdown, calculate_indian_costs
from iatb.backtesting.monte_carlo import MonteCarloAnalyzer, MonteCarloResult
from iatb.backtesting.report import QuantStatsReporter
from iatb.backtesting.session_masks import filter_timestamps_in_session, is_in_session
from iatb.backtesting.vectorbt_engine import (
    BacktestResult,
    MonteCarloResult as VectorBTMonteCarloResult,
    VectorBTConfig,
    VectorBTEngine,
    WalkForwardResult as VectorBTWalkForwardResult,
)
from iatb.backtesting.vectorized import VectorizedBacktester, VectorizedSweepResult
from iatb.backtesting.walk_forward import WalkForwardOptimizer, WalkForwardResult

__all__ = [
    "BacktestResult",
    "CostBreakdown",
    "EventDrivenBacktester",
    "EventDrivenResult",
    "ForwardTestConfig",
    "ForwardTestResult",
    "ForwardTester",
    "MonteCarloAnalyzer",
    "MonteCarloResult",
    "QuantStatsReporter",
    "VectorBTConfig",
    "VectorBTEngine",
    "VectorBTMonteCarloResult",
    "VectorBTWalkForwardResult",
    "VectorizedBacktester",
    "VectorizedSweepResult",
    "WalkForwardOptimizer",
    "WalkForwardResult",
    "calculate_indian_costs",
    "filter_timestamps_in_session",
    "is_in_session",
]
