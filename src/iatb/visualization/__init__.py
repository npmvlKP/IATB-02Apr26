"""
Visualization and operator dashboard utilities.
"""

from iatb.visualization.alerts import AlertType, TelegramAlertDispatcher
from iatb.visualization.breakout_scanner import (
    BreakoutCandidate,
    FactorHealth,
    HealthStatus,
    InstrumentHealthMatrix,
    ScannerHealthResult,
    build_instrument_health_matrix,
    build_scanner_health_result,
    compute_overall_health,
    evaluate_factor_health,
    health_status_to_badge,
    health_status_to_color,
    rank_breakout_candidates,
)
from iatb.visualization.charts import build_candlestick_chart
from iatb.visualization.dashboard import (
    ALL_TABS,
    INSTRUMENT_SCANNER_TAB,
    REQUIRED_MARKET_TABS,
    build_dashboard_payload,
    build_scanner_payload,
    convert_candidates_to_health_matrix,
    render_approved_charts,
    render_dashboard,
    render_health_matrix_table,
    render_instrument_scanner_tab,
)
from iatb.visualization.portfolio_view import build_portfolio_snapshot

__all__ = [
    "ALL_TABS",
    "AlertType",
    "BreakoutCandidate",
    "FactorHealth",
    "HealthStatus",
    "INSTRUMENT_SCANNER_TAB",
    "InstrumentHealthMatrix",
    "REQUIRED_MARKET_TABS",
    "ScannerHealthResult",
    "TelegramAlertDispatcher",
    "build_candlestick_chart",
    "build_dashboard_payload",
    "build_instrument_health_matrix",
    "build_portfolio_snapshot",
    "build_scanner_health_result",
    "build_scanner_payload",
    "compute_overall_health",
    "convert_candidates_to_health_matrix",
    "evaluate_factor_health",
    "health_status_to_badge",
    "health_status_to_color",
    "rank_breakout_candidates",
    "render_approved_charts",
    "render_dashboard",
    "render_health_matrix_table",
    "render_instrument_scanner_tab",
]
