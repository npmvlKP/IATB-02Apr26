"""
Tests for SQLite trade audit storage.
"""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

# Set deterministic seeds for reproducibility
random.seed(42)


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


class TestSQLiteStoreQueryTrades:
    """Test query_trades filtering capabilities."""

    @pytest.fixture(autouse=True)
    def _setup_store(self, tmp_path: Path) -> None:
        self.store = SQLiteStore(tmp_path / "query_audit.sqlite3")
        self.now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        self._seed_trades()

    def _seed_trades(self) -> None:
        for i in range(5):
            record = TradeAuditRecord(
                trade_id=f"trade-{i}",
                timestamp=create_timestamp(self.now + timedelta(hours=i)),
                exchange=Exchange.NSE if i % 2 == 0 else Exchange.BSE,
                symbol="RELIANCE" if i % 3 == 0 else "TCS",
                side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                quantity=create_quantity(str(10 + i)),
                price=create_price(str(1000 + i * 10)),
                status=OrderStatus.FILLED if i % 2 == 0 else OrderStatus.PARTIALLY_FILLED,
                strategy_id="strat-a" if i < 3 else "strat-b",
                metadata={"source": "test"},
            )
            self.store.append_trade(record)

    def test_query_by_time_range(self) -> None:
        start = self.now + timedelta(hours=1)
        end = self.now + timedelta(hours=3)
        trades = self.store.query_trades(start_time=start, end_time=end, limit=10)
        ids = [t.trade_id for t in trades]
        # Should include trades at hours 1, 2, 3
        assert len(ids) == 3
        assert "trade-1" in ids
        assert "trade-2" in ids
        assert "trade-3" in ids

    def test_query_by_exchange(self) -> None:
        trades = self.store.query_trades(exchange=Exchange.NSE, limit=10)
        for trade in trades:
            assert trade.exchange == Exchange.NSE

    def test_query_by_symbol(self) -> None:
        trades = self.store.query_trades(symbol="RELIANCE", limit=10)
        for trade in trades:
            assert trade.symbol == "RELIANCE"

    def test_query_by_strategy_id(self) -> None:
        trades = self.store.query_trades(strategy_id="strat-a", limit=10)
        for trade in trades:
            assert trade.strategy_id == "strat-a"

    def test_query_by_side(self) -> None:
        trades = self.store.query_trades(side=OrderSide.SELL, limit=10)
        for trade in trades:
            assert trade.side == OrderSide.SELL

    def test_query_by_status(self) -> None:
        trades = self.store.query_trades(status=OrderStatus.FILLED, limit=10)
        for trade in trades:
            assert trade.status == OrderStatus.FILLED

    def test_query_combined_filters(self) -> None:
        trades = self.store.query_trades(
            start_time=self.now,
            end_time=self.now + timedelta(days=1),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            strategy_id="strat-a",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
            limit=10,
        )
        assert len(trades) == 1
        assert trades[0].trade_id == "trade-0"

    def test_query_returns_ordered_desc(self) -> None:
        trades = self.store.query_trades(limit=3)
        assert len(trades) == 3
        # Should be ordered by timestamp DESC (latest first)
        assert trades[0].timestamp >= trades[1].timestamp
        assert trades[1].timestamp >= trades[2].timestamp

    def test_query_no_matches_returns_empty(self) -> None:
        trades = self.store.query_trades(symbol="NONEXISTENT", limit=10)
        assert trades == []

    def test_query_rejects_non_positive_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit_limit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.query_trades(limit=0)

    def test_query_limit_is_respected(self) -> None:
        trades = self.store.query_trades(limit=2)
        assert len(trades) == 2

    def test_query_time_range_start_only(self) -> None:
        start = self.now + timedelta(hours=2)
        trades = self.store.query_trades(start_time=start, limit=10)
        for trade in trades:
            assert trade.timestamp >= start

    def test_query_time_range_end_only(self) -> None:
        end = self.now + timedelta(hours=2)
        trades = self.store.query_trades(end_time=end, limit=10)
        for trade in trades:
            assert trade.timestamp <= end


