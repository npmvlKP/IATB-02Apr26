"""
Execution layer contracts and adapters.
"""

from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.ccxt_executor import CCXTExecutor
from iatb.execution.openalgo_executor import OpenAlgoExecutor
from iatb.execution.order_manager import OrderManager
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.transaction_costs import estimate_round_trip_cost, estimate_single_side_cost

__all__ = [
    "CCXTExecutor",
    "ExecutionResult",
    "Executor",
    "OpenAlgoExecutor",
    "OrderManager",
    "OrderRequest",
    "PaperExecutor",
    "estimate_round_trip_cost",
    "estimate_single_side_cost",
]
