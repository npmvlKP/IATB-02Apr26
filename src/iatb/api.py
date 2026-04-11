"""IATB Engine REST API - FastAPI backend for dashboard and external consumers."""

import asyncio
import glob
import importlib
import logging
import sqlite3
import tomllib
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import keyring
import pytz
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("iatb.api")

IST = pytz.timezone("Asia/Kolkata")

_HOLIDAYS_PATH = Path("config/nse_holidays.toml")

app = FastAPI(title="IATB Engine API", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_kite: Any = None


class BrokerStatus(BaseModel):
    uid: str
    name: str
    email: str
    available_balance: Decimal
    margin_used: Decimal


class ExchangeStatus(BaseModel):
    nse: str
    cds: str
    mcx: str


class ScannerResponse(BaseModel):
    status: str
    regime: str
    scorer_available: bool


def _init_kite() -> Any:
    """Initialize KiteConnect with securely stored credentials."""
    global _kite
    if _kite is not None:
        return _kite
    from iatb.broker.token_manager import ZerodhaTokenManager

    token_manager = ZerodhaTokenManager()
    if not token_manager.is_token_fresh():
        raise HTTPException(
            status_code=401,
            detail="relogin_required",
        )
    api_key = keyring.get_password("iatb", "zerodha_api_key")
    access_token = keyring.get_password("iatb", "zerodha_access_token")
    if not api_key or not access_token:
        raise HTTPException(status_code=401, detail="Run zerodha_login.ps1 first")
    try:
        from kiteconnect import KiteConnect

        _kite = KiteConnect(api_key=api_key)
        _kite.set_access_token(access_token)
    except Exception as exc:
        logger.error("KiteConnect init failed: %s", exc)
        raise HTTPException(status_code=503, detail="Kite SDK unavailable") from exc
    return _kite


def _is_holiday(exchange: str) -> bool:
    """Check if today is a trading holiday for the given exchange."""
    if not _HOLIDAYS_PATH.exists():
        return False
    try:
        with open(_HOLIDAYS_PATH, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        logger.warning("Failed to read holidays: %s", exc)
        return False
    today = datetime.now(IST).date().isoformat()
    year_key = str(datetime.now(IST).year)
    year_data = data.get(year_key, {})
    section_key = "nse_cds" if exchange in ("NSE", "CDS") else "mcx"
    entries = year_data.get(section_key, [])
    return any(entry.get("date") == today for entry in entries)


def _exchange_status(exchange: str, open_time: time, close_time: time) -> str:
    """Determine if an exchange is currently in trading session."""
    if _is_holiday(exchange):
        return "Closed-Holiday"
    now = datetime.now(IST).time()
    if open_time <= now <= close_time:
        return "Open-Trading"
    return "Closed"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5))
def _fetch_kite_profile(k: Any) -> Any:
    """Fetch Zerodha user profile with retry."""
    return k.profile()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5))
def _fetch_kite_margins(k: Any) -> Any:
    """Fetch Zerodha margin data with retry."""
    return k.margins()


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "healthy", "mode": "paper", "timestamp": datetime.now(UTC).isoformat()}


@app.get("/broker/status", response_model=BrokerStatus)
async def broker_status() -> BrokerStatus:
    """Fetch Zerodha broker profile and margin status."""
    try:
        k = _init_kite()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Kite init failed: %s", exc)
        raise HTTPException(status_code=503, detail="Kite unreachable") from exc
    loop = asyncio.get_running_loop()
    try:
        profile = await loop.run_in_executor(None, _fetch_kite_profile, k)
        margins = await loop.run_in_executor(None, _fetch_kite_margins, k)
    except Exception as exc:
        logger.error("Kite API call failed: %s", exc)
        raise HTTPException(status_code=503, detail="Kite unreachable") from exc
    equity = margins.get("equity", {})
    return BrokerStatus(
        uid=profile["user_id"],
        name=profile["user_name"],
        email=profile.get("email", ""),
        available_balance=Decimal(str(equity.get("net", "0"))),
        margin_used=Decimal(str(equity.get("used", "0"))),
    )


