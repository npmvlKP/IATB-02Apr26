"""
Audit logger for paper trading trade persistence.

Thin wrapper around SQLiteStore providing a simple audit logging API
for the paper trading runtime.
"""

import logging
from pathlib import Path

from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    """Persist trade audit records to SQLite for regulatory compliance."""

    def __init__(self, db_path: Path, retention_years: int = 7) -> None:
        self._store = SQLiteStore(db_path, retention_years=retention_years)
        self._store.initialize()
        logger.info("Audit logger initialized at %s", db_path)

    def log_trade(self, record: TradeAuditRecord) -> None:
        """Append a single trade audit record."""
        self._store.append_trade(record)

    def get_trade(self, trade_id: str) -> TradeAuditRecord | None:
        """Retrieve a trade by ID."""
        return self._store.get_trade(trade_id)

    def list_recent_trades(self, limit: int = 100) -> list[TradeAuditRecord]:
        """List most recent trades."""
        return self._store.list_trades(limit=limit)
