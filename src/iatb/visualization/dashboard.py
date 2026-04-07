"""
Streamlit dashboard helpers for multi-market monitoring.
"""

import importlib
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from iatb.core.exceptions import ConfigError
from iatb.scanner.instrument_scanner import ScannerCandidate
from iatb.visualization.breakout_scanner import (
    InstrumentHealthMatrix,
    ScannerHealthResult,
    build_instrument_health_matrix,
    health_status_to_badge,
    health_status_to_color,
)

REQUIRED_MARKET_TABS = ("NSE EQ", "NSE F&O", "BSE", "MCX", "Currency F&O", "Crypto")
INSTRUMENT_SCANNER_TAB = "Instrument Scanner"
ALL_TABS = REQUIRED_MARKET_TABS + (INSTRUMENT_SCANNER_TAB,)


def build_dashboard_payload(
    market_payloads: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for tab in REQUIRED_MARKET_TABS:
        source = market_payloads.get(tab, {})
        payload[tab] = dict(source)
    return payload


def render_dashboard(
    payload: Mapping[str, Mapping[str, object]], streamlit_module: object | None = None
) -> list[str]:
    streamlit = streamlit_module or _load_streamlit()
    title = getattr(streamlit, "title", None)
    tabs_fn = getattr(streamlit, "tabs", None)
    if not callable(title) or not callable(tabs_fn):
        msg = "streamlit module missing title()/tabs() required for dashboard rendering"
        raise ConfigError(msg)
    title("IATB Multi-Market Dashboard")
    tabs = tabs_fn(list(ALL_TABS))
    rendered: list[str] = []
    for index, tab_name in enumerate(ALL_TABS):
        panel = tabs[index]
        write_fn = getattr(panel, "write", None)
        if callable(write_fn):
            write_fn(payload.get(tab_name, {}))
        rendered.append(tab_name)
    return rendered


def build_scanner_payload(
    scanner_result: ScannerHealthResult | None = None,
) -> dict[str, object]:
    """Build payload for Instrument Scanner tab."""
    if scanner_result is None:
        return {
            "instruments": [],
            "approved_count": 0,
            "total_scanned": 0,
            "scan_timestamp_utc": None,
        }
    return {
        "instruments": scanner_result.instruments,
        "approved_count": scanner_result.approved_count,
        "total_scanned": scanner_result.total_scanned,
        "scan_timestamp_utc": scanner_result.scan_timestamp_utc,
    }


def render_health_matrix_table(
    instruments: list[InstrumentHealthMatrix],
    streamlit_module: object | None = None,
) -> list[str]:
    """Render health matrix table with color-coded badges.

    Returns list of rendered symbols.
    """
    st = streamlit_module or _load_streamlit()
    rendered_symbols: list[str] = []

    if not instruments:
        info_fn = getattr(st, "info", None)
        if callable(info_fn):
            info_fn("No instruments to display.")
        return rendered_symbols

    data_fn = getattr(st, "dataframe", None)
    if callable(data_fn):
        rows = []
        for inst in instruments:
            sent_badge = health_status_to_badge(inst.sentiment_health.status)
            sent_val = inst.sentiment_health.status.value
            ms_badge = health_status_to_badge(inst.market_strength_health.status)
            ms_val = inst.market_strength_health.status.value
            vol_badge = health_status_to_badge(inst.volume_analysis_health.status)
            vol_val = inst.volume_analysis_health.status.value
            drl_badge = health_status_to_badge(inst.drl_backtest_health.status)
            drl_val = inst.drl_backtest_health.status.value
            overall_badge = health_status_to_badge(inst.overall_health)
            row = {
                "Symbol": inst.symbol,
                "Sentiment": f"{sent_badge} {sent_val}",
                "Market Strength": f"{ms_badge} {ms_val}",
                "Volume Analysis": f"{vol_badge} {vol_val}",
                "DRL/Backtest": f"{drl_badge} {drl_val}",
                "Safe Exit Prob": f"{float(inst.safe_exit_probability):.2%}",
                "Overall": f"{overall_badge} {inst.overall_health.value}",
            }
            rows.append(row)
        data_fn(rows, use_container_width=True, hide_index=True)
        rendered_symbols = [inst.symbol for inst in instruments]

    return rendered_symbols


def render_approved_charts(
    instruments: list[InstrumentHealthMatrix],
    chart_data: dict[str, list[dict[str, object]]] | None = None,
    streamlit_module: object | None = None,
    plotly_module: object | None = None,
) -> list[str]:
    """Render Plotly charts for approved instruments only.

    Args:
        instruments: List of instrument health matrices
        chart_data: Optional OHLCV data per symbol for charts
        streamlit_module: Streamlit module (mocked in tests)
        plotly_module: Plotly graph_objects module (mocked in tests)

    Returns list of symbols with rendered charts.
    """
    st = streamlit_module or _load_streamlit()
    go = plotly_module or _load_plotly_go()

    approved = [inst for inst in instruments if inst.is_approved]
    rendered_charts: list[str] = []

    if not approved:
        return rendered_charts

    subheader_fn = getattr(st, "subheader", None)
    plotly_chart_fn = getattr(st, "plotly_chart", None)

    for inst in approved:
        if callable(subheader_fn):
            badge = health_status_to_badge(inst.overall_health)
            subheader_fn(f"{badge} {inst.symbol}")

        if chart_data and inst.symbol in chart_data and callable(plotly_chart_fn):
            fig = _build_approval_chart(go, inst, chart_data[inst.symbol])
            if fig is not None:
                plotly_chart_fn(fig, use_container_width=True)
        elif callable(plotly_chart_fn):
            fig = _build_summary_chart(go, inst)
            if fig is not None:
                plotly_chart_fn(fig, use_container_width=True)

        rendered_charts.append(inst.symbol)

    return rendered_charts


def _build_approval_chart(
    go: Any,
    inst: InstrumentHealthMatrix,
    ohlcv_rows: list[dict[str, object]],
) -> object:
    """Build candlestick chart with health indicators for approved instrument."""
    if len(ohlcv_rows) < 2:
        return _build_summary_chart(go, inst)

    fig = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=[row.get("timestamp", idx) for idx, row in enumerate(ohlcv_rows)],
            open=[float(row.get("open", 0)) for row in ohlcv_rows],  # type: ignore[arg-type]
            high=[float(row.get("high", 0)) for row in ohlcv_rows],  # type: ignore[arg-type]
            low=[float(row.get("low", 0)) for row in ohlcv_rows],  # type: ignore[arg-type]
            close=[float(row.get("close", 0)) for row in ohlcv_rows],  # type: ignore[arg-type]
            name="OHLC",
        )
    )

    fig.update_layout(
        title=f"{inst.symbol} - Approved for Trading",
        yaxis_title="Price",
        xaxis_title="Time",
        showlegend=True,
        height=400,
    )

    return fig


