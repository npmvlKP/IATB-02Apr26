"""
Tests for DuckDB OHLCV storage.
"""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.storage.duckdb_store import DuckDBStore

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def _bar(minute_offset: int) -> OHLCVBar:
    return OHLCVBar(
        timestamp=create_timestamp(
            datetime(2026, 1, 1, 9, 15, tzinfo=UTC) + timedelta(minutes=minute_offset)
        ),
        exchange=Exchange.NSE,
        symbol="NIFTY",
        open=create_price("100"),
        high=create_price("101"),
        low=create_price("99"),
        close=create_price("100.5"),
        volume=create_quantity("1500"),
        source="unit-test",
    )


class _FakeDuckDBConnection:
    def __init__(self) -> None:
        self.rows: list[tuple[str, ...]] = []
        self._result: list[tuple[object, ...]] = []

    def execute(
        self,
        query: str,
        params: tuple[object, ...] | list[object] | None = None,
    ) -> "_FakeDuckDBConnection":
        args = tuple(params or ())
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("delete from ohlcv_bars"):
            self.rows = [
                row
                for row in self.rows
                if not (
                    row[0] == args[0]
                    and row[1] == args[1]
                    and row[2] == args[2]
                    and row[8] == args[3]
                )
            ]
        elif normalized.startswith("insert into ohlcv_bars"):
            self.rows.append(tuple(str(value) for value in args))
        elif normalized.startswith("select exchange"):
            self._result = self._select_rows(args)
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._result)

    def close(self) -> None:
        return

    def _select_rows(self, args: tuple[object, ...]) -> list[tuple[object, ...]]:
        symbol = str(args[0])
        exchange = str(args[1])
        start = str(args[2]) if len(args) > 3 else None
        end = str(args[3]) if len(args) > 4 else None
        limit = int(args[-1])
        filtered = [row for row in self.rows if row[1] == symbol and row[0] == exchange]
        if start is not None:
            filtered = [row for row in filtered if row[2] >= start]
        if end is not None:
            filtered = [row for row in filtered if row[2] <= end]
        return [tuple(row) for row in sorted(filtered, key=lambda row: row[2])[:limit]]


class _FakeDuckDBModule:
    def __init__(self, connection: _FakeDuckDBConnection) -> None:
        self._connection = connection

    def connect(self, _: str) -> _FakeDuckDBConnection:
        return self._connection


class TestDuckDBStore:
    """Test DuckDBStore behavior using in-memory fake module."""

    def test_store_and_load_bars_roundtrip(self, tmp_path: Path) -> None:
        connection = _FakeDuckDBConnection()
        store = DuckDBStore(tmp_path / "market.duckdb")
        store._import_duckdb = lambda: _FakeDuckDBModule(connection)  # type: ignore[method-assign]
        bars = [_bar(0), _bar(1)]
        store.store_bars(bars)
        loaded = store.load_bars(symbol="NIFTY", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 2
        assert loaded[0].timestamp < loaded[1].timestamp

    def test_load_bars_applies_start_end_filters(self, tmp_path: Path) -> None:
        connection = _FakeDuckDBConnection()
        store = DuckDBStore(tmp_path / "market.duckdb")
        store._import_duckdb = lambda: _FakeDuckDBModule(connection)  # type: ignore[method-assign]
        store.store_bars([_bar(0), _bar(1), _bar(2)])
        loaded = store.load_bars(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            start=create_timestamp(datetime(2026, 1, 1, 9, 16, tzinfo=UTC)),
            end=create_timestamp(datetime(2026, 1, 1, 9, 17, tzinfo=UTC)),
            limit=10,
        )
        assert [bar.timestamp.minute for bar in loaded] == [16, 17]

    def test_store_empty_batch_is_noop(self, tmp_path: Path) -> None:
        connection = _FakeDuckDBConnection()
        store = DuckDBStore(tmp_path / "market.duckdb")
        store._import_duckdb = lambda: _FakeDuckDBModule(connection)  # type: ignore[method-assign]
        store.store_bars([])
        assert connection.rows == []

    def test_load_bars_rejects_non_positive_limit(self, tmp_path: Path) -> None:
        store = DuckDBStore(tmp_path / "market.duckdb")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.load_bars(symbol="NIFTY", exchange=Exchange.NSE, limit=0)

    def test_missing_duckdb_dependency_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = DuckDBStore(tmp_path / "market.duckdb")
        monkeypatch.setattr(
            "iatb.storage.duckdb_store.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="duckdb dependency"):
            store._import_duckdb()