class TestSQLiteStoreListTradesByRange:
    """Test list_trades_by_range time-range query."""

    def test_range_filters_correctly(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "range_audit.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        store.append_trade(_record("t1", base))
        store.append_trade(_record("t2", base + timedelta(hours=1)))
        store.append_trade(_record("t3", base + timedelta(hours=2)))
        store.append_trade(_record("t4", base + timedelta(hours=3)))
        trades = store.list_trades_by_range(
            start_utc=base + timedelta(hours=1),
            end_utc=base + timedelta(hours=2),
        )
        assert len(trades) == 2
        assert {t.trade_id for t in trades} == {"t2", "t3"}

    def test_range_returns_empty_when_no_match(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "range_audit2.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        store.append_trade(_record("t1", base))
        trades = store.list_trades_by_range(
            start_utc=base + timedelta(days=1),
            end_utc=base + timedelta(days=2),
        )
        assert trades == []

    def test_range_orders_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "range_audit3.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        store.append_trade(_record("t1", base))
        store.append_trade(_record("t2", base + timedelta(hours=1)))
        trades = store.list_trades_by_range(
            start_utc=base,
            end_utc=base + timedelta(hours=2),
        )
        assert trades[0].timestamp >= trades[1].timestamp

    def test_range_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "range_audit4.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        for i in range(5):
            store.append_trade(_record(f"t{i}", base + timedelta(hours=i)))
        trades = store.list_trades_by_range(
            start_utc=base,
            end_utc=base + timedelta(hours=10),
            limit=2,
        )
        assert len(trades) == 2

    def test_range_rejects_non_positive_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "range_audit5.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades_by_range(
                start_utc=datetime(2026, 1, 1, tzinfo=UTC),
                end_utc=datetime(2026, 1, 2, tzinfo=UTC),
                limit=0,
            )


class TestSQLiteStoreListTradesBySymbol:
    """Test list_trades_by_symbol filter."""

    @pytest.fixture(autouse=True)
    def _setup_store(self, tmp_path: Path) -> None:
        self.store = SQLiteStore(tmp_path / "symbol_audit.sqlite3")
        self.now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        self._seed_trades()

    def _seed_trades(self) -> None:
        symbols = ["RELIANCE", "TCS", "RELIANCE", "INFY", "TCS"]
        exchanges = [Exchange.NSE, Exchange.BSE, Exchange.NSE, Exchange.NSE, Exchange.BSE]
        for i, (sym, exc) in enumerate(zip(symbols, exchanges, strict=False)):
            record = TradeAuditRecord(
                trade_id=f"trade-{i}",
                timestamp=create_timestamp(self.now + timedelta(minutes=i)),
                exchange=exc,
                symbol=sym,
                side=OrderSide.BUY,
                quantity=create_quantity("10"),
                price=create_price("1000"),
                status=OrderStatus.FILLED,
                strategy_id="strat-1",
                metadata={},
            )
            self.store.append_trade(record)

    def test_filter_by_symbol(self) -> None:
        trades = self.store.list_trades_by_symbol("RELIANCE")
        assert len(trades) == 2
        for t in trades:
            assert t.symbol == "RELIANCE"

    def test_filter_by_symbol_and_exchange(self) -> None:
        trades = self.store.list_trades_by_symbol("RELIANCE", exchange=Exchange.NSE)
        assert len(trades) == 2
        for t in trades:
            assert t.symbol == "RELIANCE"
            assert t.exchange == Exchange.NSE

    def test_filter_by_symbol_no_match(self) -> None:
        trades = self.store.list_trades_by_symbol("NONEXISTENT")
        assert trades == []

    def test_filter_respects_limit(self) -> None:
        trades = self.store.list_trades_by_symbol("TCS", limit=1)
        assert len(trades) == 1

    def test_rejects_empty_symbol(self) -> None:
        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            self.store.list_trades_by_symbol("")

    def test_rejects_non_positive_limit(self) -> None:
        with pytest.raises(ConfigError, match="limit must be positive"):
            self.store.list_trades_by_symbol("RELIANCE", limit=0)


class TestSQLiteStoreListTradesByStrategy:
    """Test list_trades_by_strategy filter."""

    @pytest.fixture(autouse=True)
    def _setup_store(self, tmp_path: Path) -> None:
        self.store = SQLiteStore(tmp_path / "strategy_audit.sqlite3")
        self.now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        self._seed_trades()

    def _seed_trades(self) -> None:
        strategies = ["strat-a", "strat-a", "strat-b", "strat-a", "strat-b"]
        for i, strat in enumerate(strategies):
            record = TradeAuditRecord(
                trade_id=f"trade-{i}",
                timestamp=create_timestamp(self.now + timedelta(minutes=i)),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=create_quantity("10"),
                price=create_price("1000"),
                status=OrderStatus.FILLED,
                strategy_id=strat,
                metadata={},
            )
            self.store.append_trade(record)

    def test_filter_by_strategy(self) -> None:
        trades = self.store.list_trades_by_strategy("strat-a")
        assert len(trades) == 3
        for t in trades:
            assert t.strategy_id == "strat-a"

    def test_filter_by_strategy_no_match(self) -> None:
        trades = self.store.list_trades_by_strategy("nonexistent")
        assert trades == []

    def test_filter_respects_limit(self) -> None:
        trades = self.store.list_trades_by_strategy("strat-a", limit=2)
        assert len(trades) == 2

    def test_rejects_empty_strategy_id(self) -> None:
        with pytest.raises(ConfigError, match="strategy_id cannot be empty"):
            self.store.list_trades_by_strategy("")

    def test_rejects_non_positive_limit(self) -> None:
        with pytest.raises(ConfigError, match="limit must be positive"):
            self.store.list_trades_by_strategy("strat-a", limit=0)


class TestSQLiteStoreBatchInsert:
    """Test batch INSERT for high-throughput writes."""

    def test_batch_insert_all_records_persisted(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "batch_audit.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        records = [_record(f"batch-{i}", base + timedelta(minutes=i)) for i in range(100)]
        store.append_trades_batch(records)
        for i in range(100):
            assert store.get_trade(f"batch-{i}") is not None

    def test_batch_insert_orders_by_timestamp(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "batch_audit2.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        records = [_record(f"batch-{i}", base + timedelta(minutes=i)) for i in range(5)]
        store.append_trades_batch(records)
        trades = store.list_trades(limit=5)
        assert trades[0].timestamp >= trades[-1].timestamp

    def test_batch_insert_empty_list_no_op(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "batch_audit3.sqlite3")
        store.append_trades_batch([])
        assert store.list_trades() == []

    def test_batch_insert_duplicate_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "batch_audit4.sqlite3")
        base = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        records = [_record("dup", base), _record("dup", base + timedelta(minutes=1))]
        with pytest.raises(ConfigError, match="Batch insert conflict"):
            store.append_trades_batch(records)


class TestSQLiteStoreWalMode:
    """Test WAL mode is enabled on SQLite connections."""

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "wal_audit.sqlite3")
        store.initialize()
        with store._connect() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            assert row is not None
            assert row[0].upper() == "WAL"