def _build_summary_chart(go: Any, inst: InstrumentHealthMatrix) -> object:
    """Build summary bar chart showing factor scores for approved instrument."""
    fig = go.Figure()

    factors = ["Sentiment", "Market Strength", "Volume", "DRL/Backtest", "Exit Prob"]
    scores = [
        float(inst.sentiment_health.score),
        float(inst.market_strength_health.score),
        float(inst.volume_analysis_health.score),
        float(inst.drl_backtest_health.score),
        float(inst.safe_exit_probability),
    ]
    colors = [
        health_status_to_color(inst.sentiment_health.status),
        health_status_to_color(inst.market_strength_health.status),
        health_status_to_color(inst.volume_analysis_health.status),
        health_status_to_color(inst.drl_backtest_health.status),
        "green" if inst.safe_exit_probability >= Decimal("0.5") else "red",
    ]

    fig.add_trace(
        go.Bar(
            x=factors,
            y=scores,
            marker_color=colors,
            text=[f"{s:.2f}" for s in scores],
            textposition="auto",
            name="Factor Scores",
        )
    )

    fig.update_layout(
        title=f"{inst.symbol} - Factor Health Summary",
        yaxis_title="Score",
        yaxis_range=[0, 1],
        showlegend=False,
        height=300,
    )

    return fig


def _render_scanner_metrics(st: object, scanner_result: ScannerHealthResult) -> None:
    """Render scanner metrics (total, approved, approval rate)."""
    metric_fn = getattr(st, "metric", None)
    if not callable(metric_fn):
        return

    col1_fn = getattr(st, "columns", None)
    if not callable(col1_fn):
        return

    cols = col1_fn(3)
    if len(cols) < 3:
        return

    metric1 = getattr(cols[0], "metric", None)
    metric2 = getattr(cols[1], "metric", None)
    metric3 = getattr(cols[2], "metric", None)

    if callable(metric1):
        metric1("Total Scanned", scanner_result.total_scanned)
    if callable(metric2):
        metric2("Approved", scanner_result.approved_count)
    if callable(metric3):
        approval_rate = (
            scanner_result.approved_count / scanner_result.total_scanned * 100
            if scanner_result.total_scanned > 0
            else 0
        )
        metric3("Approval Rate", f"{approval_rate:.1f}%")


