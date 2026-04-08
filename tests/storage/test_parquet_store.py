"""
Tests for parquet archival storage.
"""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.storage.parquet_store import ParquetStore

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
        symbol="BANKNIFTY",
        open=create_price("100"),
        high=create_price("101"),
        low=create_price("99"),
        close=create_price("100.5"),
        volume=create_quantity("1500"),
        source="unit-test",
    )


class _FakeTable:
    def __init__(self, data: dict[str, list[Any]]) -> None:
        self._data = data

    def to_pydict(self) -> dict[str, list[Any]]:
        return self._data


class _FakePyArrow:
    @staticmethod
    def table(data: dict[str, list[Any]]) -> _FakeTable:
        return _FakeTable(data)


class _FakeParquet:
    def __init__(self) -> None:
        self._storage: dict[str, dict[str, list[Any]]] = {}

    def write_table(self, table: _FakeTable, file_path: Path) -> None:
        self._storage[str(file_path)] = table.to_pydict()
        file_path.write_text("parquet-placeholder", encoding="utf-8")

    def read_table(self, file_path: Path) -> _FakeTable:
        return _FakeTable(self._storage[str(file_path)])


class TestParquetStore:
    """Test parquet archival behavior using fake pyarrow module."""

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]
        file_path = store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[_bar(0), _bar(1)],
        )
        loaded = store.read_bars(file_path)
        assert len(loaded) == 2
        assert loaded[0].symbol == "BANKNIFTY"
        assert loaded[1].timestamp.minute == 16

    def test_list_parquet_files_sorted(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]
        file_b = store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[_bar(1), _bar(2)],
        )
        file_a = store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[_bar(0), _bar(1)],
        )
        listed = store.list_parquet_files(symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m")
        assert listed == sorted([file_a, file_b])

    def test_write_bars_rejects_empty_input(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        with pytest.raises(ConfigError, match="bars cannot be empty"):
            store.write_bars(symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[])

    def test_read_bars_rejects_missing_file(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        with pytest.raises(ConfigError, match="does not exist"):
            store.read_bars(tmp_path / "archive" / "missing.parquet")

    def test_missing_pyarrow_dependency_raises(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = ParquetStore(tmp_path / "archive")
        monkeypatch.setattr(
            "iatb.storage.parquet_store.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="pyarrow dependency"):
            store._import_pyarrow()
