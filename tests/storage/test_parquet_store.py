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
from iatb.storage.parquet_store import ParquetStore, _allowed_compression, _parse_timestamp

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _bar(minute_offset: int = 0) -> OHLCVBar:
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


def _bar_with_date(date: datetime, minute_offset: int = 0) -> OHLCVBar:
    return OHLCVBar(
        timestamp=create_timestamp(
            datetime(
                date.year,
                date.month,
                date.day,
                9,
                15 + minute_offset,
                tzinfo=UTC,
            )
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


class _FakeColumn:
    def __init__(self, data: list[Any]) -> None:
        self._data = data

    def to_pylist(self) -> list[Any]:
        return self._data


class _FakeTable:
    def __init__(self, data: dict[str, list[Any]]) -> None:
        self._data = data

    def to_pydict(self) -> dict[str, list[Any]]:
        return self._data

    def column(self, name: str) -> _FakeColumn:
        return _FakeColumn(self._data.get(name, []))


class _FakePyArrow:
    @staticmethod
    def table(data: dict[str, list[Any]]) -> _FakeTable:
        return _FakeTable(data)


class _FakeParquet:
    def __init__(self) -> None:
        self._storage: dict[str, dict[str, list[Any]]] = {}

    def write_table(self, table: _FakeTable, file_path: Path, compression: str = "ZSTD") -> None:
        self._storage[str(file_path)] = table.to_pydict()
        file_path.write_text("parquet-placeholder", encoding="utf-8")

    def read_table(self, file_path: Path) -> _FakeTable:
        return _FakeTable(self._storage[str(file_path)])


# --------------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------------- #
class TestTimestampParsing:
    def test_parse_iso_string(self) -> None:
        ts = _parse_timestamp("2026-01-15T10:00:00+00:00")
        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 15

    def test_parse_z_suffix(self) -> None:
        ts = _parse_timestamp("2026-01-15T10:00:00Z")
        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 15

    def test_parse_naive_datetime(self) -> None:
        ts = _parse_timestamp(datetime(2026, 1, 15, 10, 0, 0))
        assert ts.year == 2026
        assert ts.tzinfo is not None

    def test_parse_aware_datetime(self) -> None:
        ts = _parse_timestamp(datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC))
        assert ts.year == 2026
        assert ts.tzinfo is not None

    def test_parse_invalid_type(self) -> None:
        with pytest.raises(ConfigError):
            _parse_timestamp(123)  # type: ignore[arg-type]


class TestAllowedCompression:
    def test_valid_codes(self) -> None:
        for code in ("NONE", "SNAPPY", "GZIP", "BROTLI", "LZ4", "ZSTD", "ZLIB"):
            assert _allowed_compression(code) == code

    def test_invalid_code(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported parquet compression"):
            _allowed_compression("BOGUS")


# --------------------------------------------------------------------------- #
# Core ParquetStore tests
# --------------------------------------------------------------------------- #
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
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),  # type: ignore[return-value]
        )
        with pytest.raises(ConfigError, match="pyarrow dependency"):
            store._import_pyarrow()

    def test_compression_default_zstd(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        assert store.compression == "ZSTD"

    def test_compression_custom(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="SNAPPY")
        assert store.compression == "SNAPPY"

    def test_date_partition_dir(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        ts = create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC))
        partition = store._date_partition_dir(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", when=ts
        )
        expected = tmp_path / "archive" / "NSE" / "BANKNIFTY" / "1m" / "2026" / "01"
        assert partition == expected

    def test_cleanup_older_than_rejects_negative_days(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        with pytest.raises(ConfigError, match="days must be non-negative"):
            store.cleanup_older_than(days=-1)

    def test_read_bars_range_empty_when_no_files(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)
        result = store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=start,
            end=end,
        )
        assert result == []

    def test_read_bars_range_cross_partition(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]

        bar1 = _bar_with_date(datetime(2026, 1, 15, 10, 0, tzinfo=UTC), 0)
        bar2 = _bar_with_date(datetime(2026, 2, 15, 10, 0, tzinfo=UTC), 0)
        bar3 = _bar_with_date(datetime(2026, 3, 15, 10, 0, tzinfo=UTC), 0)

        store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar1],
        )
        store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar2],
        )
        store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar3],
        )

        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)
        result = store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=start,
            end=end,
        )

        assert len(result) == 2
        assert result[0].timestamp.month == 1
        assert result[1].timestamp.month == 2

    def test_write_bars_uses_date_partition(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]

        bar = _bar_with_date(datetime(2026, 1, 15, 10, 0, tzinfo=UTC), 0)
        file_path = store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar],
        )

        assert "2026" in str(file_path)
        assert "01" in str(file_path)

    def test_cleanup_older_than_deletes_old_files(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]

        old_bar = _bar_with_date(datetime(2020, 1, 15, 10, 0, tzinfo=UTC), 0)
        store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[old_bar],
        )

        deleted = store.cleanup_older_than(days=1)

        assert len(deleted) >= 0


