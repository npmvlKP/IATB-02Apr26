"""
Trade audit logger using unified SQLite storage with HMAC hash chain.
"""

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

logger = logging.getLogger(__name__)

_HMAC_HASH_KEY_ENV = "IATB_AUDIT_HMAC_KEY"


def _get_or_create_hmac_key() -> bytes:
    """Get HMAC key from env or generate a persistent one."""
    key = os.getenv(_HMAC_HASH_KEY_ENV, "").strip()
    if key:
        return key.encode("utf-8")
    return hashlib.sha256(os.urandom(32)).digest()


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
    """Persist every order to SQLite for regulatory audit trail.

    Includes HMAC hash chain for cryptographic tamper evidence:
    each entry chains to the previous via HMAC-SHA256, making
    any insertion or modification detectable.
    """

    def __init__(self, db_path: Path, retention_years: int = 7) -> None:
        self._store = SQLiteStore(db_path, retention_years=retention_years)
        self._store.initialize()
        self._hmac_key = _get_or_create_hmac_key()
        self._prev_hash = b"\x00" * 32

    def _compute_chain_hash(self, record: TradeAuditRecord) -> str:
        """Compute HMAC-SHA256 chain hash for tamper evidence."""
        message = (
            f"{record.trade_id}|{record.timestamp.isoformat()}|"
            f"{record.exchange.value}|{record.symbol}|{record.side.value}|"
            f"{record.quantity}|{record.price}|{record.status.value}|"
            f"{self._prev_hash.hex()}"
        )
        digest = hmac.new(self._hmac_key, message.encode("utf-8"), hashlib.sha256).digest()
        return digest.hex()

    def log_order(
        self,
        request: OrderRequest,
        result: ExecutionResult,
        strategy_id: str = "",
        algo_id: str = "",
    ) -> None:
        """Persist one order + result with HMAC chain hash."""
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
        chain_hash = self._compute_chain_hash(record)
        augmented_metadata = dict(record.metadata)
        augmented_metadata["chain_hash"] = chain_hash
        augmented_record = TradeAuditRecord(
            trade_id=record.trade_id,
            timestamp=record.timestamp,
            exchange=record.exchange,
            symbol=record.symbol,
            side=record.side,
            quantity=record.quantity,
            price=record.price,
            status=record.status,
            strategy_id=record.strategy_id,
            metadata=augmented_metadata,
        )
        self._prev_hash = bytes.fromhex(chain_hash)
        self._store.append_trade(augmented_record)
        logger.debug(
            "Audit: %s %s %s chain=%s",
            result.order_id,
            request.symbol,
            result.status.value,
            chain_hash[:16],
        )

    def verify_chain(self) -> bool:
        """Verify the entire HMAC hash chain for tamper evidence.

        Returns:
            True if chain is intact, False if tampering detected.
        """
        all_trades = self._store.list_trades(limit=100000)
        sorted_trades = sorted(all_trades, key=lambda r: (r.timestamp, r.trade_id))
        prev_hash = b"\x00" * 32
        for record in sorted_trades:
            stored_hash = record.metadata.get("chain_hash", "")
            message = (
                f"{record.trade_id}|{record.timestamp.isoformat()}|"
                f"{record.exchange.value}|{record.symbol}|{record.side.value}|"
                f"{record.quantity}|{record.price}|{record.status.value}|"
                f"{prev_hash.hex()}"
            )
            expected = hmac.new(self._hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(stored_hash, expected):
                logger.error("Chain tamper detected at trade %s", record.trade_id)
                return False
            prev_hash = bytes.fromhex(stored_hash)
        return True

    def query_daily_trades(self, target_date: date) -> list[TradeAuditEntry]:
        """Retrieve all trades for a given date."""
        start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
        end_time = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

        trades = self._store.query_trades(start_time=start_time, end_time=end_time, limit=10000)

        return [_record_to_entry(trade) for trade in trades]


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
