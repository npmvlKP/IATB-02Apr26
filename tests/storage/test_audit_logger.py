"""
Tests for AuditLogger in storage layer.
"""

import random
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.storage.audit_logger import AuditLogger
from iatb.storage.sqlite_store import TradeAuditRecord

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _record(trade_id: str, timestamp: datetime) -> TradeAuditRecord:
    return TradeAuditRecord(
        trade_id=trade_id,
        timestamp=create_timestamp(timestamp),
        exchange=Exchange.NSE,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        quantity=create_quantity("5"),
        price=create_price("2500.50"),
        status=OrderStatus.FILLED,
        strategy_id="mom-1",
        metadata={"source": "unit-test"},
    )


class TestAuditLogger:
    """Test AuditLogger wrapper around SQLiteStore."""

    def test_init_creates_db(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        logger = AuditLogger(db)
        assert db.exists()
        assert logger._store._db_path == db

    def test_log_and_retrieve_trade(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        logger = AuditLogger(db)
        ts = datetime.now(UTC)
        rec = _record("T-001", ts)
        logger.log_trade(rec)
        result = logger.get_trade("T-001")
        assert result is not None
        assert result.trade_id == "T-001"
        assert result.symbol == "RELIANCE"

    def test_list_recent_trades(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        logger = AuditLogger(db)
        ts = datetime.now(UTC)
        for i in range(3):
            logger.log_trade(_record(f"T-{i:03d}", ts))
        trades = logger.list_recent_trades(limit=2)
        assert len(trades) == 2

    def test_get_missing_trade_returns_none(self, tmp_path: Path) -> None:
        db = tmp_path / "audit.sqlite"
        logger = AuditLogger(db)
        assert logger.get_trade("NONEXISTENT") is None
