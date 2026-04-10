"""
Lightweight SQLite status polling for dashboard.

Replaces urlopen timeout with direct SQLite reads from the shared
engine database. Zero new deps, <10ms overhead per poll.

Reads engine health, recent trades, and scanner results from the
same SQLite database that the engine writes to.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path("data/audit/trades.sqlite")
_ENGINE_STATUS_TABLE = "engine_status"
_SCANNER_RESULTS_TABLE = "scanner_results"


@dataclass(frozen=True)
class EngineStatus:
    """Snapshot of engine health from SQLite."""

    is_running: bool
    mode: str
    last_heartbeat_utc: datetime | None
    uptime_seconds: int
    trades_today: int
    scanner_instruments_count: int


@dataclass(frozen=True)
class ZerodhaAccountSnapshot:
    """Cached Zerodha account data from SQLite."""

    user_id: str
    user_name: str
    user_email: str
    available_balance: Decimal
    equity_margin: Decimal
    commodity_margin: Decimal
    snapshot_timestamp_utc: datetime | None


@dataclass(frozen=True)
class ExchangeSessionStatus:
    """Per-exchange open/closed status."""

    exchange: Exchange
    is_open: bool
    session_open_time: str
    session_close_time: str
    status_label: str


@dataclass(frozen=True)
class ScannerInstrumentRow:
    """Single instrument row from scanner results."""

    symbol: str
    exchange: Exchange
    sentiment_score: Decimal
    market_strength_score: Decimal
    drl_score: Decimal
    volume_profile_score: Decimal
    composite_score: Decimal
    is_approved: bool
    scan_timestamp_utc: datetime | None


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        msg = f"status database not found: {db_path}"
        raise ConfigError(msg)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection, table: str, columns: str) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ({columns})"  # nosec B608  # noqa: S608
    )


def initialize_status_tables(db_path: Path = _DEFAULT_DB_PATH) -> None:
    """Create engine_status and scanner_results tables if missing."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_table(
            conn,
            _ENGINE_STATUS_TABLE,
            "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_utc TEXT NOT NULL",
        )
        _ensure_table(
            conn,
            _SCANNER_RESULTS_TABLE,
            (
                "symbol TEXT NOT NULL, exchange TEXT NOT NULL, "
                "sentiment_score TEXT NOT NULL, market_strength_score TEXT NOT NULL, "
                "drl_score TEXT NOT NULL, volume_profile_score TEXT NOT NULL, "
                "composite_score TEXT NOT NULL, is_approved INTEGER NOT NULL, "
                "scan_timestamp_utc TEXT NOT NULL"
            ),
        )
    finally:
        conn.close()


def write_engine_heartbeat(
    db_path: Path = _DEFAULT_DB_PATH,
    mode: str = "PAPER",
    trades_today: int = 0,
) -> None:
    """Write engine heartbeat to SQLite for dashboard polling."""
    initialize_status_tables(db_path)
    now_iso = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        for key, value in [
            ("is_running", "1"),
            ("mode", mode),
            ("last_heartbeat_utc", now_iso),
            ("trades_today", str(trades_today)),
        ]:
            conn.execute(
                f"INSERT OR REPLACE INTO {_ENGINE_STATUS_TABLE} "  # nosec B608  # noqa: S608
                "(key, value, updated_utc) VALUES (?, ?, ?)",
                (key, value, now_iso),
            )


def write_zerodha_snapshot(
    user_id: str,
    user_name: str,
    user_email: str,
    available_balance: Decimal,
    equity_margin: Decimal,
    commodity_margin: Decimal,
    db_path: Path = _DEFAULT_DB_PATH,
) -> None:
    """Persist Zerodha account snapshot to SQLite for dashboard."""
    initialize_status_tables(db_path)
    now_iso = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        for key, value in [
            ("zerodha_user_id", user_id),
            ("zerodha_user_name", user_name),
            ("zerodha_user_email", user_email),
            ("zerodha_available_balance", str(available_balance)),
            ("zerodha_equity_margin", str(equity_margin)),
            ("zerodha_commodity_margin", str(commodity_margin)),
            ("zerodha_snapshot_utc", now_iso),
        ]:
            conn.execute(
                f"INSERT OR REPLACE INTO {_ENGINE_STATUS_TABLE} "  # nosec B608  # noqa: S608
                "(key, value, updated_utc) VALUES (?, ?, ?)",
                (key, value, now_iso),
            )


