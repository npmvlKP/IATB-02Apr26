"""
Trade audit logger with SQLite persistence.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from iatb.execution.base import ExecutionResult, OrderRequest

logger = logging.getLogger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS trade_audit (
    timestamp_utc TEXT NOT NULL,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    status TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    algo_id TEXT NOT NULL,
    PRIMARY KEY (order_id)
)
"""

_INSERT_SQL = """
INSERT OR REPLACE INTO trade_audit
    (timestamp_utc, order_id, symbol, exchange, side,
     quantity, price, status, strategy_id, algo_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


@dataclass(frozen=True)
class TradeAuditEntry:
    timestamp_utc: datetime
    order_id: str
    symbol: str
    exchange: str
    side: str
    quantity: Decimal
    price: Decimal
    status: str
    strategy_id: str
    algo_id: str


class TradeAuditLogger:
    """Persist every order to SQLite for regulatory audit trail."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_SQL)

    def log_order(
        self,
        request: OrderRequest,
        result: ExecutionResult,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> None:
        """Persist one order + result."""
        now = datetime.now(UTC).isoformat()
        price = str(result.average_price)
        with self._connect() as conn:
            conn.execute(
                _INSERT_SQL,
                (
                    now,
                    result.order_id,
                    request.symbol,
                    request.exchange.value,
                    request.side.value,
                    str(result.filled_quantity),
                    price,
                    result.status.value,
                    strategy_id,
                    algo_id,
                ),
            )
        logger.debug("Audit: %s %s %s", result.order_id, request.symbol, result.status.value)

    def query_daily_trades(self, target_date: date) -> list[TradeAuditEntry]:
        """Retrieve all trades for a given date."""
        prefix = target_date.isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_audit WHERE timestamp_utc LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]


def _row_to_entry(row: sqlite3.Row) -> TradeAuditEntry:
    return TradeAuditEntry(
        timestamp_utc=datetime.fromisoformat(str(row["timestamp_utc"])),
        order_id=str(row["order_id"]),
        symbol=str(row["symbol"]),
        exchange=str(row["exchange"]),
        side=str(row["side"]),
        quantity=Decimal(str(row["quantity"])),
        price=Decimal(str(row["price"])),
        status=str(row["status"]),
        strategy_id=str(row["strategy_id"]),
        algo_id=str(row["algo_id"]),
    )
