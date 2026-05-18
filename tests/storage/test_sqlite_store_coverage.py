"""
Comprehensive tests for SQLite trade audit storage.
Targets 90%+ coverage for src/iatb/storage/sqlite_store.py
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.storage.sqlite_store import (
    SQLiteStore,
    TradeAuditRecord,
    _normalize_metadata,
    _parse_timestamp,
    _record_to_row,
    _require_non_empty_text,
    _row_to_record,
)


def _record(
    trade_id: str,
    timestamp: datetime,
    exchange: Exchange = Exchange.NSE,
    symbol: str = "RELIANCE",
    side: OrderSide = OrderSide.BUY,
    quantity: str = "5",
    price: str = "2500.50",
    status: OrderStatus = OrderStatus.FILLED,
    strategy_id: str = "mom-1",
    metadata: dict[str, str] | None = None,
) -> TradeAuditRecord:
    return TradeAuditRecord(
        trade_id=trade_id,
        timestamp=create_timestamp(timestamp),
        exchange=exchange,
        symbol=symbol,
        side=side,
        quantity=create_quantity(quantity),
        price=create_price(price),
        status=status,
        strategy_id=strategy_id,
        metadata=metadata or {"source": "unit-test"},
    )


class TestRequireNonEmptyText:
    """Test _require_non_empty_text validation."""

    def test_valid_text_passes(self) -> None:
        _require_non_empty_text("valid", "field_name")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ConfigError, match="field_name cannot be empty"):
            _require_non_empty_text("", "field_name")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ConfigError, match="field_name cannot be empty"):
            _require_non_empty_text("   ", "field_name")

    def test_whitespace_with_newline_raises(self) -> None:
        with pytest.raises(ConfigError, match="field_name cannot be empty"):
            _require_non_empty_text("\n\t  \n", "field_name")


class TestNormalizeMetadata:
    """Test _normalize_metadata function."""

    def test_normalizes_dict_to_copy(self) -> None:
        original = {"key1": "value1", "key2": "value2"}
        result = _normalize_metadata(original)
        assert result == original
        assert result is not original

    def test_empty_dict_returns_empty_dict(self) -> None:
        result = _normalize_metadata({})
        assert result == {}

    def test_preserves_string_values(self) -> None:
        metadata = {"a": "1", "b": "2"}
        result = _normalize_metadata(metadata)
        assert result == metadata


class TestParseTimestamp:
    """Test _parse_timestamp function."""

    def test_parse_valid_iso_timestamp(self) -> None:
        result = _parse_timestamp("2026-01-01T10:00:00+00:00")
        assert result.tzinfo == UTC
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1

    def test_parse_naive_timestamp_converts_to_utc(self) -> None:
        result = _parse_timestamp("2026-01-01T10:00:00")
        assert result.tzinfo == UTC
        assert result.year == 2026

    def test_parse_invalid_format_raises(self) -> None:
        with pytest.raises(ConfigError, match="Invalid timestamp"):
            _parse_timestamp("not-a-timestamp")

    def test_parse_malformed_iso_raises(self) -> None:
        with pytest.raises(ConfigError, match="Invalid timestamp"):
            _parse_timestamp("2026-13-01T10:00:00")


class TestRecordToRow:
    """Test _record_to_row conversion."""

    def test_converts_record_to_tuple(self) -> None:
        record = _record("trade-1", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        row = _record_to_row(record)
        assert len(row) == 10
        assert row[0] == "trade-1"
        assert row[1] == "2026-01-01T10:00:00+00:00"
        assert row[2] == "NSE"
        assert row[3] == "RELIANCE"
        assert row[4] == "BUY"
        assert row[5] == "5"
        assert row[6] == "2500.50"
        assert row[7] == "FILLED"
        assert row[8] == "mom-1"
        assert json.loads(row[9]) == {"source": "unit-test"}

    def test_serializes_metadata_as_sorted_json(self) -> None:
        record = _record(
            "trade-1",
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            metadata={"z": "1", "a": "2"},
        )
        row = _record_to_row(record)
        metadata = json.loads(row[9])
        assert list(metadata.keys()) == ["a", "z"]


class TestRowToRecord:
    """Test _row_to_record conversion."""

    def test_converts_row_to_record(self) -> None:
        row = {
            "trade_id": "trade-1",
            "timestamp_utc": "2026-01-01T10:00:00+00:00",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "5",
            "price": "2500.50",
            "status": "FILLED",
            "strategy_id": "mom-1",
            "metadata_json": '{"source": "unit-test"}',
        }
        record = _row_to_record(row)
        assert record.trade_id == "trade-1"
        assert record.symbol == "RELIANCE"
        assert record.price == create_price("2500.50")
        assert record.metadata == {"source": "unit-test"}

    def test_parses_naive_timestamp_as_utc(self) -> None:
        row = {
            "trade_id": "trade-1",
            "timestamp_utc": "2026-01-01T10:00:00",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "5",
            "price": "2500.50",
            "status": "FILLED",
            "strategy_id": "mom-1",
            "metadata_json": "{}",
        }
        record = _row_to_record(row)
        assert record.timestamp.tzinfo == UTC

    def test_invalid_metadata_json_raises(self) -> None:
        row = {
            "trade_id": "trade-1",
            "timestamp_utc": "2026-01-01T10:00:00+00:00",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "5",
            "price": "2500.50",
            "status": "FILLED",
            "strategy_id": "mom-1",
            "metadata_json": "not-json",
        }
        with pytest.raises((ConfigError, json.JSONDecodeError)):
            _row_to_record(row)

    def test_non_dict_metadata_raises(self) -> None:
        row = {
            "trade_id": "trade-1",
            "timestamp_utc": "2026-01-01T10:00:00+00:00",
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "side": "BUY",
            "quantity": "5",
            "price": "2500.50",
            "status": "FILLED",
            "strategy_id": "mom-1",
            "metadata_json": "[]",
        }
        with pytest.raises(
            ConfigError, match="metadata_json must decode to dictionary"
        ):
            _row_to_record(row)


class TestTradeAuditRecord:
    """Test TradeAuditRecord dataclass."""

    def test_creates_valid_record(self) -> None:
        record = _record("trade-1", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        assert record.trade_id == "trade-1"
        assert record.symbol == "RELIANCE"
        assert record.strategy_id == "mom-1"

    def test_empty_trade_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="trade_id cannot be empty"):
            TradeAuditRecord(
                trade_id="",
                timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=create_quantity("5"),
                price=create_price("2500.50"),
                status=OrderStatus.FILLED,
                strategy_id="mom-1",
            )

    def test_whitespace_only_trade_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="trade_id cannot be empty"):
            TradeAuditRecord(
                trade_id="  ",
                timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=create_quantity("5"),
                price=create_price("2500.50"),
                status=OrderStatus.FILLED,
                strategy_id="mom-1",
            )

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            TradeAuditRecord(
                trade_id="trade-1",
                timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="",
                side=OrderSide.BUY,
                quantity=create_quantity("5"),
                price=create_price("2500.50"),
                status=OrderStatus.FILLED,
                strategy_id="mom-1",
            )

    def test_empty_strategy_id_raises(self) -> None:
        with pytest.raises(ConfigError, match="strategy_id cannot be empty"):
            TradeAuditRecord(
                trade_id="trade-1",
                timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                quantity=create_quantity("5"),
                price=create_price("2500.50"),
                status=OrderStatus.FILLED,
                strategy_id="",
            )

    def test_metadata_is_normalized_to_copy(self) -> None:
        original_metadata = {"key": "value"}
        record = TradeAuditRecord(
            trade_id="trade-1",
            timestamp=create_timestamp(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=create_quantity("5"),
            price=create_price("2500.50"),
            status=OrderStatus.FILLED,
            strategy_id="mom-1",
            metadata=original_metadata,
        )
        assert record.metadata == original_metadata
        assert record.metadata is not original_metadata

    def test_frozen_dataclass_is_immutable(self) -> None:
        record = _record("trade-1", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        with pytest.raises((AttributeError, TypeError)):
            record.trade_id = "new-id"


class TestBuildQuery:
    """Test SQLiteStore._build_query static method."""

    def test_build_query_with_conditions(self) -> None:
        conditions = ["exchange = ?", "symbol = ?"]
        query = SQLiteStore._build_query(conditions)
        assert "WHERE" in query
        assert "exchange = ?" in query
        assert "symbol = ?" in query
        assert "ORDER BY timestamp_utc DESC LIMIT ?" in query

    def test_build_query_without_conditions(self) -> None:
        query = SQLiteStore._build_query([])
        assert "WHERE" not in query
        assert "ORDER BY timestamp_utc DESC LIMIT ?" in query

    def test_build_query_single_condition(self) -> None:
        conditions = ["status = ?"]
        query = SQLiteStore._build_query(conditions)
        assert "WHERE status = ?" in query


class TestBuildFilterConditions:
    """Test SQLiteStore._build_filter_conditions static method."""

    def test_build_all_filter_conditions(self) -> None:
        conditions: list[str] = []
        params: list[object] = []
        SQLiteStore._build_filter_conditions(
            conditions,
            params,
            start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            strategy_id="strat-1",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
        )
        assert len(conditions) == 7
        assert len(params) == 7
        assert "timestamp_utc >= ?" in conditions
        assert "timestamp_utc <= ?" in conditions
        assert "exchange = ?" in conditions
        assert "symbol = ?" in conditions
        assert "strategy_id = ?" in conditions
        assert "side = ?" in conditions
        assert "status = ?" in conditions

    def test_build_no_filter_conditions(self) -> None:
        conditions: list[str] = []
        params: list[object] = []
        SQLiteStore._build_filter_conditions(
            conditions,
            params,
            start_time=None,
            end_time=None,
            exchange=None,
            symbol=None,
            strategy_id=None,
            side=None,
            status=None,
        )
        assert len(conditions) == 0
        assert len(params) == 0

    def test_build_partial_filter_conditions(self) -> None:
        conditions: list[str] = []
        params: list[object] = []
        SQLiteStore._build_filter_conditions(
            conditions,
            params,
            start_time=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            end_time=None,
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            strategy_id=None,
            side=None,
            status=None,
        )
        assert len(conditions) == 3
        assert len(params) == 3


class TestSQLiteStoreInit:
    """Test SQLiteStore initialization."""

    def test_init_with_positive_retention_years(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=5)
        assert store._retention_years == 5

    def test_init_with_default_retention_years(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        assert store._retention_years == 7

    def test_init_with_zero_retention_years_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="retention_years must be positive"):
            SQLiteStore(tmp_path / "audit.sqlite3", retention_years=0)

    def test_init_with_negative_retention_years_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="retention_years must be positive"):
            SQLiteStore(tmp_path / "audit.sqlite3", retention_years=-1)


class TestSQLiteStoreConnect:
    """Test SQLiteStore._connect method."""

    def test_connect_returns_connection_with_row_factory(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        conn = store._connect()
        assert conn.row_factory is not None
        conn.close()

    def test_connect_enables_wal_mode(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        conn = store._connect()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row is not None
        assert row[0].upper() == "WAL"
        conn.close()


class TestSQLiteStoreInitialize:
    """Test SQLiteStore.initialize method."""

    def test_initialize_creates_parent_directory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "audit.sqlite3"
        store = SQLiteStore(db_path)
        store.initialize()
        assert db_path.parent.exists()

    def test_initialize_creates_schema(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        store.initialize()
        with store._connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "trade_audit_log" in table_names

    def test_initialize_creates_indexes(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        store.initialize()
        with store._connect() as conn:
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = [i[0] for i in indexes]
            assert "idx_trade_audit_timestamp" in index_names
            assert "idx_trade_audit_exchange" in index_names
            assert "idx_trade_audit_symbol" in index_names
            assert "idx_trade_audit_strategy" in index_names

    def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        store.initialize()
        store.initialize()
        with store._connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert len(tables) == 1


class TestSQLiteStoreAppendTrade:
    """Test SQLiteStore.append_trade method."""

    def test_append_trade_persists_record(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        record = _record("trade-1", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        store.append_trade(record)
        loaded = store.get_trade("trade-1")
        assert loaded is not None
        assert loaded.trade_id == "trade-1"

    def test_append_duplicate_trade_id_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        record = _record("trade-1", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
        store.append_trade(record)
        with pytest.raises(ConfigError, match="trade_id already exists"):
            store.append_trade(record)

    def test_append_trade_with_metadata(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        record = _record(
            "trade-1",
            datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            metadata={"key1": "value1", "key2": "value2"},
        )
        store.append_trade(record)
        loaded = store.get_trade("trade-1")
        assert loaded is not None
        assert loaded.metadata == {"key1": "value1", "key2": "value2"}


class TestSQLiteStoreGetTrade:
    """Test SQLiteStore.get_trade method."""

    def test_get_trade_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        result = store.get_trade("nonexistent")
        assert result is None

    def test_get_trade_with_empty_string_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="trade_id cannot be empty"):
            store.get_trade("")

    def test_get_trade_with_whitespace_only_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="trade_id cannot be empty"):
            store.get_trade("  ")


class TestSQLiteStoreListTrades:
    """Test SQLiteStore.list_trades method."""

    def test_list_trades_returns_empty_when_no_trades(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        trades = store.list_trades()
        assert trades == []

    def test_list_trades_orders_by_timestamp_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base))
        store.append_trade(_record("trade-2", base + timedelta(minutes=1)))
        store.append_trade(_record("trade-3", base + timedelta(minutes=2)))
        trades = store.list_trades()
        assert [t.trade_id for t in trades] == ["trade-3", "trade-2", "trade-1"]

    def test_list_trades_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(10):
            store.append_trade(_record(f"trade-{i}", base + timedelta(minutes=i)))
        trades = store.list_trades(limit=5)
        assert len(trades) == 5

    def test_list_trades_with_zero_limit_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades(limit=0)

    def test_list_trades_with_negative_limit_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades(limit=-1)


class TestSQLiteStoreListTradesByRange:
    """Test SQLiteStore.list_trades_by_range method."""

    def test_list_trades_by_range_inclusive_bounds(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base))
        store.append_trade(_record("trade-2", base + timedelta(hours=1)))
        store.append_trade(_record("trade-3", base + timedelta(hours=2)))
        trades = store.list_trades_by_range(
            start_utc=base,
            end_utc=base + timedelta(hours=2),
        )
        assert len(trades) == 3
        assert {t.trade_id for t in trades} == {"trade-1", "trade-2", "trade-3"}

    def test_list_trades_by_range_orders_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base))
        store.append_trade(_record("trade-2", base + timedelta(hours=1)))
        trades = store.list_trades_by_range(
            start_utc=base,
            end_utc=base + timedelta(hours=2),
        )
        assert trades[0].timestamp >= trades[1].timestamp

    def test_list_trades_by_range_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(10):
            store.append_trade(_record(f"trade-{i}", base + timedelta(hours=i)))
        trades = store.list_trades_by_range(
            start_utc=base,
            end_utc=base + timedelta(days=1),
            limit=5,
        )
        assert len(trades) == 5

    def test_list_trades_by_range_with_zero_limit_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades_by_range(
                start_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
                end_utc=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
                limit=0,
            )


class TestSQLiteStoreListTradesBySymbol:
    """Test SQLiteStore.list_trades_by_symbol method."""

    def test_list_trades_by_symbol_with_empty_string_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            store.list_trades_by_symbol("")

    def test_list_trades_by_symbol_with_whitespace_only_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="symbol cannot be empty"):
            store.list_trades_by_symbol("  ")

    def test_list_trades_by_symbol_without_exchange(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(
            _record("trade-1", base, exchange=Exchange.NSE, symbol="RELIANCE")
        )
        store.append_trade(
            _record("trade-2", base, exchange=Exchange.BSE, symbol="RELIANCE")
        )
        trades = store.list_trades_by_symbol("RELIANCE")
        assert len(trades) == 2

    def test_list_trades_by_symbol_with_exchange(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(
            _record("trade-1", base, exchange=Exchange.NSE, symbol="RELIANCE")
        )
        store.append_trade(
            _record("trade-2", base, exchange=Exchange.BSE, symbol="RELIANCE")
        )
        trades = store.list_trades_by_symbol("RELIANCE", exchange=Exchange.NSE)
        assert len(trades) == 1
        assert trades[0].exchange == Exchange.NSE

    def test_list_trades_by_symbol_orders_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, symbol="RELIANCE"))
        store.append_trade(
            _record("trade-2", base + timedelta(minutes=1), symbol="RELIANCE")
        )
        trades = store.list_trades_by_symbol("RELIANCE")
        assert trades[0].timestamp >= trades[1].timestamp

    def test_list_trades_by_symbol_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(10):
            store.append_trade(
                _record(f"trade-{i}", base + timedelta(minutes=i), symbol="RELIANCE")
            )
        trades = store.list_trades_by_symbol("RELIANCE", limit=5)
        assert len(trades) == 5

    def test_list_trades_by_symbol_with_zero_limit_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades_by_symbol("RELIANCE", limit=0)


class TestSQLiteStoreListTradesByStrategy:
    """Test SQLiteStore.list_trades_by_strategy method."""

    def test_list_trades_by_strategy_with_empty_string_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="strategy_id cannot be empty"):
            store.list_trades_by_strategy("")

    def test_list_trades_by_strategy_with_whitespace_only_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="strategy_id cannot be empty"):
            store.list_trades_by_strategy("  ")

    def test_list_trades_by_strategy_filters_correctly(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, strategy_id="strat-a"))
        store.append_trade(_record("trade-2", base, strategy_id="strat-b"))
        store.append_trade(_record("trade-3", base, strategy_id="strat-a"))
        trades = store.list_trades_by_strategy("strat-a")
        assert len(trades) == 2
        assert all(t.strategy_id == "strat-a" for t in trades)

    def test_list_trades_by_strategy_orders_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, strategy_id="strat-a"))
        store.append_trade(
            _record("trade-2", base + timedelta(minutes=1), strategy_id="strat-a")
        )
        trades = store.list_trades_by_strategy("strat-a")
        assert trades[0].timestamp >= trades[1].timestamp

    def test_list_trades_by_strategy_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(10):
            store.append_trade(
                _record(
                    f"trade-{i}", base + timedelta(minutes=i), strategy_id="strat-a"
                )
            )
        trades = store.list_trades_by_strategy("strat-a", limit=5)
        assert len(trades) == 5

    def test_list_trades_by_strategy_with_zero_limit_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.list_trades_by_strategy("strat-a", limit=0)


class TestSQLiteStoreAppendTradesBatch:
    """Test SQLiteStore.append_trades_batch method."""

    def test_append_trades_batch_empty_list_no_op(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        store.append_trades_batch([])
        assert store.list_trades() == []

    def test_append_trades_batch_single_record(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        records = [_record("trade-1", base)]
        store.append_trades_batch(records)
        assert store.get_trade("trade-1") is not None

    def test_append_trades_batch_multiple_records(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        records = [
            _record(f"trade-{i}", base + timedelta(minutes=i)) for i in range(10)
        ]
        store.append_trades_batch(records)
        for i in range(10):
            assert store.get_trade(f"trade-{i}") is not None

    def test_append_trades_batch_duplicate_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        records = [
            _record("trade-1", base),
            _record("trade-1", base + timedelta(minutes=1)),
        ]
        with pytest.raises(ConfigError, match="Batch insert conflict"):
            store.append_trades_batch(records)

    def test_append_trades_batch_preserves_metadata(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        records = [
            _record("trade-1", base, metadata={"key": "value1"}),
            _record("trade-2", base, metadata={"key": "value2"}),
        ]
        store.append_trades_batch(records)
        loaded1 = store.get_trade("trade-1")
        loaded2 = store.get_trade("trade-2")
        assert loaded1 is not None
        assert loaded2 is not None
        assert loaded1.metadata == {"key": "value1"}
        assert loaded2.metadata == {"key": "value2"}


class TestSQLiteStoreQueryTrades:
    """Test SQLiteStore.query_trades method."""

    def test_query_trades_no_filters(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(5):
            store.append_trade(_record(f"trade-{i}", base + timedelta(minutes=i)))
        trades = store.query_trades()
        assert len(trades) == 5

    def test_query_trades_all_filters(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(
            _record(
                "trade-1",
                base,
                exchange=Exchange.NSE,
                symbol="RELIANCE",
                side=OrderSide.BUY,
                status=OrderStatus.FILLED,
                strategy_id="strat-a",
            )
        )
        store.append_trade(
            _record(
                "trade-2",
                base + timedelta(minutes=1),
                exchange=Exchange.BSE,
                symbol="TCS",
                side=OrderSide.SELL,
                status=OrderStatus.PARTIALLY_FILLED,
                strategy_id="strat-b",
            )
        )
        trades = store.query_trades(
            start_time=base,
            end_time=base + timedelta(hours=1),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            status=OrderStatus.FILLED,
            strategy_id="strat-a",
        )
        assert len(trades) == 1
        assert trades[0].trade_id == "trade-1"

    def test_query_trades_orders_desc(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(5):
            store.append_trade(_record(f"trade-{i}", base + timedelta(minutes=i)))
        trades = store.query_trades()
        assert trades[0].timestamp >= trades[1].timestamp

    def test_query_trades_respects_limit(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(10):
            store.append_trade(_record(f"trade-{i}", base + timedelta(minutes=i)))
        trades = store.query_trades(limit=5)
        assert len(trades) == 5

    def test_query_trades_with_zero_limit_raises(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.query_trades(limit=0)

    def test_query_trades_start_time_only(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(5):
            store.append_trade(_record(f"trade-{i}", base + timedelta(hours=i)))
        start = base + timedelta(hours=2)
        trades = store.query_trades(start_time=start)
        assert all(t.timestamp >= start for t in trades)

    def test_query_trades_end_time_only(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        for i in range(5):
            store.append_trade(_record(f"trade-{i}", base + timedelta(hours=i)))
        end = base + timedelta(hours=2)
        trades = store.query_trades(end_time=end)
        assert all(t.timestamp <= end for t in trades)

    def test_query_trades_exchange_filter(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, exchange=Exchange.NSE))
        store.append_trade(_record("trade-2", base, exchange=Exchange.BSE))
        trades = store.query_trades(exchange=Exchange.NSE)
        assert len(trades) == 1
        assert trades[0].exchange == Exchange.NSE

    def test_query_trades_symbol_filter(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, symbol="RELIANCE"))
        store.append_trade(_record("trade-2", base, symbol="TCS"))
        trades = store.query_trades(symbol="RELIANCE")
        assert len(trades) == 1
        assert trades[0].symbol == "RELIANCE"

    def test_query_trades_strategy_id_filter(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, strategy_id="strat-a"))
        store.append_trade(_record("trade-2", base, strategy_id="strat-b"))
        trades = store.query_trades(strategy_id="strat-a")
        assert len(trades) == 1
        assert trades[0].strategy_id == "strat-a"

    def test_query_trades_side_filter(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, side=OrderSide.BUY))
        store.append_trade(_record("trade-2", base, side=OrderSide.SELL))
        trades = store.query_trades(side=OrderSide.BUY)
        assert len(trades) == 1
        assert trades[0].side == OrderSide.BUY

    def test_query_trades_status_filter(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base, status=OrderStatus.FILLED))
        store.append_trade(
            _record("trade-2", base, status=OrderStatus.PARTIALLY_FILLED)
        )
        trades = store.query_trades(status=OrderStatus.FILLED)
        assert len(trades) == 1
        assert trades[0].status == OrderStatus.FILLED

    def test_query_trades_no_matches_returns_empty(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base))
        trades = store.query_trades(symbol="NONEXISTENT")
        assert trades == []


class TestSQLiteStorePurgeExpired:
    """Test SQLiteStore.purge_expired method."""

    def test_purge_expired_with_default_reference_time(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        old_time = base - timedelta(days=400)
        store.append_trade(_record("old-trade", old_time))
        store.append_trade(_record("new-trade", base))
        deleted = store.purge_expired()
        assert deleted == 1
        assert store.get_trade("old-trade") is None
        assert store.get_trade("new-trade") is not None

    def test_purge_expired_with_custom_reference_time(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        old_time = base - timedelta(days=400)
        store.append_trade(_record("old-trade", old_time))
        store.append_trade(_record("new-trade", base))
        reference = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        deleted = store.purge_expired(reference_time=reference)
        assert deleted == 1

    def test_purge_expired_with_naive_reference_time_raises(
        self, tmp_path: Path
    ) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3")
        with pytest.raises(ConfigError, match="reference_time must be timezone-aware"):
            store.purge_expired(reference_time=datetime(2026, 1, 1, 10, 0))  # noqa: DTZ001

    def test_purge_expired_with_non_utc_timezone(self, tmp_path: Path) -> None:
        from datetime import timezone

        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        base = datetime(
            2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        )
        base_utc = base.astimezone(UTC)
        old_time = base_utc - timedelta(days=400)
        store.append_trade(_record("old-trade", old_time))
        store.append_trade(_record("new-trade", base_utc))
        deleted = store.purge_expired(reference_time=base)
        assert deleted == 1

    def test_purge_expired_no_expired_records(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        store.append_trade(_record("trade-1", base))
        deleted = store.purge_expired(reference_time=base)
        assert deleted == 0

    def test_purge_expired_all_records_expired(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=1)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        old_time = base - timedelta(days=400)
        for i in range(5):
            store.append_trade(_record(f"trade-{i}", old_time + timedelta(days=i)))
        deleted = store.purge_expired(reference_time=base)
        assert deleted == 5

    def test_purge_expired_respects_retention_years(self, tmp_path: Path) -> None:
        store = SQLiteStore(tmp_path / "audit.sqlite3", retention_years=2)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        old_time = base - timedelta(days=400)
        store.append_trade(_record("old-trade", old_time))
        store.append_trade(_record("new-trade", base))
        deleted = store.purge_expired(reference_time=base)
        assert deleted == 0
        assert store.get_trade("old-trade") is not None
        assert store.get_trade("new-trade") is not None
