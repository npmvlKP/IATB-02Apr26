#!/usr/bin/env python
"""
iATB Deployment Dashboard — Zero-dependency browser UI.

⚠️  DEPRECATED: This script is deprecated. Use `scripts/start_master.py` instead.
    The master startup script orchestrates engine and dashboard startup in the
    correct sequence, preventing the "Loading..." issue.

    To start all services:
      poetry run python scripts/start_master.py

Serves a live status page at http://localhost:8080 showing:
  - Engine & health status
  - Pre-flight check results
  - Kill switch state
  - Daily loss guard state
  - Recent trades from audit SQLite
  - Session PnL summary
  - Log tail (last 50 lines)

Run:  poetry run python scripts/dashboard.py
Open:  http://localhost:8080
"""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_PORT = 8080
_AUDIT_DB = Path("data/audit/trades.sqlite")
_LOG_DIR = Path("logs")
_REFRESH_SECONDS = 5


def _read_trades() -> list[dict[str, str]]:
    if not _AUDIT_DB.exists():
        return []
    try:
        conn = sqlite3.connect(_AUDIT_DB)
        conn.row_factory = sqlite3.Row
        today = datetime.now(UTC).date().isoformat()
        rows = conn.execute(
            "SELECT * FROM trade_audit WHERE timestamp_utc LIKE ? ORDER BY timestamp_utc DESC",
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
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as r:
            return r.read().decode()
    except Exception:
        return '{"status":"unreachable"}'


def _check_sentiment_health() -> dict[str, str]:
    """Check sentiment analysis health status."""
    components = {
        "finbert": "unavailable",
        "aion": "unavailable",
        "aggregator": "unavailable",
        "ensemble_status": "not operational",
    }

    # Check FinBERT
    try:
        from iatb.sentiment.finbert_analyzer import FinbertAnalyzer

        analyzer = FinbertAnalyzer()
        _ = analyzer  # Trigger import validation
        components["finbert"] = "available"
    except Exception as exc:
        components["finbert"] = f"error: {type(exc).__name__}"

    # Check AION
    try:
        from iatb.sentiment.aion_analyzer import AionAnalyzer

        analyzer = AionAnalyzer()
        _ = analyzer  # Trigger import validation
        components["aion"] = "available"
    except Exception as exc:
        components["aion"] = f"error: {type(exc).__name__}"

    # Check Aggregator (requires both components)
    if components["finbert"] == "available" and components["aion"] == "available":
        try:
            from iatb.sentiment.aggregator import SentimentAggregator

            aggregator = SentimentAggregator()
            _ = aggregator  # Trigger import validation
            components["aggregator"] = "available"
            components["ensemble_status"] = "operational"
        except Exception as exc:
            components["aggregator"] = f"error: {type(exc).__name__}"
            components["ensemble_status"] = f"error: {type(exc).__name__}"
    else:
        components["aggregator"] = "unavailable (dependencies missing)"
        components["ensemble_status"] = "unavailable (dependencies missing)"

    return components


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
    }


_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh}">
<title>iATB Deployment Dashboard</title>
<style>
  body {{ font-family: 'Segoe UI', Consolas, monospace; background: #0d1117; color: #c9d1d9; margin: 20px; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
  h2 {{ color: #8b949e; margin-top: 30px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 10px 0; }}
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
    health_ok = "ok" in health_raw and "unreachable" not in health_raw

    # If engine is down, show error state for all cards
    if not health_ok:
        return _HTML.format(
            refresh=_REFRESH_SECONDS,
            timestamp=str(status.get("timestamp_utc", ""))[:19],
            health_status="OFFLINE",
            health_class="fail",
            total_trades="N/A",
            net_pnl="N/A",
            buy_count="N/A",
            sell_count="N/A",
            trades_table="<p style='color:#f85149'>Engine unreachable. No trades available.</p>",
            log_tail="<p style='color:#f85149'>Engine unreachable. Logs unavailable.</p>",
            finbert_status="Unknown",
            finbert_class="status-err",
            aion_status="Unknown",
            aion_class="status-err",
            aggregator_status="Unknown",
            aggregator_class="status-err",
            ensemble_status_display="Engine Unreachable",
            ensemble_class="fail",
        )

    # Engine is up, render normally
    pnl = status.get("pnl_summary", {})
    trades = status.get("recent_trades", [])
    log_lines = status.get("log_tail", [])
    sentiment_health = status.get("sentiment_health", {})

    finbert_ok = sentiment_health.get("finbert", "") == "available"
    aion_ok = sentiment_health.get("aion", "") == "available"
    aggregator_ok = sentiment_health.get("aggregator", "") == "available"
    ensemble_ok = sentiment_health.get("ensemble_status", "") == "operational"

    return _HTML.format(
        refresh=_REFRESH_SECONDS,
        timestamp=str(status.get("timestamp_utc", ""))[:19],
        health_status="ONLINE",
        health_class="pass",
        total_trades=pnl.get("total_trades", "0") if isinstance(pnl, dict) else "0",
        net_pnl=pnl.get("net_notional_pnl", "0") if isinstance(pnl, dict) else "0",
        buy_count=pnl.get("buy_trades", "0") if isinstance(pnl, dict) else "0",
        sell_count=pnl.get("sell_trades", "0") if isinstance(pnl, dict) else "0",
        trades_table=_render_trades_table(trades if isinstance(trades, list) else []),
        log_tail="\n".join(log_lines if isinstance(log_lines, list) else []),
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
    def do_GET(self) -> None:
        if self.path == "/api/status":
            status = _build_status()
            body = json.dumps(status, default=str).encode()
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
    print("⚠️  DEPRECATION NOTICE")
    print("  This script is deprecated. Use `scripts/start_master.py` instead.")
    print("  The master startup script orchestrates engine and dashboard startup")
    print("  in the correct sequence, preventing the 'Loading...' issue.")
    print("")
    print("iATB Deployment Dashboard")
    print(f"  URL:  http://localhost:{_PORT}")
    print(f"  API:  http://localhost:{_PORT}/api/status")
    print(f"  Auto-refresh: {_REFRESH_SECONDS}s")
    print("  Press Ctrl+C to stop\n")
    server = ThreadingHTTPServer(("127.0.0.1", _PORT), _DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