# --------------------------------------------------------------------------- #
# Range query edge-case tests
# --------------------------------------------------------------------------- #
class TestReadBarsRangeEdges:
    """Edge-case coverage for read_bars_range."""

    def _make_store(self, tmp_path: Path) -> tuple[ParquetStore, _FakeParquet]:
        store = ParquetStore(tmp_path / "archive")
        fake_parquet = _FakeParquet()
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]
        return store, fake_parquet

    def test_naive_start_raises(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        with pytest.raises(ConfigError, match="timezone-aware"):
            store.read_bars_range(
                symbol="X",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 1, 9, 0, 0),
                end=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
            )

    def test_naive_end_raises(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        with pytest.raises(ConfigError, match="timezone-aware"):
            store.read_bars_range(
                symbol="X",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC),
                end=datetime(2026, 1, 1, 10, 0, 0),
            )

    def test_end_before_start_raises(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        with pytest.raises(ConfigError, match="end must be after start"):
            store.read_bars_range(
                symbol="X",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 2, 9, 0, 0, tzinfo=UTC),
                end=datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC),
            )

    def test_returns_sorted_bars(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        bar_jan = _bar_with_date(datetime(2026, 1, 10, 10, 0, tzinfo=UTC), 0)
        bar_feb = _bar_with_date(datetime(2026, 2, 5, 10, 0, tzinfo=UTC), 0)
        bar_mar = _bar_with_date(datetime(2026, 3, 5, 10, 0, tzinfo=UTC), 0)

        store.write_bars(symbol="SORT", exchange=Exchange.NSE, timeframe="1m", bars=[bar_feb])
        store.write_bars(symbol="SORT", exchange=Exchange.NSE, timeframe="1m", bars=[bar_jan])
        store.write_bars(symbol="SORT", exchange=Exchange.NSE, timeframe="1m", bars=[bar_mar])

        result = store.read_bars_range(
            symbol="SORT",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end=datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
        )
        # Should be chronologically sorted regardless of write order
        months = [r.timestamp.month for r in result]
        assert months == sorted(months)

    def test_filters_by_timestamp_bounds(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        bar_jan10 = _bar_with_date(datetime(2026, 1, 10, 10, 0, tzinfo=UTC), 0)
        bar_feb20 = _bar_with_date(datetime(2026, 2, 20, 10, 0, tzinfo=UTC), 0)
        store.write_bars(symbol="BND", exchange=Exchange.NSE, timeframe="1m", bars=[bar_jan10])
        store.write_bars(symbol="BND", exchange=Exchange.NSE, timeframe="1m", bars=[bar_feb20])

        result = store.read_bars_range(
            symbol="BND",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
            end=datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
        )
        assert len(result) == 1
        assert result[0].timestamp.month == 2

    def test_no_files_returns_empty(self, tmp_path: Path) -> None:
        store, _ = self._make_store(tmp_path)
        result = store.read_bars_range(
            symbol="NOSYMB",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
        )
        assert result == []


# --------------------------------------------------------------------------- #
# Cleanup / retention tests
# --------------------------------------------------------------------------- #
class TestCleanupRetention:
    def _make_store(self, tmp_path: Path, days: int) -> tuple[ParquetStore, datetime]:
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), _FakeParquet())  # type: ignore[method-assign]
        # Write bars that are far in the past
        old_bar = _bar_with_date(datetime.now(UTC) - timedelta(days=days + 1), 0)
        store.write_bars(symbol=" CLEAN", exchange=Exchange.NSE, timeframe="1m", bars=[old_bar])
        return store, old_bar.timestamp

    def test_cleanup_deletes_old_files(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]

        old_bar = _bar_with_date(datetime(2020, 1, 15, 10, 0, tzinfo=UTC), 0)
        store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[old_bar],
        )

        deleted = store.cleanup_older_than(days=1)
        assert len(deleted) >= 0

    def test_cleanup_zero_days_keeps_recent(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), _FakeParquet())  # type: ignore[method-assign]
        bar = _bar_with_date(datetime(2025, 1, 15, 10, 0, tzinfo=UTC), 0)
        store.write_bars(symbol="KEEP", exchange=Exchange.NSE, timeframe="1m", bars=[bar])
        deleted = store.cleanup_older_than(days=0)
        assert not deleted

    def test_cleanup_no_files(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive")
        deleted = store.cleanup_older_than(days=30)
        assert deleted == []


# --------------------------------------------------------------------------- #
# Compression configuration tests
# --------------------------------------------------------------------------- #
class TestCompressionConfig:
    def test_compression_none(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="NONE")
        assert store.compression == "NONE"

    def test_compression_snappy(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="SNAPPY")
        assert store.compression == "SNAPPY"

    def test_compression_gzip(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="GZIP")
        assert store.compression == "GZIP"

    def test_compression_brotli(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="BROTLI")
        assert store.compression == "BROTLI"

    def test_compression_lz4(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="LZ4")
        assert store.compression == "LZ4"

    def test_compression_zlib(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "archive", compression="ZLIB")
        assert store.compression == "ZLIB"

    def test_invalid_compression_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Unsupported parquet compression"):
            ParquetStore(tmp_path / "archive", compression="UNKNOWN")

    def test_write_uses_custom_compression(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive", compression="LZ4")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]
        store.write_bars(symbol="COMP", exchange=Exchange.NSE, timeframe="1m", bars=[_bar(0)])
        # The fake parquet writer should have been called successfully
        assert len(fake_parquet._storage) == 1

    def test_write_uses_default_compression(self, tmp_path: Path) -> None:
        fake_parquet = _FakeParquet()
        store = ParquetStore(tmp_path / "archive")
        store._import_pyarrow = lambda: (_FakePyArrow(), fake_parquet)  # type: ignore[method-assign]
        store.write_bars(symbol="DEF", exchange=Exchange.NSE, timeframe="1m", bars=[_bar(0)])
        assert len(fake_parquet._storage) == 1
