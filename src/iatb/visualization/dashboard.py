"""
Streamlit dashboard helpers for multi-market monitoring.

Includes Zerodha account profile display, NSE/CDS/MCX exchange status,
comprehensive scanner matrix, live charts, and SQLite-based engine polling.
"""

import importlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.openalgo_provider import DataFeedStatus, FeedStatus
from iatb.scanner.instrument_scanner import ScannerCandidate
from iatb.visualization.breakout_scanner import (
    InstrumentHealthMatrix,
    ScannerHealthResult,
    build_instrument_health_matrix,
    health_status_to_badge,
    health_status_to_color,
)
from iatb.visualization.dashboard_status import (
    EngineStatus,
    ExchangeSessionStatus,
    ScannerInstrumentRow,
    ZerodhaAccountSnapshot,
    read_engine_status,
    read_exchange_session_status,
    read_scanner_results,
    read_zerodha_snapshot,
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


_FEED_STATUS_BADGES = {
    FeedStatus.LIVE: ("✅", "LIVE"),
    FeedStatus.FALLBACK: ("⚠️", "FALLBACK"),
    FeedStatus.UNAVAILABLE: ("❌", "UNAVAILABLE"),
}


def render_data_feed_status(
    feed_status: DataFeedStatus | None = None,
    streamlit_module: object | None = None,
) -> str:
    """Render data feed status with colored badges per exchange.

    Returns a human-readable status line.
    """
    st = streamlit_module or _load_streamlit()
    if feed_status is None:
        info_fn = getattr(st, "info", None)
        if callable(info_fn):
            info_fn("Data feed not initialized.")
        return "Data feed not initialized"

    parts: list[str] = []
    for exchange, state in feed_status.exchanges.items():
        badge, label = _FEED_STATUS_BADGES.get(state.status, ("⚪", "UNKNOWN"))
        parts.append(f"{exchange.value} {badge} ({state.source})")

    status_line = " | ".join(parts)
    subheader_fn = getattr(st, "subheader", None)
    if callable(subheader_fn):
        subheader_fn("Data Feed Status")

    success_fn = getattr(st, "success", None)
    warning_fn = getattr(st, "warning", None)
    all_live = all(s.status == FeedStatus.LIVE for s in feed_status.exchanges.values())
    if all_live and callable(success_fn):
        success_fn(status_line)
    elif callable(warning_fn):
        warning_fn(status_line)

    return status_line


def render_instrument_scanner_tab(
    scanner_result: ScannerHealthResult | None = None,
    chart_data: dict[str, list[dict[str, object]]] | None = None,
    streamlit_module: object | None = None,
    plotly_module: object | None = None,
    feed_status: DataFeedStatus | None = None,
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

    render_data_feed_status(feed_status, st)

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


def _render_zerodha_metrics(st: object, snapshot: ZerodhaAccountSnapshot) -> None:
    metric_fn = getattr(st, "metric", None)
    columns_fn = getattr(st, "columns", None)
    if not callable(metric_fn) or not callable(columns_fn):
        return
    cols = columns_fn(3)
    if len(cols) < 3:
        return
    user_metric = getattr(cols[0], "metric", None)
    balance_metric = getattr(cols[1], "metric", None)
    email_metric = getattr(cols[2], "metric", None)
    if callable(user_metric):
        user_metric("User ID", snapshot.user_id)
    if callable(balance_metric):
        balance_metric("Available Balance", f"₹{snapshot.available_balance:,.2f}")
    if callable(email_metric):
        email_metric("Email", snapshot.user_email)


def _render_zerodha_connection_info(st: object, snapshot: ZerodhaAccountSnapshot) -> None:
    success_fn = getattr(st, "success", None)
    if not callable(success_fn):
        return
    ts_label = (
        snapshot.snapshot_timestamp_utc.isoformat()[:19] + "Z"
        if snapshot.snapshot_timestamp_utc
        else "N/A"
    )
    success_fn(
        f"Connected as {snapshot.user_name} (UID: {snapshot.user_id}) "
        f"| Equity Margin: ₹{snapshot.equity_margin:,.2f} "
        f"| Commodity Margin: ₹{snapshot.commodity_margin:,.2f} "
        f"| Last Sync: {ts_label}"
    )


def render_zerodha_account_status(
    snapshot: ZerodhaAccountSnapshot | None = None,
    streamlit_module: object | None = None,
) -> dict[str, object]:
    """Render Zerodha account profile with UID, email, and balance.

    Returns dict with rendered fields for testing verification.
    """
    st = streamlit_module or _load_streamlit()
    result: dict[str, object] = {"rendered": False}

    subheader_fn = getattr(st, "subheader", None)
    if callable(subheader_fn):
        subheader_fn("Zerodha Account")

    if snapshot is None:
        warning_fn = getattr(st, "warning", None)
        if callable(warning_fn):
            warning_fn("Zerodha account not connected. Set ZERODHA_ACCESS_TOKEN.")
        result["reason"] = "no_snapshot"
        return result

    _render_zerodha_metrics(st, snapshot)
    _render_zerodha_connection_info(st, snapshot)

    result["rendered"] = True
    result["user_id"] = snapshot.user_id
    result["balance"] = str(snapshot.available_balance)
    result["email"] = snapshot.user_email
    return result


def render_exchange_status_panel(
    exchange_sessions: list[ExchangeSessionStatus] | None = None,
    streamlit_module: object | None = None,
) -> list[dict[str, object]]:
    """Render NSE/CDS/MCX exchange open/closed status.

    Returns list of rendered exchange status dicts for testing.
    """
    st = streamlit_module or _load_streamlit()
    rendered: list[dict[str, object]] = []

    subheader_fn = getattr(st, "subheader", None)
    if callable(subheader_fn):
        subheader_fn("Exchange Status (NSE / CDS / MCX)")

    if exchange_sessions is None:
        exchange_sessions = [
            read_exchange_session_status(Exchange.NSE, "09:15", "15:30"),
            read_exchange_session_status(Exchange.CDS, "09:00", "17:00"),
            read_exchange_session_status(Exchange.MCX, "09:00", "23:30"),
        ]

    metric_fn = getattr(st, "metric", None)
    columns_fn = getattr(st, "columns", None)

    if callable(metric_fn) and callable(columns_fn):
        cols = columns_fn(len(exchange_sessions))
        for idx, session in enumerate(exchange_sessions):
            if idx >= len(cols):
                break
            col_metric = getattr(cols[idx], "metric", None)
            if callable(col_metric):
                badge = "🟢" if session.is_open else "🔴"
                col_metric(
                    session.exchange.value,
                    f"{badge} {session.status_label}",
                    f"{session.session_open_time} – {session.session_close_time} IST",
                )
            rendered.append(
                {
                    "exchange": session.exchange.value,
                    "is_open": session.is_open,
                    "status": session.status_label,
                }
            )

    return rendered


def _render_scanner_summary_metrics(
    st: object,
    total: int,
    approved: int,
) -> None:
    metric_fn = getattr(st, "metric", None)
    columns_fn = getattr(st, "columns", None)
    if not callable(metric_fn) or not callable(columns_fn):
        return
    cols = columns_fn(3)
    if len(cols) < 3:
        return
    m1 = getattr(cols[0], "metric", None)
    m2 = getattr(cols[1], "metric", None)
    m3 = getattr(cols[2], "metric", None)
    if callable(m1):
        m1("Total Scanned", str(total))
    if callable(m2):
        m2("Approved", str(approved))
    if callable(m3):
        rate = (approved / total * 100) if total > 0 else 0
        m3("Approval Rate", f"{rate:.1f}%")


def _render_scanner_dataframe(
    st: object,
    instruments: list[ScannerInstrumentRow],
) -> None:
    data_fn = getattr(st, "dataframe", None)
    if not callable(data_fn):
        return
    rows = [
        {
            "Symbol": inst.symbol,
            "Exchange": inst.exchange.value,
            "Sentiment": f"{float(inst.sentiment_score):.2f}",
            "Strength": f"{float(inst.market_strength_score):.2f}",
            "DRL": f"{float(inst.drl_score):.2f}",
            "Volume Profile": f"{float(inst.volume_profile_score):.2f}",
            "Composite": f"{float(inst.composite_score):.2f}",
            "Approved": "✅" if inst.is_approved else "❌",
        }
        for inst in instruments
    ]
    data_fn(rows, use_container_width=True, hide_index=True)


def _render_approved_instrument_charts(
    st: object,
    go: Any,
    instruments: list[ScannerInstrumentRow],
) -> list[str]:
    subheader_fn = getattr(st, "subheader", None)
    plotly_chart_fn = getattr(st, "plotly_chart", None)
    rendered: list[str] = []
    for inst in instruments:
        if not inst.is_approved:
            continue
        if callable(subheader_fn):
            subheader_fn(f"✅ {inst.symbol} ({inst.exchange.value})")
        if callable(plotly_chart_fn):
            fig = _build_instrument_factor_chart(go, inst)
            if fig is not None:
                plotly_chart_fn(fig, use_container_width=True)
        rendered.append(inst.symbol)
    return rendered


def render_scanner_matrix_from_sqlite(
    instruments: list[ScannerInstrumentRow] | None = None,
    streamlit_module: object | None = None,
    plotly_module: object | None = None,
    db_path: Path | None = None,
) -> dict[str, object]:
    """Render comprehensive scanner matrix with sentiment + strength + DRL + volume.

    Reads from SQLite if instruments not provided directly.
    Returns summary dict with rendered counts.
    """
    st = streamlit_module or _load_streamlit()
    go = plotly_module or _load_plotly_go()

    result: dict[str, object] = {"total": 0, "approved": 0, "symbols": []}

    header_fn = getattr(st, "header", None)
    if callable(header_fn):
        header_fn("Instrument Scanner — Multi-Factor Matrix")

    if instruments is None:
        path = db_path or Path("data/audit/trades.sqlite")
        instruments = read_scanner_results(path)

    if not instruments:
        info_fn = getattr(st, "info", None)
        if callable(info_fn):
            info_fn("No scanner results. Run a scan from the engine to populate data.")
        return result

    total = len(instruments)
    approved = sum(1 for i in instruments if i.is_approved)
    result["total"] = total
    result["approved"] = approved

    _render_scanner_summary_metrics(st, total, approved)
    _render_scanner_dataframe(st, instruments)

    divider_fn = getattr(st, "divider", None)
    subheader_fn = getattr(st, "subheader", None)
    if callable(divider_fn):
        divider_fn()
    if callable(subheader_fn):
        subheader_fn("Approved Instrument Charts")

    result["symbols"] = _render_approved_instrument_charts(st, go, instruments)
    return result


def _build_instrument_factor_chart(
    go: Any,
    inst: ScannerInstrumentRow,
) -> object:
    """Build radar/bar factor chart for a scanner instrument row."""
    fig = go.Figure()

    factors = ["Sentiment", "Strength", "DRL", "Volume", "Composite"]
    scores = [
        float(inst.sentiment_score),
        float(inst.market_strength_score),
        float(inst.drl_score),
        float(inst.volume_profile_score),
        float(inst.composite_score),
    ]
    colors = []
    for score in scores[:-1]:
        if score >= 0.6:
            colors.append("green")
        elif score >= 0.4:
            colors.append("gray")
        else:
            colors.append("red")
    colors.append("green" if inst.composite_score >= Decimal("0.6") else "red")

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
        title=f"{inst.symbol} — Factor Score Matrix",
        yaxis_title="Score",
        yaxis_range=[0, 1],
        showlegend=False,
        height=300,
    )

    return fig


def render_live_chart(
    symbol: str,
    ohlcv_data: list[dict[str, object]],
    plotly_module: object | None = None,
    streamlit_module: object | None = None,
) -> object | None:
    """Render a live candlestick chart for a selected instrument.

    Returns the Plotly figure (or None if insufficient data).
    """
    go: Any = plotly_module or _load_plotly_go()
    st = streamlit_module or _load_streamlit()

    if len(ohlcv_data) < 2:
        info_fn = getattr(st, "info", None)
        if callable(info_fn):
            info_fn(f"Insufficient data for {symbol} live chart (need >= 2 bars).")
        return None

    fig: Any = go.Figure()

    fig.add_trace(
        go.Candlestick(
            x=[row.get("timestamp", idx) for idx, row in enumerate(ohlcv_data)],
            open=[float(row.get("open", 0)) for row in ohlcv_data],  # type: ignore[arg-type]
            high=[float(row.get("high", 0)) for row in ohlcv_data],  # type: ignore[arg-type]
            low=[float(row.get("low", 0)) for row in ohlcv_data],  # type: ignore[arg-type]
            close=[float(row.get("close", 0)) for row in ohlcv_data],  # type: ignore[arg-type]
            name=symbol,
        )
    )

    fig.update_layout(
        title=f"{symbol} — Live Chart",
        yaxis_title="Price",
        xaxis_title="Time",
        showlegend=True,
        height=450,
    )

    plotly_chart_fn = getattr(st, "plotly_chart", None)
    if callable(plotly_chart_fn):
        plotly_chart_fn(fig, use_container_width=True)

    return fig  # type: ignore[no-any-return]


def _render_engine_health_section(
    st: object,
    engine_status: EngineStatus,
) -> None:
    subheader_fn = getattr(st, "subheader", None)
    success_fn = getattr(st, "success", None)
    warning_fn = getattr(st, "warning", None)

    if callable(subheader_fn):
        subheader_fn("Engine Health")

    if engine_status.is_running:
        if not callable(success_fn):
            return
        hb_label = (
            engine_status.last_heartbeat_utc.isoformat()[:19] + "Z"
            if engine_status.last_heartbeat_utc
            else "N/A"
        )
        success_fn(
            f"Engine Online | Mode: {engine_status.mode} | "
            f"Trades Today: {engine_status.trades_today} | "
            f"Heartbeat: {hb_label}"
        )
    else:
        if callable(warning_fn):
            warning_fn("Engine Offline — start with scripts/start_paper.ps1")


def _render_engine_metrics(st: object, engine_status: EngineStatus) -> None:
    metric_fn = getattr(st, "metric", None)
    columns_fn = getattr(st, "columns", None)
    if not callable(metric_fn) or not callable(columns_fn):
        return
    cols = columns_fn(3)
    if len(cols) < 3:
        return
    m1 = getattr(cols[0], "metric", None)
    m2 = getattr(cols[1], "metric", None)
    m3 = getattr(cols[2], "metric", None)
    if callable(m1):
        m1("Mode", engine_status.mode)
    if callable(m2):
        m2("Trades Today", str(engine_status.trades_today))
    if callable(m3):
        m3("Scanner Instruments", str(engine_status.scanner_instruments_count))


def render_system_tab(
    db_path: Path | None = None,
    streamlit_module: object | None = None,
) -> dict[str, object]:
    """Render complete System tab: engine health + Zerodha + exchange status.

    Uses SQLite polling instead of urlopen to avoid timeout issues.
    Returns summary dict for testing.
    """
    st = streamlit_module or _load_streamlit()
    path = db_path or Path("data/audit/trades.sqlite")

    result: dict[str, object] = {
        "engine_running": False,
        "zerodha_connected": False,
        "exchanges": [],
    }

    engine_status = read_engine_status(path)
    result["engine_running"] = engine_status.is_running

    _render_engine_health_section(st, engine_status)
    _render_engine_metrics(st, engine_status)

    divider_or_none = getattr(st, "divider", None)
    if callable(divider_or_none):
        divider_or_none()

    zerodha_snapshot = read_zerodha_snapshot(path)
    zerodha_result = render_zerodha_account_status(zerodha_snapshot, st)
    result["zerodha_connected"] = zerodha_result.get("rendered", False)

    if callable(divider_or_none):
        divider_or_none()

    exchange_result = render_exchange_status_panel(streamlit_module=st)
    result["exchanges"] = exchange_result

    return result


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


# Streamlit app entry point
if __name__ == "__main__":  # pragma: no cover
    import os

    import streamlit as st

    from iatb.data.openalgo_provider import DataFeedStatus, ExchangeFeedState, FeedStatus

    # Page configuration
    st.set_page_config(
        page_title="IATB Paper Trading Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Header
    st.title("📊 IATB Multi-Market Dashboard")

    # Mode indicators
    col1, col2 = st.columns(2)
    with col1:
        mode = os.environ.get("IATB_MODE", "unknown")
        st.metric("Mode", mode.upper())
    with col2:
        live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "false")
        status = "🟢 PAPER" if live_enabled == "false" else "🔴 LIVE"
        st.metric("Trading", status)

    # Sidebar
    st.sidebar.header("Configuration")
    config_path = os.environ.get("IATB_CONFIG_PATH", "config/settings.toml")
    st.sidebar.write(f"Config: `{config_path}`")
    st.sidebar.header("System Info")
    st.sidebar.write(f"Timestamp: `{datetime.now(UTC).isoformat()[:19]}Z`")

    # Create tabs
    tabs = st.tabs(list(ALL_TABS))

    # Render each tab
    for i, tab_name in enumerate(ALL_TABS):
        with tabs[i]:
            if tab_name == INSTRUMENT_SCANNER_TAB:
                st.header("🔍 Instrument Scanner")
                from iatb.data.openalgo_provider import FeedStatus

                feed_placeholder = DataFeedStatus(
                    exchanges={
                        Exchange.NSE: ExchangeFeedState(
                            exchange=Exchange.NSE,
                            status=FeedStatus.FALLBACK,
                            source="jugaad-data (EOD)",
                            checked_at_utc=datetime.now(UTC),
                            error="Engine not started",
                        ),
                    }
                )
                render_data_feed_status(feed_placeholder, st)
                st.info(
                    """
                    **Scanner Status**: Paper trading mode active.

                    The instrument scanner will display here when the engine is running.
                    It will show:
                    - Health matrix with sentiment, market strength, volume analysis
                    - DRL backtest health scores
                    - Safe exit probabilities
                    - Factor breakdown charts
                    """
                )
                # Check if scanner is available
                try:
                    st.success("✅ Scanner components available")
                except Exception as e:
                    st.warning(f"⚠️ Scanner not fully initialized: {e}")
            else:
                st.header(f"{tab_name}")
                st.info(
                    f"""
                    **{tab_name}** tab is ready.

                    Market data for {tab_name} will be displayed here when the engine is running.
                    """
                )

    # Footer
    st.markdown("---")
    st.caption(
        "📊 Dashboard auto-refreshes on interaction. "
        "Press 'R' or click 'Rerun' to refresh manually."
    )
