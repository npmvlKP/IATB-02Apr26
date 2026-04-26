"""Comprehensive tests for trade_audit.py module."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.execution.base import ExecutionResult, OrderRequest
from iatb.execution.trade_audit import TradeAuditEntry, TradeAuditLogger, _record_to_entry
from iatb.storage.sqlite_store import TradeAuditRecord


def _make_request(
    symbol: str = "NIFTY",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
) -> OrderRequest:
    return OrderRequest(
        exchange=Exchange.NSE,
        symbol=symbol,
        side=side,
        quantity=quantity,
    )


def _make_result(
    order_id: str = "OID-1",
    status: OrderStatus = OrderStatus.FILLED,
    filled_quantity: Decimal = Decimal("10"),
    average_price: Decimal = Decimal("100.50"),
) -> ExecutionResult:
    return ExecutionResult(order_id, status, filled_quantity, average_price, "test fill")


class TestRecordToEntry:
    def test_converts_record_to_entry(self) -> None:
        ts = create_timestamp(datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC))
        record = TradeAuditRecord(
            trade_id="OID-1",
            timestamp=ts,
            exchange=Exchange.NSE,
            symbol="NIFTY",
            side=OrderSide.BUY,
            quantity=create_quantity("10"),
            price=create_price("100.50"),
            status=OrderStatus.FILLED,
            strategy_id="STRAT-1",
            metadata={"algo_id": "ALG-101"},
        )
        entry = _record_to_entry(record)
        assert isinstance(entry, TradeAuditEntry)
        assert entry.order_id == "OID-1"
        assert entry.symbol == "NIFTY"
        assert entry.exchange == "NSE"
        assert entry.side == "BUY"
        assert entry.quantity == Decimal("10")
        assert entry.price == Decimal("100.50")
        assert entry.status == "FILLED"
        assert entry.strategy_id == "STRAT-1"
        assert entry.algo_id == "ALG-101"
        assert entry.timestamp_utc.tzinfo == UTC

    def test_missing_algo_id_in_metadata(self) -> None:
        ts = create_timestamp(datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC))
        record = TradeAuditRecord(
            trade_id="OID-2",
            timestamp=ts,
            exchange=Exchange.BSE,
            symbol="RELIANCE",
            side=OrderSide.SELL,
            quantity=create_quantity("5"),
            price=create_price("2500.00"),
            status=OrderStatus.PARTIALLY_FILLED,
            strategy_id="STRAT-2",
            metadata={},
        )
        entry = _record_to_entry(record)
        assert entry.algo_id == ""

    def test_sell_order_conversion(self) -> None:
        ts = create_timestamp(datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC))
        record = TradeAuditRecord(
            trade_id="OID-3",
            timestamp=ts,
            exchange=Exchange.MCX,
            symbol="CRUDEOIL",
            side=OrderSide.SELL,
            quantity=create_quantity("1"),
            price=create_price("6500.00"),
            status=OrderStatus.REJECTED,
            strategy_id="STRAT-3",
            metadata={"algo_id": "ALG-301"},
        )
        entry = _record_to_entry(record)
        assert entry.side == "SELL"
        assert entry.status == "REJECTED"
        assert entry.exchange == "MCX"


class TestTradeAuditEntry:
    def test_entry_is_frozen_dataclass(self) -> None:
        entry = TradeAuditEntry(
            timestamp_utc=datetime(2026, 4, 26, 10, 0, 0, tzinfo=UTC),
            order_id="OID-1",
            symbol="NIFTY",
            exchange="NSE",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100.50"),
            status="FILLED",
            strategy_id="STRAT-1",
            algo_id="ALG-101",
        )
        assert entry.order_id == "OID-1"
        with pytest.raises(AttributeError):
            entry.order_id = "NEW"  # type: ignore[misc]


class TestTradeAuditLogger:
    def test_log_order_creates_record(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        request = _make_request()
        result = _make_result()
        logger.log_order(request, result, "STRAT-1", "ALG-101")

    def test_log_order_with_empty_strategy_id(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        request = _make_request()
        result = _make_result()
        from iatb.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="strategy_id cannot be empty"):
            logger.log_order(request, result, "", "")

    def test_query_daily_trades(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        request = _make_request()
        result = _make_result(order_id="OID-DAY1")
        logger.log_order(request, result, "STRAT-1", "ALG-101")

        trades = logger.query_daily_trades(datetime.now(UTC).date())
        assert len(trades) >= 1
        assert trades[0].order_id == "OID-DAY1"

    def test_query_daily_trades_no_trades(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        trades = logger.query_daily_trades(date(2020, 1, 1))
        assert len(trades) == 0

    def test_query_daily_trades_multiple_records(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        for i in range(5):
            request = _make_request()
            result = _make_result(order_id=f"OID-{i}")
            logger.log_order(request, result, "STRAT-1", "ALG-101")

        trades = logger.query_daily_trades(datetime.now(UTC).date())
        assert len(trades) == 5

    def test_query_daily_trades_sell_order(self, tmp_path: Path) -> None:
        logger = TradeAuditLogger(tmp_path / "audit.db")
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.SELL,
            quantity=Decimal("5"),
        )
        result = ExecutionResult(
            "OID-SELL", OrderStatus.FILLED, Decimal("5"), Decimal("2500"), "sell"
        )
        logger.log_order(request, result, "STRAT-2", "ALG-202")

        trades = logger.query_daily_trades(datetime.now(UTC).date())
        assert len(trades) == 1
        assert trades[0].side == "SELL"
        assert trades[0].symbol == "RELIANCE"

    def test_initializes_database(self, tmp_path: Path) -> None:
        db_file = tmp_path / "audit_init.db"
        TradeAuditLogger(db_file)
        assert db_file.exists()
