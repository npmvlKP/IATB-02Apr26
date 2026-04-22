"""
Execution layer contracts and adapters.
"""

from iatb.execution.base import ExecutionResult, Executor, OrderRequest
from iatb.execution.ccxt_executor import CCXTExecutor
from iatb.execution.live_gate import (
    LiveGateConfig,
    LiveTradingSafetyGate,
    assert_live_trading_allowed,
    require_live_trading_enabled,
)
from iatb.execution.openalgo_executor import OpenAlgoExecutor
from iatb.execution.order_manager import OrderManager
from iatb.execution.paper_executor import PaperExecutor
from iatb.execution.token_helpers import apply_env_defaults, load_env_file
from iatb.execution.transaction_costs import estimate_round_trip_cost, estimate_single_side_cost
from iatb.execution.zerodha_connection import ZerodhaConnection, ZerodhaSession

__all__ = [
    "CCXTExecutor",
    "ExecutionResult",
    "Executor",
    "LiveGateConfig",
    "LiveTradingSafetyGate",
    "OpenAlgoExecutor",
    "OrderManager",
    "OrderRequest",
    "PaperExecutor",
    "apply_env_defaults",
    "assert_live_trading_allowed",
    "estimate_round_trip_cost",
    "estimate_single_side_cost",
    "load_env_file",
    "require_live_trading_enabled",
    "ZerodhaConnection",
    "ZerodhaSession",
]
