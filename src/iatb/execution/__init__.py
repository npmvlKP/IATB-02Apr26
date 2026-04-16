"""
Execution layer contracts and adapters.
"""

import warnings

from iatb.broker.token_manager import ZerodhaTokenManager as CanonicalZerodhaTokenManager
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
from iatb.execution.transaction_costs import estimate_round_trip_cost, estimate_single_side_cost
from iatb.execution.zerodha_connection import ZerodhaConnection, ZerodhaSession
from iatb.execution.zerodha_token_manager import ZerodhaTokenManager

# Emit deprecation warning when importing from execution module
warnings.warn(
    "Direct import of ZerodhaTokenManager from iatb.execution is deprecated. "
    "Import from iatb.broker.token_manager instead. "
    "This module will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export with deprecation notice
_ZerodhaTokenManager = ZerodhaTokenManager

# For backward compatibility, alias to canonical implementation
ZerodhaTokenManager = CanonicalZerodhaTokenManager  # type: ignore[misc, assignment]

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
    "assert_live_trading_allowed",
    "estimate_round_trip_cost",
    "estimate_single_side_cost",
    "require_live_trading_enabled",
    "ZerodhaConnection",
    "ZerodhaSession",
    "ZerodhaTokenManager",
]
