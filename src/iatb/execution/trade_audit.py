"""
Trade audit logger using unified SQLite storage layer.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeAuditEntry:
    """Legacy audit entry for backward compatibility."""

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
    """Persist every order to SQLite for regulatory audit trail using unified storage."""

    def __init__(self, db_path: Path, retention_years: int = 7) -> None:
        self._store = SQLiteStore(db_path, retention_years=retention_years)
        self._store.initialize()

    def log_order(
        self,
        request: OrderRequest,
        result: ExecutionResult,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> None:
        """Persist one order + result."""
        record = TradeAuditRecord(
            trade_id=result.order_id,
            timestamp=create_timestamp(datetime.now(UTC)),
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            quantity=create_quantity(str(result.filled_quantity)),
            price=create_price(str(result.average_price)),
            status=result.status,
            strategy_id=strategy_id,
            metadata={"algo_id": algo_id},
        )
        self._store.append_trade(record)
        logger.debug("Audit: %s %s %s", result.order_id, request.symbol, result.status.value)

    def query_daily_trades(self, target_date: date) -> list[TradeAuditEntry]:
        """Retrieve all trades for a given date."""
        start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
        end_time = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

        # Fetch all trades and filter by date
        all_trades = self._store.list_trades(limit=10000)
        filtered = [trade for trade in all_trades if start_time <= trade.timestamp <= end_time]

        return [_record_to_entry(trade) for trade in filtered]


def _record_to_entry(record: TradeAuditRecord) -> TradeAuditEntry:
    """Convert TradeAuditRecord to legacy TradeAuditEntry."""
    return TradeAuditEntry(
        timestamp_utc=record.timestamp,
        order_id=record.trade_id,
        symbol=record.symbol,
        exchange=record.exchange.value,
        side=record.side.value,
        quantity=Decimal(str(record.quantity)),
        price=Decimal(str(record.price)),
        status=record.status.value,
        strategy_id=record.strategy_id,
        algo_id=record.metadata.get("algo_id", ""),
    )
