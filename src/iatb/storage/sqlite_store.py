"""
SQLite-backed trade audit storage.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    Price,
    Quantity,
    Timestamp,
    create_price,
    create_quantity,
    create_timestamp,
)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} cannot be empty"
        raise ConfigError(msg)


def _normalize_metadata(metadata: dict[str, str]) -> dict[str, str]:
    return dict(metadata)


@dataclass(frozen=True)
class TradeAuditRecord:
    """Typed trade record for SEBI-grade audit persistence."""

    trade_id: str
    timestamp: Timestamp
    exchange: Exchange
    symbol: str
    side: OrderSide
    quantity: Quantity
    price: Price
    status: OrderStatus
    strategy_id: str
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", create_timestamp(self.timestamp))
        _require_non_empty_text(self.trade_id, "trade_id")
        _require_non_empty_text(self.symbol, "symbol")
        _require_non_empty_text(self.strategy_id, "strategy_id")
        object.__setattr__(self, "metadata", _normalize_metadata(self.metadata))


def _record_to_row(
    record: TradeAuditRecord,
) -> tuple[str, str, str, str, str, str, str, str, str, str]:
    return (
        record.trade_id,
        record.timestamp.isoformat(),
        record.exchange.value,
        record.symbol,
        record.side.value,
        str(record.quantity),
        str(record.price),
        record.status.value,
        record.strategy_id,
        json.dumps(record.metadata, sort_keys=True),
    )


def _parse_timestamp(raw_value: str) -> Timestamp:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        msg = f"Invalid timestamp in trade_audit_log: {raw_value!r}"
        raise ConfigError(msg) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return create_timestamp(parsed.astimezone(UTC))


def _row_to_record(row: sqlite3.Row) -> TradeAuditRecord:
    metadata = json.loads(str(row["metadata_json"]))
    if not isinstance(metadata, dict):
        msg = "metadata_json must decode to dictionary"
        raise ConfigError(msg)
    return TradeAuditRecord(
        trade_id=str(row["trade_id"]),
        timestamp=_parse_timestamp(str(row["timestamp_utc"])),
        exchange=Exchange(str(row["exchange"])),
        symbol=str(row["symbol"]),
        side=OrderSide(str(row["side"])),
        quantity=create_quantity(str(row["quantity"])),
        price=create_price(str(row["price"])),
        status=OrderStatus(str(row["status"])),
        strategy_id=str(row["strategy_id"]),
        metadata={str(key): str(value) for key, value in metadata.items()},
    )


class SQLiteStore:
    """Store and query trade audit records in SQLite."""

    def __init__(self, db_path: Path, retention_years: int = 7) -> None:
        if retention_years <= 0:
            msg = "retention_years must be positive"
            raise ConfigError(msg)
        self._db_path = db_path
        self._retention_years = retention_years

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._enable_wal(connection)
            self._create_schema(connection)

    def _enable_wal(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA journal_mode=WAL")

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_audit_log (
                trade_id TEXT PRIMARY KEY,
                timestamp_utc TEXT NOT NULL,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT NOT NULL,
                status TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_audit_timestamp
            ON trade_audit_log (timestamp_utc)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_audit_exchange
            ON trade_audit_log (exchange)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_audit_symbol
            ON trade_audit_log (symbol)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trade_audit_strategy
            ON trade_audit_log (strategy_id)
            """
        )

    def append_trade(self, record: TradeAuditRecord) -> None:
        self.initialize()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO trade_audit_log (
                        trade_id, timestamp_utc, exchange, symbol, side,
                        quantity, price, status, strategy_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _record_to_row(record),
                )
        except sqlite3.IntegrityError as exc:
            msg = f"trade_id already exists: {record.trade_id}"
            raise ConfigError(msg) from exc

    def get_trade(self, trade_id: str) -> TradeAuditRecord | None:
        _require_non_empty_text(trade_id, "trade_id")
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trade_audit_log WHERE trade_id = ?",
                (trade_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def list_trades(self, limit: int = 100) -> list[TradeAuditRecord]:
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM trade_audit_log
                ORDER BY timestamp_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    @staticmethod
    def _build_query(conditions: list[str]) -> str:
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        if where_clause:
            parts = [
                "SELECT * FROM trade_audit_log",
                where_clause,
                "ORDER BY timestamp_utc DESC LIMIT ?",
            ]
            return " ".join(parts)
        return "SELECT * FROM trade_audit_log ORDER BY timestamp_utc DESC LIMIT ?"

    @staticmethod
    def _build_filter_conditions(
        conditions: list[str],
        params: list[object],
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        exchange: Exchange | None,
        symbol: str | None,
        strategy_id: str | None,
        side: OrderSide | None,
        status: OrderStatus | None,
    ) -> None:
        if start_time is not None:
            conditions.append("timestamp_utc >= ?")
            params.append(start_time.isoformat())
        if end_time is not None:
            conditions.append("timestamp_utc <= ?")
            params.append(end_time.isoformat())
        if exchange is not None:
            conditions.append("exchange = ?")
            params.append(exchange.value)
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if strategy_id is not None:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if side is not None:
            conditions.append("side = ?")
            params.append(side.value)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

    def query_trades(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        exchange: Exchange | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        side: OrderSide | None = None,
        status: OrderStatus | None = None,
        limit: int = 100,
    ) -> list[TradeAuditRecord]:
        """Query trades with optional filtering.

        Args:
            start_time: Optional UTC-aware start timestamp (inclusive).
            end_time: Optional UTC-aware end timestamp (inclusive).
            exchange: Optional exchange filter.
            symbol: Optional symbol filter (exact match).
            strategy_id: Optional strategy filter (exact match).
            side: Optional side filter.
            status: Optional status filter.
            limit: Maximum number of records to return.

        Returns:
            List of matching TradeAuditRecord ordered by timestamp DESC.
        """
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        self.initialize()
        conditions: list[str] = []
        params: list[object] = []
        self._build_filter_conditions(
            conditions,
            params,
            start_time=start_time,
            end_time=end_time,
            exchange=exchange,
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            status=status,
        )
        params.append(limit)
        query = self._build_query(conditions)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def purge_expired(self, reference_time: datetime | None = None) -> int:
        if reference_time is None:
            anchor = datetime.now(UTC)
        elif reference_time.tzinfo is None:
            msg = "reference_time must be timezone-aware"
            raise ConfigError(msg)
        else:
            anchor = reference_time.astimezone(UTC)
        cutoff = anchor - timedelta(days=365 * self._retention_years)
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM trade_audit_log WHERE timestamp_utc < ?",
                (cutoff.isoformat(),),
            )
        return int(cursor.rowcount)