@app.get("/exchanges/status", response_model=ExchangeStatus)
async def exchange_status() -> ExchangeStatus:
    """Return current trading status for NSE, CDS, and MCX."""
    return ExchangeStatus(
        nse=_exchange_status("NSE", time(9, 15), time(15, 30)),
        cds=_exchange_status("CDS", time(9, 15), time(15, 30)),
        mcx=_exchange_status("MCX", time(9, 0), time(23, 30)),
    )


@app.get("/sentiment/health")
async def sentiment_health() -> dict[str, str]:
    """Check sentiment model availability via import inspection."""
    modules: list[tuple[str, str, str]] = [
        ("iatb.sentiment.finbert_analyzer", "FinbertAnalyzer", "finbert"),
        ("iatb.sentiment.aion_analyzer", "AionAnalyzer", "aion"),
        ("iatb.sentiment.vader_analyzer", "VaderAnalyzer", "vader"),
        ("iatb.sentiment.aggregator", "SentimentAggregator", "aggregator"),
    ]
    health: dict[str, str] = {}
    for module_path, class_name, key in modules:
        try:
            mod = importlib.import_module(module_path)
            getattr(mod, class_name)
            health[key] = "available"
        except Exception as exc:
            logger.debug("Sentiment %s unavailable: %s", key, exc)
            health[key] = "unavailable"
    all_ok = all(v == "available" for v in health.values())
    health["ensemble_status"] = "operational" if all_ok else "degraded"
    return health


_AUDIT_DB = Path("data/audit/trades.sqlite")


@app.get("/pnl/summary")
async def pnl_summary() -> dict[str, str]:
    """Read PnL from trade audit SQLite using Decimal arithmetic."""
    if not _AUDIT_DB.exists():
        return {
            "net_notional_pnl": "0",
            "buy_trades": "0",
            "sell_trades": "0",
            "total_trades": "0",
        }
    try:
        conn = sqlite3.connect(str(_AUDIT_DB))
        conn.row_factory = sqlite3.Row
        today = datetime.now(UTC).date().isoformat()
        rows = conn.execute(
            "SELECT side, quantity, price FROM trade_audit_log WHERE timestamp_utc LIKE ?",
            (f"{today}%",),
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("PnL query failed: %s", exc)
        return {
            "net_notional_pnl": "0",
            "buy_trades": "0",
            "sell_trades": "0",
            "total_trades": "0",
        }
    total = Decimal("0")
    buy_count = 0
    sell_count = 0
    for row in rows:
        qty = Decimal(str(row["quantity"]))
        price = Decimal(str(row["price"]))
        side = str(row["side"])
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
        "total_trades": str(len(rows)),
    }


_LOG_DIR = Path("logs")


@app.get("/logs/tail")
async def logs_tail() -> dict[str, Any]:
    """Return last 30 lines from the most recent deployment log."""
    pattern = str(_LOG_DIR / "deployment_*.log")
    log_files = sorted(glob.glob(pattern), reverse=True)
    if not log_files:
        return {"lines": ["No deployment logs found."], "count": 1}
    try:
        with open(log_files[0], encoding="utf-8") as f:
            all_lines = f.read().splitlines()
        tail = all_lines[-30:]
        return {"lines": tail, "count": len(tail)}
    except Exception as exc:
        logger.warning("Log read failed: %s", exc)
        return {"lines": [f"Error reading log: {exc}"], "count": 1}


@app.post("/scanner/run", response_model=ScannerResponse)
async def run_scanner() -> ScannerResponse:
    """Return instrument scorer readiness status."""
    from iatb.market_strength.regime_detector import MarketRegime
    from iatb.selection.instrument_scorer import InstrumentScorer

    InstrumentScorer()
    return ScannerResponse(
        status="scanner_ready",
        regime=MarketRegime.SIDEWAYS.value,
        scorer_available=True,
    )
