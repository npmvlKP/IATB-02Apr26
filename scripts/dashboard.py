#!/usr/bin/env python
"""
iATB Deployment Dashboard — Zero-dependency browser UI.

Serves a live status page at http://localhost:8080 showing:
  - Engine & health status
  - Pre-flight check results
  - Kill switch state
  - Daily loss guard state
  - Recent trades from audit SQLite
  - Session PnL summary
  - Log tail (last 50 lines)
  - Live Plotly charts from instrument scanner

Run:  poetry run python scripts/dashboard.py
Open:  http://localhost:8080
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_PORT = 8080
_AUDIT_DB = Path("data/audit/trades.sqlite")
_LOG_DIR = Path("logs")
_REFRESH_SECONDS = 5
_SCANNER_DATA: dict[str, Any] = {"gainers": [], "losers": [], "timestamp": ""}

# Global scanner instance for live updates
_scanner_instance = None


def _read_trades() -> list[dict[str, str]]:
    if not _AUDIT_DB.exists():
        return []
    try:
        conn = sqlite3.connect(_AUDIT_DB)
        conn.row_factory = sqlite3.Row
        today = datetime.now(UTC).date().isoformat()
        rows = conn.execute(
            "SELECT * FROM trade_audit WHERE timestamp_utc LIKE ? " "ORDER BY timestamp_utc DESC",
            (f"{today}%",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _read_log_tail(n: int = 50) -> list[str]:
    logs = sorted(_LOG_DIR.glob("deployment_*.log"), reverse=True)
    if not logs:
        return ["No deployment logs found."]
    try:
        lines = logs[0].read_text(encoding="utf-8").splitlines()
        return lines[-n:]
    except Exception as exc:
        return [f"Error reading log: {exc}"]


def _check_health() -> str:
    import urllib.request

    try:
        with urllib.request.urlopen(  # nosec: S310
            "http://127.0.0.1:8000/health", timeout=2
        ) as r:
            data = r.read()
            return data.decode() if isinstance(data, bytes) else str(data)
    except Exception:
        return '{"status":"unreachable"}'


def _check_sentiment_health() -> dict[str, str]:
    """Check sentiment analysis health status."""
    try:
        import iatb.sentiment.aggregator  # noqa: F401
        import iatb.sentiment.aion_analyzer  # noqa: F401
        import iatb.sentiment.finbert_analyzer  # noqa: F401

        return {
            "finbert": "available",
            "aion": "available",
            "aggregator": "available",
            "ensemble_status": "operational",
        }
    except Exception as exc:
        return {
            "finbert": "unavailable",
            "aion": "unavailable",
            "aggregator": "unavailable",
            "ensemble_status": f"error: {exc}",
        }


def _compute_pnl(trades: list[dict[str, str]]) -> dict[str, str]:
    total = Decimal("0")
    buy_count = 0
    sell_count = 0
    for t in trades:
        qty = Decimal(t.get("quantity", "0"))
        price = Decimal(t.get("price", "0"))
        side = t.get("side", "")
        if side == "BUY":
            total -= qty * price
            buy_count += 1
        elif side == "SELL":
            total += qty * price
            sell_count += 1
    return {
        "net_notional_pnl": str(total),
        "buy_trades": str(buy_count),
        "sell_trades": str(sell_count),
        "total_trades": str(len(trades)),
    }


def _update_scanner_data(gainers: list[Any], losers: list[Any]) -> None:
    """Update global scanner data for dashboard display."""
    global _SCANNER_DATA
    _SCANNER_DATA["gainers"] = gainers
    _SCANNER_DATA["losers"] = losers
    _SCANNER_DATA["timestamp"] = datetime.now(UTC).isoformat()


def _generate_plotly_chart(candidates: list[Any], title: str) -> dict[str, Any]:
    """Generate Plotly chart JSON for scanner candidates."""
    if not candidates:
        return {"data": [], "layout": {"title": {"text": title}}}

    symbols = [c.get("symbol", "N/A") for c in candidates]
    # Convert Decimal to float for Plotly compatibility
    pct_changes = [float(Decimal(str(c.get("pct_change", 0)))) for c in candidates]
    composite_scores = [float(Decimal(str(c.get("composite_score", 0)))) for c in candidates]
    volume_ratios = [float(Decimal(str(c.get("volume_ratio", 0)))) for c in candidates]

    data = [
        {
            "x": symbols,
            "y": pct_changes,
            "type": "bar",
            "name": "% Change",
            "marker": {"color": "#58a6ff"},
            "yaxis": "y",
        },
        {
            "x": symbols,
            "y": composite_scores,
            "type": "scatter",
            "mode": "lines+markers",
            "name": "Composite Score",
            "line": {"color": "#3fb950", "width": 3},
            "yaxis": "y2",
        },
        {
            "x": symbols,
            "y": volume_ratios,
            "type": "scatter",
            "mode": "markers",
            "name": "Volume Ratio",
            "marker": {"color": "#d29922", "size": 10},
            "yaxis": "y2",
        },
    ]

    layout = {
        "title": {"text": title, "font": {"color": "#c9d1d9"}},
        "plot_bgcolor": "#0d1117",
        "paper_bgcolor": "#161b22",
        "font": {"color": "#8b949e"},
        "xaxis": {
            "tickangle": -45,
            "tickfont": {"color": "#8b949e"},
            "gridcolor": "#30363d",
        },
        "yaxis": {
            "title": "% Change",
            "tickfont": {"color": "#58a6ff"},
            "gridcolor": "#30363d",
        },
        "yaxis2": {
            "title": "Score / Ratio",
            "overlaying": "y",
            "side": "right",
            "tickfont": {"color": "#3fb950"},
            "gridcolor": "#30363d",
        },
        "legend": {"font": {"color": "#8b949e"}},
        "margin": {"b": 150, "l": 60, "r": 60, "t": 60},
        "height": 400,
    }

    return {"data": data, "layout": layout}


def _build_status() -> dict[str, object]:
    trades = _read_trades()
    pnl = _compute_pnl(trades)
    health = _check_health()
    sentiment_health = _check_sentiment_health()
    log_tail = _read_log_tail(30)
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "engine_health": health,
        "sentiment_health": sentiment_health,
        "trades_today": len(trades),
        "pnl_summary": pnl,
        "recent_trades": trades[:20],
        "log_tail": log_tail,
        "scanner_data": _SCANNER_DATA,
    }


_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>iATB Deployment Dashboard</title>
<style>
  body {{ font-family: 'Segoe UI', Consolas, monospace; background: #0d1117;
          color: #c9d1d9; margin: 20px; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
  h2 {{ color: #8b949e; margin-top: 30px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 16px; margin: 10px 0; }}
  .pass {{ color: #3fb950; font-weight: bold; }}
  .fail {{ color: #f85149; font-weight: bold; }}
  .warn {{ color: #d29922; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #21262d; }}
  th {{ color: #8b949e; font-size: 0.85em; text-transform: uppercase; }}
  tr:hover {{ background: #1c2128; }}
  .metric {{ font-size: 1.8em; font-weight: bold; color: #58a6ff; }}
  .metric-label {{ font-size: 0.8em; color: #8b949e; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
  pre {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px;
         font-size: 0.8em; max-height: 400px; overflow-y: auto; white-space: pre-wrap; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; }}
  .badge-filled {{ background: #238636; color: white; }}
  .badge-rejected {{ background: #da3633; color: white; }}
  .status-ok {{ color: #3fb950; font-weight: bold; }}
  .status-err {{ color: #f85149; font-weight: bold; }}
</style>
</head><body>
<h1>iATB Deployment Dashboard</h1>
<p style="color:#8b949e">Last refresh: {timestamp} UTC &nbsp;|&nbsp; Auto-refresh: {refresh}s</p>

<div class="grid">
  <div class="card">
    <div class="metric-label">Engine Health</div>
    <div class="metric {health_class}">{health_status}</div>
  </div>
  <div class="card">
    <div class="metric-label">Trades Today</div>
    <div class="metric">{total_trades}</div>
  </div>
  <div class="card">
    <div class="metric-label">Net Notional PnL</div>
    <div class="metric">{net_pnl}</div>
  </div>
  <div class="card">
    <div class="metric-label">Buy / Sell</div>
    <div class="metric">{buy_count} / {sell_count}</div>
  </div>
</div>

<h2>Sentiment Analysis Health</h2>
<div class="grid-2">
  <div class="card">
    <table>
      <tr><th>Component</th><th>Status</th></tr>
      <tr>
        <td>FinBERT (ProsusAI)</td>
        <td class="{finbert_class}">{finbert_status}</td>
      </tr>
      <tr>
        <td>AION-IN-v3</td>
        <td class="{aion_class}">{aion_status}</td>
      </tr>
      <tr>
        <td>Ensemble Aggregator</td>
        <td class="{aggregator_class}">{aggregator_status}</td>
      </tr>
    </table>
  </div>
  <div class="card">
    <div class="metric-label">Ensemble Status</div>
    <div class="metric {ensemble_class}">{ensemble_status_display}</div>
    <p style="color:#8b949e; margin-top:10px; font-size:0.85em;">
      VERY_STRONG threshold: |score| ≥ 0.75<br>
      Volume confirmation: ratio ≥ 1.5
    </p>
  </div>
</div>

<h2>Recent Trades</h2>
<div class="card">
{trades_table}
</div>

<h2>Deployment Log (last 30 lines)</h2>
<pre>{log_tail}</pre>

</body></html>"""


