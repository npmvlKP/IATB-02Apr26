"""
Tests for SQLite trade audit storage.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord


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


class TestSQLiteStore:
    """Test SQLiteStore behaviors and fail-closed paths."""

    def test_append_and_get_trade_roundtrip(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        record = _record("trade-1", datetime(2026, 1, 1, 9, 15, tzinfo=UTC))
        store.append_trade(record)
        loaded = store.get_trade("trade-1")
        assert loaded is not None
        assert loaded.trade_id == "trade-1"
        assert loaded.price == create_price("2500.50")
        assert loaded.metadata == {"source": "unit-test"}

    def test_duplicate_trade_id_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        timestamp = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        store.append_trade(_record("trade-dup", timestamp))
        with pytest.raises(ConfigError, match="already exists"):
            store.append_trade(_record("trade-dup", timestamp + timedelta(minutes=1)))

    def test_list_trades_orders_by_latest_timestamp(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        store.append_trade(_record("trade-1", datetime(2026, 1, 1, 9, 15, tzinfo=UTC)))
        store.append_trade(_record("trade-2", datetime(2026, 1, 1, 9, 16, tzinfo=UTC)))
        trades = store.list_trades(limit=2)
        assert [trade.trade_id for trade in trades] == ["trade-2", "trade-1"]

    def test_list_trades_rejects_non_positive_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades(limit=0)

    def test_purge_expired_deletes_old_records(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        old_trade_time = now - timedelta(days=366)
        store.append_trade(_record("old-trade", old_trade_time))
        store.append_trade(_record("new-trade", now))
        deleted = store.purge_expired(reference_time=now)
        assert deleted == 1
        assert store.get_trade("old-trade") is None
        assert store.get_trade("new-trade") is not None

    def test_purge_expired_rejects_naive_reference_time(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="timezone-aware"):
            store.purge_expired(reference_time=datetime(2026, 1, 1, 10, 0))  # noqa: DTZ001

    def test_retention_years_must_be_positive(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="retention_years must be positive"):
            SQLiteStore(tmp_path / "audit.sqlite3", retention_years=0)
