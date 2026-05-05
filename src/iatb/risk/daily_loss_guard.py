"""
Daily loss guard with automatic kill-switch engagement.
Provides ``record_trade`` integration for the unified risk pipeline.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from iatb.core.exceptions import ConfigError

if TYPE_CHECKING:
    from iatb.risk.kill_switch import KillSwitch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyLossState:
    cumulative_pnl: Decimal
    limit: Decimal
    breached: bool
    trade_count: int


class _DailyLossStateStore:
    """SQLite-backed persistence for DailyLossGuard state.

    Stores cumulative PnL and trade count keyed by date (YYYY-MM-DD).
    A new day automatically starts a fresh record.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_loss_state (
                date TEXT PRIMARY KEY,
                cumulative_pnl TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_loss_date
            ON daily_loss_state (date)
            """
        )

    def save(self, date_str: str, cumulative_pnl: Decimal, trade_count: int) -> None:
        """Persist state for a given date."""
        now_iso = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            self._init_schema(conn)
            conn.execute(
                """
                INSERT INTO daily_loss_state (date, cumulative_pnl, trade_count, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    cumulative_pnl=excluded.cumulative_pnl,
                    trade_count=excluded.trade_count,
                    updated_at=excluded.updated_at
                """,
                (date_str, str(cumulative_pnl), trade_count, now_iso),
            )

    def load(self, date_str: str) -> tuple[Decimal, int] | None:
        """Load persisted state for a given date."""
        with self._connect() as conn:
            self._init_schema(conn)
            row = conn.execute(
                "SELECT cumulative_pnl, trade_count FROM daily_loss_state WHERE date = ?",
                (date_str,),
            ).fetchone()
        if row is None:
            return None
        return Decimal(str(row["cumulative_pnl"])), int(row["trade_count"])

    def purge_before(self, cutoff_date_str: str) -> int:
        """Remove records older than the given date."""
        with self._connect() as conn:
            self._init_schema(conn)
            cursor = conn.execute(
                "DELETE FROM daily_loss_state WHERE date < ?",
                (cutoff_date_str,),
            )
        return int(cursor.rowcount)


class DailyLossGuard:
    """Track intraday PnL and engage kill switch on breach."""

    def __init__(
        self,
        max_daily_loss_pct: Decimal,
        starting_nav: Decimal,
        kill_switch: "KillSwitch",
        *,
        state_db_path: Path | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        if max_daily_loss_pct <= Decimal("0") or max_daily_loss_pct > Decimal("1"):
            msg = "max_daily_loss_pct must be in (0, 1]"
            raise ConfigError(msg)
        if starting_nav <= Decimal("0"):
            msg = "starting_nav must be positive"
            raise ConfigError(msg)
        self._max_pct = max_daily_loss_pct
        self._limit = starting_nav * max_daily_loss_pct
        self._cumulative_pnl = Decimal("0")
        self._trade_count = 0
        self._kill_switch = kill_switch
        self._state_store: _DailyLossStateStore | None = None
        if state_db_path is not None:
            self._state_store = _DailyLossStateStore(state_db_path)
        # Load persisted state if available
        today = (now_utc or datetime.now(UTC)).strftime("%Y-%m-%d")
        if self._state_store is not None:
            persisted = self._state_store.load(today)
            if persisted is not None:
                self._cumulative_pnl, self._trade_count = persisted
                logger.info(
                    "DailyLossGuard loaded persisted state: PnL=%s, trades=%d",
                    self._cumulative_pnl,
                    self._trade_count,
                )

    @property
    def state(self) -> DailyLossState:
        return DailyLossState(
            cumulative_pnl=self._cumulative_pnl,
            limit=self._limit,
            breached=self._cumulative_pnl <= -self._limit,
            trade_count=self._trade_count,
        )

    def record_trade(self, pnl: Decimal, now_utc: datetime) -> DailyLossState:
        """Add trade PnL. Auto-engage kill switch if limit breached."""
        _validate_utc(now_utc)
        self._cumulative_pnl += pnl
        self._trade_count += 1
        if self._cumulative_pnl <= -self._limit:
            logger.warning(
                "Daily loss limit breached: PnL=%s, limit=-%s",
                self._cumulative_pnl,
                self._limit,
            )
            self._kill_switch.engage(
                f"daily loss limit breached: {self._cumulative_pnl}",
                now_utc,
            )
        self._persist_state(now_utc)
        return self.state

    def reset(self, starting_nav: Decimal, now_utc: datetime) -> None:
        """Reset for new trading day."""
        _validate_utc(now_utc)
        if starting_nav <= Decimal("0"):
            msg = "starting_nav must be positive"
            raise ConfigError(msg)
        self._limit = starting_nav * self._max_pct
        self._cumulative_pnl = Decimal("0")
        self._trade_count = 0
        logger.info("Daily loss guard reset: NAV=%s, limit=%s", starting_nav, self._limit)
        self._persist_state(now_utc)

    def save_state(self, now_utc: datetime) -> None:
        """Explicitly persist current state."""
        _validate_utc(now_utc)
        self._persist_state(now_utc)

    def load_state(self, now_utc: datetime) -> bool:
        """Explicitly load state for the current day. Returns True if loaded."""
        _validate_utc(now_utc)
        if self._state_store is None:
            return False
        today = now_utc.strftime("%Y-%m-%d")
        persisted = self._state_store.load(today)
        if persisted is not None:
            self._cumulative_pnl, self._trade_count = persisted
            return True
        return False

    def _persist_state(self, now_utc: datetime) -> None:
        """Internal helper to persist state to SQLite."""
        if self._state_store is None:
            return
        date_str = now_utc.strftime("%Y-%m-%d")
        try:
            self._state_store.save(date_str, self._cumulative_pnl, self._trade_count)
        except Exception:
            logger.exception("Failed to persist DailyLossGuard state")


def _validate_utc(dt: datetime) -> None:
    if dt.tzinfo != UTC:
        msg = "datetime must be UTC"
        raise ConfigError(msg)