def _render_scanner_content(
    st: object,
    go: object,
    scanner_result: ScannerHealthResult,
    chart_data: dict[str, list[dict[str, object]]] | None,
) -> tuple[list[str], list[str]]:
    """Render scanner content (health matrix and charts).

    Returns tuple of (table_symbols, chart_symbols).
    """
    subheader_fn = getattr(st, "subheader", None)
    divider_fn = getattr(st, "divider", None)

    if callable(divider_fn):
        divider_fn()

    if callable(subheader_fn):
        subheader_fn("Health Matrix")

    table_symbols = render_health_matrix_table(scanner_result.instruments, st)

    if callable(divider_fn):
        divider_fn()

    if callable(subheader_fn):
        subheader_fn("Approved Instruments Charts")

    chart_symbols = render_approved_charts(scanner_result.instruments, chart_data, st, go)

    return table_symbols, chart_symbols


def render_instrument_scanner_tab(
    scanner_result: ScannerHealthResult | None = None,
    chart_data: dict[str, list[dict[str, object]]] | None = None,
    streamlit_module: object | None = None,
    plotly_module: object | None = None,
) -> dict[str, object]:
    """Render complete Instrument Scanner tab with health matrix and charts.

    Returns summary dict with rendered counts.
    """
    st = streamlit_module or _load_streamlit()
    go = plotly_module or _load_plotly_go()

    result: dict[str, object] = {
        "table_symbols": [],
        "chart_symbols": [],
        "approved_count": 0,
        "total_count": 0,
    }

    header_fn = getattr(st, "header", None)
    if callable(header_fn):
        header_fn("🔍 Instrument Scanner")

    if scanner_result is None:
        info_fn = getattr(st, "info", None)
        if callable(info_fn):
            info_fn("No scanner result available. Run scanner to see instruments.")
        return result

    result["total_count"] = len(scanner_result.instruments)
    result["approved_count"] = scanner_result.approved_count

    _render_scanner_metrics(st, scanner_result)
    table_symbols, chart_symbols = _render_scanner_content(st, go, scanner_result, chart_data)
    result["table_symbols"] = table_symbols
    result["chart_symbols"] = chart_symbols

    return result


def convert_candidates_to_health_matrix(
    candidates: list[ScannerCandidate],
    sentiment_threshold: Decimal = Decimal("0.6"),
    strength_threshold: Decimal = Decimal("0.6"),
    volume_threshold: Decimal = Decimal("0.6"),
    drl_threshold: Decimal = Decimal("0.6"),
) -> list[InstrumentHealthMatrix]:
    """Convert ScannerCandidate list to InstrumentHealthMatrix list.

    This integrates instrument_scanner results with health matrix visualization.
    """
    matrices: list[InstrumentHealthMatrix] = []

    for candidate in candidates:
        volume_score = min(Decimal("1"), candidate.volume_ratio / Decimal("5"))

        drl_score = candidate.exit_probability

        matrix = build_instrument_health_matrix(
            symbol=candidate.symbol,
            sentiment_score=abs(candidate.sentiment_score),
            market_strength_score=Decimal(candidate.metadata.get("strength_score", "0.5")),
            volume_score=volume_score,
            drl_backtest_score=drl_score,
            safe_exit_probability=candidate.exit_probability,
            timestamp_utc=candidate.timestamp_utc,
            sentiment_threshold=sentiment_threshold,
            strength_threshold=strength_threshold,
            volume_threshold=volume_threshold,
            drl_threshold=drl_threshold,
        )
        matrices.append(matrix)

    return matrices


def _load_streamlit() -> object:
    try:
        return importlib.import_module("streamlit")
    except ModuleNotFoundError as exc:
        msg = "streamlit dependency is required for dashboard rendering"
        raise ConfigError(msg) from exc


def _load_plotly_go() -> Any:
    try:
        return importlib.import_module("plotly.graph_objects")
    except ModuleNotFoundError as exc:
        msg = "plotly dependency is required for chart rendering"
        raise ConfigError(msg) from exc