def _render_trades_table(trades: list[dict[str, str]]) -> str:
    if not trades:
        return "<p style='color:#8b949e'>No trades today.</p>"
    rows = ""
    for t in trades:
        status = t.get("status", "")
        badge = "badge-filled" if status == "FILLED" else "badge-rejected"
        rows += (
            f"<tr>"
            f"<td>{t.get('order_id','')}</td>"
            f"<td>{t.get('timestamp_utc','')[:19]}</td>"
            f"<td><b>{t.get('side','')}</b></td>"
            f"<td>{t.get('symbol','')}</td>"
            f"<td>{t.get('quantity','')}</td>"
            f"<td>{t.get('price','')}</td>"
            f"<td><span class='badge {badge}'>{status}</span></td>"
            f"<td>{t.get('algo_id','')}</td>"
            f"</tr>"
        )
    return (
        "<table>"
        "<tr><th>Order ID</th><th>Time</th><th>Side</th><th>Symbol</th>"
        "<th>Qty</th><th>Price</th><th>Status</th><th>Algo ID</th></tr>"
        f"{rows}</table>"
    )


def _render_html(status: dict[str, object]) -> str:
    health_raw = str(status.get("engine_health", ""))
    health_ok = "ok" in health_raw
    pnl = status.get("pnl_summary", {})
    trades = status.get("recent_trades", [])
    log_lines = status.get("log_tail", [])
    sentiment_health = status.get("sentiment_health", {})

    finbert_ok = (
        isinstance(sentiment_health, dict) and sentiment_health.get("finbert", "") == "available"
    )
    aion_ok = isinstance(sentiment_health, dict) and sentiment_health.get("aion", "") == "available"
    aggregator_ok = (
        isinstance(sentiment_health, dict) and sentiment_health.get("aggregator", "") == "available"
    )
    ensemble_ok = (
        isinstance(sentiment_health, dict)
        and sentiment_health.get("ensemble_status", "") == "operational"
    )

    total_trades_val = pnl.get("total_trades", "0") if isinstance(pnl, dict) else "0"
    net_pnl_val = pnl.get("net_notional_pnl", "0") if isinstance(pnl, dict) else "0"
    buy_count_val = pnl.get("buy_trades", "0") if isinstance(pnl, dict) else "0"
    sell_count_val = pnl.get("sell_trades", "0") if isinstance(pnl, dict) else "0"
    trades_table_val = _render_trades_table(trades if isinstance(trades, list) else [])
    log_tail_val = "\n".join(log_lines if isinstance(log_lines, list) else [])

    return _HTML.format(
        refresh=_REFRESH_SECONDS,
        timestamp=str(status.get("timestamp_utc", ""))[:19],
        health_status="ONLINE" if health_ok else "OFFLINE",
        health_class="pass" if health_ok else "fail",
        total_trades=total_trades_val,
        net_pnl=net_pnl_val,
        buy_count=buy_count_val,
        sell_count=sell_count_val,
        trades_table=trades_table_val,
        log_tail=log_tail_val,
        finbert_status="Available" if finbert_ok else "Unavailable",
        finbert_class="status-ok" if finbert_ok else "status-err",
        aion_status="Available" if aion_ok else "Unavailable",
        aion_class="status-ok" if aion_ok else "status-err",
        aggregator_status="Available" if aggregator_ok else "Unavailable",
        aggregator_class="status-ok" if aggregator_ok else "status-err",
        ensemble_status_display="Operational" if ensemble_ok else "Error",
        ensemble_class="pass" if ensemble_ok else "fail",
    )


class _DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            status = _build_status()
            body = json.dumps(status, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/charts/gainers":
            gainers = _SCANNER_DATA.get("gainers", [])
            chart = _generate_plotly_chart(gainers, "Top Gainers - Live Scanner")
            body = json.dumps(chart, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/charts/losers":
            losers = _SCANNER_DATA.get("losers", [])
            chart = _generate_plotly_chart(losers, "Top Losers - Live Scanner")
            body = json.dumps(chart, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/" or self.path == "/dashboard":
            status = _build_status()
            html = _render_html(status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress console noise


def main() -> None:
    print("iATB Deployment Dashboard")  # noqa: T201
    print(f"  URL:  http://localhost:{_PORT}")  # noqa: T201
    print(f"  API:  http://localhost:{_PORT}/api/status")  # noqa: T201
    print(f"  Auto-refresh: {_REFRESH_SECONDS}s")  # noqa: T201
    print("  Press Ctrl+C to stop\n")  # noqa: T201
    server = ThreadingHTTPServer(("127.0.0.1", _PORT), _DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")  # noqa: T201
        server.shutdown()


if __name__ == "__main__":
    main()