def write_scanner_results(
    instruments: list[ScannerInstrumentRow],
    db_path: Path = _DEFAULT_DB_PATH,
) -> None:
    """Persist scanner results to SQLite for dashboard display."""
    initialize_status_tables(db_path)
    now_iso = datetime.now(UTC).isoformat()
    with _connect(db_path) as conn:
        conn.execute(f"DELETE FROM {_SCANNER_RESULTS_TABLE}")  # nosec B608  # noqa: S608
        for inst in instruments:
            conn.execute(
                f"INSERT INTO {_SCANNER_RESULTS_TABLE} "  # nosec B608  # noqa: S608
                "(symbol, exchange, sentiment_score, market_strength_score, "
                "drl_score, volume_profile_score, composite_score, "
                "is_approved, scan_timestamp_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    inst.symbol,
                    inst.exchange.value,
                    str(inst.sentiment_score),
                    str(inst.market_strength_score),
                    str(inst.drl_score),
                    str(inst.volume_profile_score),
                    str(inst.composite_score),
                    1 if inst.is_approved else 0,
                    inst.scan_timestamp_utc.isoformat() if inst.scan_timestamp_utc else now_iso,
                ),
            )


def read_engine_status(db_path: Path = _DEFAULT_DB_PATH) -> EngineStatus:
    """Poll engine status from SQLite (<10ms)."""
    if not db_path.exists():
        return EngineStatus(
            is_running=False,
            mode="UNKNOWN",
            last_heartbeat_utc=None,
            uptime_seconds=0,
            trades_today=0,
            scanner_instruments_count=0,
        )
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT key, value FROM {_ENGINE_STATUS_TABLE}"  # nosec B608  # noqa: S608
            ).fetchall()
            data = {str(row["key"]): str(row["value"]) for row in rows}
            scanner_count = conn.execute(
                f"SELECT COUNT(*) as cnt FROM {_SCANNER_RESULTS_TABLE}"  # nosec B608  # noqa: S608
            ).fetchone()

        is_running = data.get("is_running") == "1"
        last_hb_str = data.get("last_heartbeat_utc")
        last_hb = None
        uptime = 0
        if last_hb_str:
            try:
                last_hb = datetime.fromisoformat(last_hb_str)
                if last_hb.tzinfo is None:
                    last_hb = last_hb.replace(tzinfo=UTC)
                delta = (datetime.now(UTC) - last_hb).total_seconds()
                uptime = max(0, int(delta))
            except (ValueError, OSError):
                last_hb = None

        count = int(scanner_count["cnt"]) if scanner_count else 0

        return EngineStatus(
            is_running=is_running,
            mode=data.get("mode", "UNKNOWN"),
            last_heartbeat_utc=last_hb,
            uptime_seconds=uptime,
            trades_today=int(data.get("trades_today", "0")),
            scanner_instruments_count=count,
        )
    except (sqlite3.Error, ConfigError):
        logger.debug("Engine status poll failed, returning unavailable")
        return EngineStatus(
            is_running=False,
            mode="UNKNOWN",
            last_heartbeat_utc=None,
            uptime_seconds=0,
            trades_today=0,
            scanner_instruments_count=0,
        )


