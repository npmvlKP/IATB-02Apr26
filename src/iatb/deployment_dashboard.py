"""IATB Deployment Dashboard - FastAPI service on port 8080.

Provides /api/status JSON endpoint and HTML dashboard that proxies
engine health, broker info, and exchange status from the main API (port 8000).
"""

import importlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

logger = logging.getLogger("iatb.deployment_dashboard")

_ENGINE_BASE = "http://127.0.0.1:8000"

_SENTIMENT_MODULES: list[tuple[str, str]] = [
    ("iatb.sentiment.finbert_analyzer", "FinbertAnalyzer"),
    ("iatb.sentiment.aion_analyzer", "AionAnalyzer"),
    ("iatb.sentiment.vader_analyzer", "VaderAnalyzer"),
    ("iatb.sentiment.aggregator", "SentimentAggregator"),
]

_SENTIMENT_KEYS: list[str] = ["finbert", "aion", "vader", "aggregator"]

app = FastAPI(title="iATB Deployment Dashboard", version="1.0.0")

_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>iATB Deployment Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:Consolas,Monaco,monospace;padding:20px}
h1{color:#58a6ff;margin-bottom:4px}
.meta{color:#8b949e;font-size:12px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card h2{color:#58a6ff;font-size:13px;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px}
.row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot.g{background:#3fb950}.dot.r{background:#f85149}.dot.y{background:#d29922}
.lbl{color:#8b949e;font-size:13px}.val{color:#c9d1d9;font-size:13px;font-weight:bold}
.logbox{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:12px;font-size:12px;color:#3fb950;max-height:200px;overflow-y:auto}
.logline{margin-bottom:4px}
.ts{color:#8b949e;font-size:12px;margin-top:16px}
</style>
</head>
<body>
<h1>iATB Deployment Dashboard</h1>
<p class="meta">Port 8080 &middot; Auto-refresh 5s</p>
<div class="grid">
<div class="card"><h2>Engine Health</h2><div id="eng">Loading...</div></div>
<div class="card"><h2>Broker Status</h2><div id="brk">Loading...</div></div>
<div class="card"><h2>Exchange Status</h2><div id="exch">Loading...</div></div>
<div class="card"><h2>Sentiment Health</h2><div id="sent">Loading...</div></div>
<div class="card"><h2>PnL Summary</h2><div id="pnl">Loading...</div></div>
<div class="card"><h2>Log Tail</h2><div id="log" class="logbox">Loading...</div></div>
</div>
<p class="ts" id="ts"></p>
<script>
var _err='<div class="row"><span class="dot r"></span> <span class="val">Engine Unreachable</span></div>';
function dot(s){s=String(s).toLowerCase();if(s==="healthy"||s==="online"||s==="available"||s==="operational"||s.indexOf("open")===0)return'<span class="dot g"></span>';if(s==="offline"||s==="unreachable"||s==="unavailable")return'<span class="dot r"></span>';return'<span class="dot y"></span>'}
function go(){fetch("/api/status").then(function(r){return r.json()}).then(function(d){
var eh=d.engine_health||{};document.getElementById("eng").innerHTML='<div class="row">'+dot(eh.status)+' <span class="val">'+(eh.status||"unknown")+'</span></div><div class="lbl">Mode: '+(eh.mode||"N/A")+"</div>";
var bi=d.broker_info||{};if(bi.status==="unreachable"){document.getElementById("brk").innerHTML='<div class="row">'+dot("unreachable")+' <span class="val">Unreachable</span></div>'}else{document.getElementById("brk").innerHTML='<div class="row">'+dot("online")+' <span class="val">'+(bi.uid||"N/A")+"</span></div>"+'<div class="lbl">Name: '+(bi.name||"N/A")+"</div>"+'<div class="lbl">Balance: \\u20b9'+(bi.available_balance||"0")+"</div>"+'<div class="lbl">Margin Used: \\u20b9'+(bi.margin_used||"0")+"</div>"}
var ex=d.exchange_info||{};document.getElementById("exch").innerHTML=["nse","cds","mcx"].map(function(e){return'<div class="row">'+dot(ex[e])+' <span class="lbl">'+e.toUpperCase()+"</span> <span class=\"val\">"+(ex[e]||"N/A")+"</span></div>"}).join("");
var sh=d.sentiment_health||{};document.getElementById("sent").innerHTML=["finbert","aion","vader","aggregator"].map(function(s){return'<div class="row">'+dot(sh[s])+' <span class="lbl">'+s+"</span> <span class=\"val\">"+(sh[s]||"N/A")+"</span></div>"}).join("")+'<div class="row">'+dot(sh.ensemble_status)+' <span class="lbl">Ensemble</span> <span class="val">'+(sh.ensemble_status||"N/A")+"</span></div>";
var p=d.pnl_summary||{};document.getElementById("pnl").innerHTML='<div class="lbl">Net PnL: <span class="val">\\u20b9'+(p.net_notional_pnl||"0")+"</span></div>"+'<div class="lbl">Buy: '+(p.buy_trades||"0")+" | Sell: "+(p.sell_trades||"0")+" | Total: "+(p.total_trades||"0")+"</div>"+'<div class="lbl">Trades Today: <span class="val">'+(d.trades_today||0)+"</span></div>";
var lg=d.log_tail||[];document.getElementById("log").innerHTML=lg.map(function(l){return'<div class="logline">'+l+"</div>"}).join("");
document.getElementById("ts").textContent="Last updated: "+(d.timestamp_utc||"N/A");
}).catch(function(){document.getElementById("eng").innerHTML=_err;document.getElementById("brk").innerHTML=_err;document.getElementById("exch").innerHTML=_err;document.getElementById("sent").innerHTML=_err;document.getElementById("pnl").innerHTML=_err;document.getElementById("log").innerHTML='<div class="logline" style="color:#f85149">Engine Unreachable \u2014 retrying in 5s</div>';document.getElementById("ts").textContent="Connection failed"})}
go();setInterval(go,5000);
</script>
</body>
</html>"""


def _check_sentiment_module(module_path: str, class_name: str) -> str:
    """Check if a sentiment module and class are importable."""
    try:
        mod = importlib.import_module(module_path)
        getattr(mod, class_name)
        return "available"
    except Exception as exc:
        logger.debug("Sentiment module %s unavailable: %s", module_path, exc)
        return "unavailable"


def _build_sentiment_health() -> dict[str, str]:
    """Build sentiment health dict from import-based availability checks."""
    statuses = [_check_sentiment_module(m, c) for m, c in _SENTIMENT_MODULES]
    health: dict[str, str] = dict(zip(_SENTIMENT_KEYS, statuses, strict=True))
    all_available = all(s == "available" for s in statuses)
    health["ensemble_status"] = "operational" if all_available else "degraded"
    return health


async def _fetch_engine(path: str, timeout: float = 2.0) -> dict[str, Any]:
    """Fetch JSON from engine API, returning empty dict on failure."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_ENGINE_BASE}{path}", timeout=timeout)
            resp.raise_for_status()
            return cast(dict[str, Any], resp.json())
    except Exception:
        logger.warning("Engine fetch failed for %s", path)
        return {}


def _build_offline_status() -> dict[str, Any]:
    """Build fallback status when engine is unreachable."""
    sentiment = _build_sentiment_health()
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "engine_health": {"status": "offline"},
        "sentiment_health": sentiment,
        "broker_info": {"status": "unreachable"},
        "exchange_info": {"nse": "Closed", "cds": "Closed", "mcx": "Closed"},
        "trades_today": 0,
        "pnl_summary": {
            "net_notional_pnl": "0",
            "buy_trades": "0",
            "sell_trades": "0",
            "total_trades": "0",
        },
        "recent_trades": [],
        "log_tail": ["Engine offline \u2014 check start_all.ps1"],
    }


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    """Aggregate deployment status from engine API."""
    health = await _fetch_engine("/health", timeout=2.0)
    if not health:
        return _build_offline_status()

    broker = await _fetch_engine("/broker/status", timeout=2.0) or {"status": "unreachable"}
    exchanges = await _fetch_engine("/exchanges/status", timeout=2.0) or {
        "nse": "Closed",
        "cds": "Closed",
        "mcx": "Closed",
    }
    sentiment = await _fetch_engine("/sentiment/health", timeout=2.0)
    pnl = await _fetch_engine("/pnl/summary", timeout=2.0) or {
        "net_notional_pnl": "0",
        "buy_trades": "0",
        "sell_trades": "0",
        "total_trades": "0",
    }
    log_resp = await _fetch_engine("/logs/tail", timeout=2.0)
    log_tail = log_resp.get("lines", []) if log_resp else []

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "engine_health": health,
        "sentiment_health": sentiment if sentiment else _build_sentiment_health(),
        "broker_info": broker,
        "exchange_info": exchanges,
        "trades_today": pnl.get("total_trades", 0),
        "pnl_summary": pnl,
        "recent_trades": [],
        "log_tail": log_tail if log_tail else ["No log entries available"],
    }


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Render deployment dashboard HTML."""
    return _DASHBOARD_HTML