def read_zerodha_snapshot(db_path: Path = _DEFAULT_DB_PATH) -> ZerodhaAccountSnapshot | None:
    """Poll Zerodha account snapshot from SQLite."""
    if not db_path.exists():
        return None
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT key, value FROM {_ENGINE_STATUS_TABLE}"  # nosec B608  # noqa: S608
            ).fetchall()
        data = {str(row["key"]): str(row["value"]) for row in rows}
        user_id = data.get("zerodha_user_id")
        if not user_id:
            return None
        ts_str = data.get("zerodha_snapshot_utc")
        ts = None
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
            except (ValueError, OSError):
                ts = None
        return ZerodhaAccountSnapshot(
            user_id=user_id,
            user_name=data.get("zerodha_user_name", ""),
            user_email=data.get("zerodha_user_email", ""),
            available_balance=Decimal(data.get("zerodha_available_balance", "0")),
            equity_margin=Decimal(data.get("zerodha_equity_margin", "0")),
            commodity_margin=Decimal(data.get("zerodha_commodity_margin", "0")),
            snapshot_timestamp_utc=ts,
        )
    except (sqlite3.Error, ConfigError, Exception):  # noqa: BLE001
        logger.debug("Zerodha snapshot poll failed")
        return None


def read_scanner_results(db_path: Path = _DEFAULT_DB_PATH) -> list[ScannerInstrumentRow]:
    """Poll scanner results from SQLite for dashboard matrix display."""
    if not db_path.exists():
        return []
    try:
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM {_SCANNER_RESULTS_TABLE} "  # nosec B608  # noqa: S608
                "ORDER BY composite_score DESC"
            ).fetchall()
        results: list[ScannerInstrumentRow] = []
        for row in rows:
            ts_str = str(row["scan_timestamp_utc"])
            ts = None
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
            except (ValueError, OSError):
                ts = None
            results.append(
                ScannerInstrumentRow(
                    symbol=str(row["symbol"]),
                    exchange=Exchange(str(row["exchange"])),
                    sentiment_score=Decimal(str(row["sentiment_score"])),
                    market_strength_score=Decimal(str(row["market_strength_score"])),
                    drl_score=Decimal(str(row["drl_score"])),
                    volume_profile_score=Decimal(str(row["volume_profile_score"])),
                    composite_score=Decimal(str(row["composite_score"])),
                    is_approved=bool(int(row["is_approved"])),
                    scan_timestamp_utc=ts,
                )
            )
        return results
    except (sqlite3.Error, ConfigError, Exception):  # noqa: BLE001
        logger.debug("Scanner results poll failed")
        return []


def read_exchange_session_status(
    exchange: Exchange,
    open_time: str = "09:15",
    close_time: str = "15:30",
) -> ExchangeSessionStatus:
    """Determine if exchange is open/closed based on IST current time.

    Uses local clock comparison against configured session window.
    All times interpreted as IST (UTC+5:30).
    """
    from datetime import timedelta

    now_utc = datetime.now(UTC)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset

    ist_today = now_ist.date()
    weekday = ist_today.weekday()
    if weekday >= 5:
        return ExchangeSessionStatus(
            exchange=exchange,
            is_open=False,
            session_open_time=open_time,
            session_close_time=close_time,
            status_label="CLOSED (Weekend)",
        )

    try:
        open_parts = open_time.split(":")
        close_parts = close_time.split(":")
        open_h, open_m = int(open_parts[0]), int(open_parts[1])
        close_h, close_m = int(close_parts[0]), int(close_parts[1])
    except (ValueError, IndexError):
        return ExchangeSessionStatus(
            exchange=exchange,
            is_open=False,
            session_open_time=open_time,
            session_close_time=close_time,
            status_label="ERROR",
        )

    now_minutes = now_ist.hour * 60 + now_ist.minute
    open_minutes = open_h * 60 + open_m
    close_minutes = close_h * 60 + close_m

    is_open = open_minutes <= now_minutes < close_minutes
    if is_open:
        label = "OPEN"
    elif now_minutes < open_minutes:
        label = "PRE-MARKET"
    else:
        label = "CLOSED"

    return ExchangeSessionStatus(
        exchange=exchange,
        is_open=is_open,
        session_open_time=open_time,
        session_close_time=close_time,
        status_label=label,
    )
