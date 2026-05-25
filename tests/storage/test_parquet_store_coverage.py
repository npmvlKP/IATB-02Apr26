"""
Comprehensive test coverage for ParquetStore with real pyarrow integration.
Covers all 5 scenarios: round-trip, cross-file queries, compression, retention, partitions.
"""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.data.base import OHLCVBar
from iatb.storage.parquet_store import (
    ParquetStore,
    ParquetStoreError,
    _allowed_compression,
    _parse_timestamp,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parquet_store(tmp_path: Path) -> ParquetStore:
    """Provide a ParquetStore instance with temporary directory."""
    return ParquetStore(root_dir=tmp_path / "archive")


@pytest.fixture
def sample_bars() -> list[OHLCVBar]:
    """Provide sample OHLCVBar objects for testing."""
    base_time = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    return [
        OHLCVBar(
            timestamp=create_timestamp(base_time + timedelta(minutes=i)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        for i in range(5)
    ]


@pytest.fixture
def bars_different_months() -> list[list[OHLCVBar]]:
    """Provide bars for different months to test partitioning."""
    return [
        [
            OHLCVBar(
                timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="BANKNIFTY",
                open=create_price("100.00"),
                high=create_price("101.00"),
                low=create_price("99.00"),
                close=create_price("100.50"),
                volume=create_quantity("1500"),
                source="unit-test",
            )
        ],
        [
            OHLCVBar(
                timestamp=create_timestamp(datetime(2026, 2, 15, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="BANKNIFTY",
                open=create_price("101.00"),
                high=create_price("102.00"),
                low=create_price("100.00"),
                close=create_price("101.50"),
                volume=create_quantity("1600"),
                source="unit-test",
            )
        ],
        [
            OHLCVBar(
                timestamp=create_timestamp(datetime(2026, 3, 15, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="BANKNIFTY",
                open=create_price("102.00"),
                high=create_price("103.00"),
                low=create_price("101.00"),
                close=create_price("102.50"),
                volume=create_quantity("1700"),
                source="unit-test",
            )
        ],
    ]


# ---------------------------------------------------------------------------
# Timestamp Parsing Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestParseTimestamp:
    """Tests for _parse_timestamp helper function."""

    def test_parse_iso_string_with_offset(self) -> None:
        """Test parsing ISO formatted string with timezone offset."""
        ts = _parse_timestamp("2026-01-15T10:00:00+00:00")
        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 15
        assert ts.hour == 10
        assert ts.tzinfo == UTC

    def test_parse_iso_string_with_z_suffix(self) -> None:
        """Test parsing ISO string with 'Z' suffix (UTC indicator)."""
        ts = _parse_timestamp("2026-01-15T10:00:00Z")
        assert ts.year == 2026
        assert ts.month == 1
        assert ts.day == 15
        assert ts.tzinfo == UTC

    def test_parse_naive_datetime_converts_to_utc(self) -> None:
        """Test parsing naive datetime auto-converts to UTC."""
        naive_dt = datetime(2026, 1, 15, 10, 0, 0)
        ts = _parse_timestamp(naive_dt)
        assert ts.year == 2026
        assert ts.tzinfo == UTC

    def test_parse_aware_datetime_preserves_utc(self) -> None:
        """Test parsing timezone-aware datetime preserves UTC."""
        aware_dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        ts = _parse_timestamp(aware_dt)
        assert ts.year == 2026
        assert ts.tzinfo == UTC

    def test_parse_aware_datetime_converts_to_utc(self) -> None:
        """Test parsing timezone-aware datetime in different timezone converts to UTC."""
        from datetime import timezone

        # Create datetime in UTC+5:30 (IST)
        ist = timezone(timedelta(hours=5, minutes=30))
        ist_dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=ist)
        ts = _parse_timestamp(ist_dt)
        assert ts.year == 2026
        assert ts.tzinfo == UTC
        # 10:00 IST = 04:30 UTC
        assert ts.hour == 4
        assert ts.minute == 30

    def test_parse_invalid_type_raises(self) -> None:
        """Test parsing invalid type raises ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported parquet timestamp type"):
            _parse_timestamp(123)  # type: ignore[arg-type]

    def test_parse_invalid_string_raises(self) -> None:
        """Test parsing invalid string raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid parquet timestamp"):
            _parse_timestamp("invalid-timestamp")

    def test_parse_invalid_iso_format_raises(self) -> None:
        """Test parsing invalid ISO format raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid parquet timestamp"):
            _parse_timestamp("2026-13-01T10:00:00+00:00")


# ---------------------------------------------------------------------------
# Compression Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestAllowedCompression:
    """Tests for _allowed_compression validation."""

    @pytest.mark.parametrize(
        "code", ["NONE", "SNAPPY", "GZIP", "BROTLI", "LZ4", "ZSTD"]
    )
    def test_valid_compression_codes(self, code: str) -> None:
        """Test all valid compression codes are accepted."""
        assert _allowed_compression(code) == code

    def test_invalid_compression_raises(self) -> None:
        """Test invalid compression code raises ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported parquet compression"):
            _allowed_compression("INVALID")

    def test_case_sensitive(self) -> None:
        """Test compression codes are case-sensitive."""
        with pytest.raises(ConfigError, match="Unsupported parquet compression"):
            _allowed_compression("zstd")


# ---------------------------------------------------------------------------
# ParquetStore Initialization Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestParquetStoreInitialization:
    """Tests for ParquetStore initialization."""

    def test_default_compression(self, tmp_path: Path) -> None:
        """Test default compression is ZSTD."""
        store = ParquetStore(tmp_path / "archive")
        assert store.compression == "ZSTD"

    def test_custom_compression(self, tmp_path: Path) -> None:
        """Test custom compression is set correctly."""
        store = ParquetStore(tmp_path / "archive", compression="SNAPPY")
        assert store.compression == "SNAPPY"

    def test_invalid_compression_raises(self, tmp_path: Path) -> None:
        """Test invalid compression raises ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported parquet compression"):
            ParquetStore(tmp_path / "archive", compression="INVALID")

    def test_root_dir_property(self, tmp_path: Path) -> None:
        """Test root_dir property returns correct path."""
        store = ParquetStore(tmp_path / "archive")
        assert store.root_dir == tmp_path / "archive"


# ---------------------------------------------------------------------------
# Write/Read Round-Trip Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestWriteReadRoundTrip:
    """Tests for write_bars and read_bars round-trip functionality."""

    def test_write_and_read_single_bar(
        self, parquet_store: ParquetStore, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test write and read round-trip for a single bar."""
        pytest.importorskip("pyarrow")

        file_path = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[0]],
        )

        assert file_path.exists()
        loaded = parquet_store.read_bars(file_path)
        assert len(loaded) == 1
        assert loaded[0].symbol == "BANKNIFTY"
        assert loaded[0].exchange == Exchange.NSE
        assert loaded[0].open == create_price("100.00")
        assert loaded[0].high == create_price("101.00")
        assert loaded[0].low == create_price("99.00")
        assert loaded[0].close == create_price("100.50")
        assert loaded[0].volume == create_quantity("1500")
        assert loaded[0].source == "unit-test"

    def test_write_and_read_multiple_bars(
        self, parquet_store: ParquetStore, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test write and read round-trip for multiple bars."""
        pytest.importorskip("pyarrow")

        file_path = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=sample_bars,
        )

        loaded = parquet_store.read_bars(file_path)
        assert len(loaded) == 5
        for i, bar in enumerate(loaded):
            assert bar.symbol == "BANKNIFTY"
            assert bar.timestamp.minute == 30 + i

    def test_write_bars_rejects_empty_list(self, parquet_store: ParquetStore) -> None:
        """Test write_bars rejects empty bars list."""
        with pytest.raises(ConfigError, match="bars cannot be empty"):
            parquet_store.write_bars(
                symbol="BANKNIFTY",
                exchange=Exchange.NSE,
                timeframe="1m",
                bars=[],
            )

    def test_read_bars_rejects_missing_file(self, parquet_store: ParquetStore) -> None:
        """Test read_bars rejects non-existent file."""
        with pytest.raises(ConfigError, match="does not exist"):
            parquet_store.read_bars(parquet_store.root_dir / "nonexistent.parquet")

    def test_write_bars_creates_partition_directory(
        self, parquet_store: ParquetStore, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test write_bars creates date-based partition directory."""
        pytest.importorskip("pyarrow")

        file_path = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[0]],
        )

        # Check directory structure: root/exchange/symbol/timeframe/YYYY/MM
        parts = file_path.relative_to(parquet_store.root_dir).parts
        assert parts[0] == "NSE"
        assert parts[1] == "BANKNIFTY"
        assert parts[2] == "1m"
        assert parts[3] == "2026"
        assert parts[4] == "01"

    def test_filename_contains_timestamps(
        self, parquet_store: ParquetStore, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test filename contains start and end timestamps."""
        pytest.importorskip("pyarrow")

        file_path = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=sample_bars[:3],
        )

        filename = file_path.name
        # Should contain timestamps in format: 20260115T093000_20260115T093200.parquet
        assert "20260115T093000" in filename
        assert "20260115T093200" in filename
        assert filename.endswith(".parquet")


# ---------------------------------------------------------------------------
# Cross-File Query Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestCrossFileQueries:
    """Tests for read_bars_range across multiple partitions."""

    def test_read_bars_range_cross_partition(
        self, parquet_store: ParquetStore, bars_different_months: list[list[OHLCVBar]]
    ) -> None:
        """Test querying bars across multiple date partitions."""
        pytest.importorskip("pyarrow")

        # Write bars for different months
        for bars in bars_different_months:
            parquet_store.write_bars(
                symbol="BANKNIFTY",
                exchange=Exchange.NSE,
                timeframe="1m",
                bars=bars,
            )

        # Query across Jan-Feb 2026
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 2, 28, 23, 59, tzinfo=UTC)

        result = parquet_store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=start,
            end=end,
        )

        assert len(result) == 2  # Jan and Feb bars
        assert result[0].timestamp.month == 1
        assert result[1].timestamp.month == 2

    def test_read_bars_range_naive_start_raises(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range raises ConfigError for naive start datetime."""
        with pytest.raises(ConfigError, match="timezone-aware"):
            parquet_store.read_bars_range(
                symbol="BANKNIFTY",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 1, 9, 0, 0),  # Naive
                end=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
            )

    def test_read_bars_range_naive_end_raises(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range raises ConfigError for naive end datetime."""
        with pytest.raises(ConfigError, match="timezone-aware"):
            parquet_store.read_bars_range(
                symbol="BANKNIFTY",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC),
                end=datetime(2026, 1, 1, 10, 0, 0),  # Naive
            )

    def test_read_bars_range_end_before_start_raises(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range raises ConfigError when end is before start."""
        with pytest.raises(ConfigError, match="end must be after start"):
            parquet_store.read_bars_range(
                symbol="BANKNIFTY",
                exchange=Exchange.NSE,
                timeframe="1m",
                start=datetime(2026, 1, 2, 9, 0, 0, tzinfo=UTC),
                end=datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC),
            )

    def test_read_bars_range_empty_when_no_files(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range returns empty list when no files exist."""
        start = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)

        result = parquet_store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=start,
            end=end,
        )

        assert result == []

    def test_read_bars_range_sorts_results_chronologically(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range returns results sorted by timestamp."""
        pytest.importorskip("pyarrow")

        # Write bars in non-chronological order
        bar_mar = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 3, 5, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("102.00"),
            high=create_price("103.00"),
            low=create_price("101.00"),
            close=create_price("102.50"),
            volume=create_quantity("1700"),
            source="unit-test",
        )
        bar_jan = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 10, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        bar_feb = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 2, 5, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("101.00"),
            high=create_price("102.00"),
            low=create_price("100.00"),
            close=create_price("101.50"),
            volume=create_quantity("1600"),
            source="unit-test",
        )

        # Write in reverse order
        parquet_store.write_bars(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[bar_mar]
        )
        parquet_store.write_bars(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[bar_jan]
        )
        parquet_store.write_bars(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[bar_feb]
        )

        # Query all
        result = parquet_store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            end=datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
        )

        assert len(result) == 3
        months = [r.timestamp.month for r in result]
        assert months == [1, 2, 3]  # Sorted chronologically

    def test_read_bars_range_filters_by_timestamp_bounds(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test read_bars_range filters bars by timestamp bounds."""
        pytest.importorskip("pyarrow")

        bar_jan10 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 10, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        bar_feb20 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 2, 20, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("101.00"),
            high=create_price("102.00"),
            low=create_price("100.00"),
            close=create_price("101.50"),
            volume=create_quantity("1600"),
            source="unit-test",
        )

        parquet_store.write_bars(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[bar_jan10]
        )
        parquet_store.write_bars(
            symbol="BANKNIFTY", exchange=Exchange.NSE, timeframe="1m", bars=[bar_feb20]
        )

        # Query only February
        result = parquet_store.read_bars_range(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            start=datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
            end=datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
        )

        assert len(result) == 1
        assert result[0].timestamp.month == 2


# ---------------------------------------------------------------------------
# Retention Policy Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestRetentionPolicy:
    """Tests for cleanup_older_than retention policy."""

    def test_cleanup_older_than_rejects_negative_days(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test cleanup_older_than rejects negative days."""
        with pytest.raises(ConfigError, match="days must be non-negative"):
            parquet_store.cleanup_older_than(days=-1)

    def test_cleanup_older_than_no_files(self, parquet_store: ParquetStore) -> None:
        """Test cleanup_older_than returns empty list when no files exist."""
        deleted = parquet_store.cleanup_older_than(days=30)
        assert deleted == []

    def test_cleanup_older_than_deletes_old_files(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test cleanup_older_than deletes files older than specified days."""
        pytest.importorskip("pyarrow")

        old_bar = OHLCVBar(
            timestamp=create_timestamp(datetime(2020, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[old_bar],
        )

        frozen_now = datetime(2026, 5, 11, tzinfo=UTC)
        from unittest.mock import patch

        with patch.object(
            ParquetStore,
            "_get_utc_now",
            return_value=frozen_now,
        ):
            deleted = parquet_store.cleanup_older_than(days=1)
        assert len(deleted) == 1
        assert not deleted[0].exists()

    def test_cleanup_older_than_skips_recent_files(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test cleanup_older_than skips files newer than specified days."""
        pytest.importorskip("pyarrow")

        recent_bar = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 5, 10, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[recent_bar],
        )

        frozen_now = datetime(2026, 5, 11, tzinfo=UTC)
        from unittest.mock import patch

        with patch.object(
            ParquetStore,
            "_get_utc_now",
            return_value=frozen_now,
        ):
            deleted = parquet_store.cleanup_older_than(days=1)
        assert len(deleted) == 0

    def test_cleanup_zero_days_deletes_all_but_today(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test cleanup with zero days deletes all files."""
        pytest.importorskip("pyarrow")

        old_bar = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 5, 10, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[old_bar],
        )

        frozen_now = datetime(2026, 5, 11, tzinfo=UTC)
        from unittest.mock import patch

        with patch.object(
            ParquetStore,
            "_get_utc_now",
            return_value=frozen_now,
        ):
            deleted = parquet_store.cleanup_older_than(days=0)
        assert len(deleted) == 1


# ---------------------------------------------------------------------------
# Compression Codec Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestCompressionCodecs:
    """Tests for compression codec support."""

    @pytest.mark.parametrize(
        "codec", ["NONE", "SNAPPY", "GZIP", "BROTLI", "LZ4", "ZSTD"]
    )
    def test_write_read_with_compression_codec(
        self, tmp_path: Path, codec: str, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test write/read round-trip with each compression codec."""
        pytest.importorskip("pyarrow")

        store = ParquetStore(tmp_path / "archive", compression=codec)
        assert store.compression == codec

        file_path = store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[0]],
        )

        assert file_path.exists()
        loaded = store.read_bars(file_path)
        assert len(loaded) == 1
        assert loaded[0].symbol == "BANKNIFTY"


# ---------------------------------------------------------------------------
# Date-Based Partition Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestDateBasedPartitions:
    """Tests for date-based partition directory structure."""

    def test_partition_dir_structure(self, parquet_store: ParquetStore) -> None:
        """Test _partition_dir returns correct path."""
        partition = parquet_store._partition_dir(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
        )
        expected = parquet_store.root_dir / "NSE" / "BANKNIFTY" / "1m"
        assert partition == expected

    def test_date_partition_dir_structure(self, parquet_store: ParquetStore) -> None:
        """Test _date_partition_dir returns correct path with date."""
        ts = create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC))
        partition = parquet_store._date_partition_dir(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            when=ts,
        )
        expected = parquet_store.root_dir / "NSE" / "BANKNIFTY" / "1m" / "2026" / "01"
        assert partition == expected

    def test_build_filename_with_timestamps(self, parquet_store: ParquetStore) -> None:
        """Test _build_filename generates correct filename."""
        start = create_timestamp(datetime(2026, 1, 15, 9, 30, tzinfo=UTC))
        end = create_timestamp(datetime(2026, 1, 15, 9, 35, tzinfo=UTC))

        filename = ParquetStore._build_filename(start, end)
        assert filename == "20260115T093000_20260115T093500.parquet"

    def test_list_parquet_files_empty(self, parquet_store: ParquetStore) -> None:
        """Test list_parquet_files returns empty list when no files exist."""
        files = parquet_store.list_parquet_files(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
        )
        assert files == []

    def test_list_parquet_files_returns_sorted(
        self, parquet_store: ParquetStore, sample_bars: list[OHLCVBar]
    ) -> None:
        """Test list_parquet_files returns sorted list of files."""
        pytest.importorskip("pyarrow")

        # Write multiple files
        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[0]],
        )
        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[1]],
        )

        files = parquet_store.list_parquet_files(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
        )

        assert len(files) == 2
        # Files should be sorted
        assert files == sorted(files)


# ---------------------------------------------------------------------------
# Column Conversion Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestColumnConversion:
    """Tests for column conversion helpers."""

    def test_bars_to_columns_conversion(self, sample_bars: list[OHLCVBar]) -> None:
        """Test _bars_to_columns converts bars to column dict."""
        columns = ParquetStore._bars_to_columns(sample_bars[:2])

        assert "exchange" in columns
        assert "symbol" in columns
        assert "timestamp_utc" in columns
        assert "open_price" in columns
        assert "high_price" in columns
        assert "low_price" in columns
        assert "close_price" in columns
        assert "volume" in columns
        assert "source" in columns

        assert len(columns["exchange"]) == 2
        assert len(columns["symbol"]) == 2
        assert len(columns["timestamp_utc"]) == 2

    def test_columns_to_bars_roundtrip(self, sample_bars: list[OHLCVBar]) -> None:
        """Test _columns_to_bars round-trip conversion."""
        columns = ParquetStore._bars_to_columns(sample_bars[:2])
        converted_bars = ParquetStore._columns_to_bars(columns)

        assert len(converted_bars) == 2
        for i, bar in enumerate(converted_bars):
            assert bar.symbol == sample_bars[i].symbol
            assert bar.exchange == sample_bars[i].exchange
            assert bar.open == sample_bars[i].open
            assert bar.high == sample_bars[i].high
            assert bar.low == sample_bars[i].low
            assert bar.close == sample_bars[i].close
            assert bar.volume == sample_bars[i].volume

    def test_columns_to_bars_missing_required_fields(self) -> None:
        """Test _columns_to_bars raises ConfigError for missing required fields."""
        columns = {
            "exchange": ["NSE"],
            "symbol": ["BANKNIFTY"],
            # Missing other required fields
        }
        with pytest.raises(
            ConfigError, match="Parquet columns missing required OHLCV fields"
        ):
            ParquetStore._columns_to_bars(columns)

    def test_build_bar_from_columns(self) -> None:
        """Test _build_bar_from_columns creates correct OHLCVBar."""
        columns = {
            "exchange": ["NSE"],
            "symbol": ["BANKNIFTY"],
            "timestamp_utc": ["2026-01-15T10:00:00+00:00"],
            "open_price": ["100.00"],
            "high_price": ["101.00"],
            "low_price": ["99.00"],
            "close_price": ["100.50"],
            "volume": ["1500"],
            "source": ["unit-test"],
        }

        bar = ParquetStore._build_bar_from_columns(columns, 0)

        assert bar.exchange == Exchange.NSE
        assert bar.symbol == "BANKNIFTY"
        assert bar.timestamp.year == 2026
        assert bar.open == create_price("100.00")
        assert bar.high == create_price("101.00")
        assert bar.low == create_price("99.00")
        assert bar.close == create_price("100.50")
        assert bar.volume == create_quantity("1500")
        assert bar.source == "unit-test"


# ---------------------------------------------------------------------------
# Logging Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestLogging:
    """Tests for structured logging."""

    def test_write_bars_logs_success(
        self,
        parquet_store: ParquetStore,
        sample_bars: list[OHLCVBar],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test write_bars logs successful write operation."""
        pytest.importorskip("pyarrow")

        caplog.set_level(logging.INFO)

        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[sample_bars[0]],
        )

        assert "Wrote 1 bars to" in caplog.text
        assert "compression=ZSTD" in caplog.text

    def test_cleanup_logs_deletion(
        self,
        parquet_store: ParquetStore,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test cleanup_older_than logs deleted files."""
        pytest.importorskip("pyarrow")

        caplog.set_level(logging.INFO)

        old_bar = OHLCVBar(
            timestamp=create_timestamp(datetime(2020, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[old_bar],
        )

        frozen_now = datetime(2026, 5, 11, tzinfo=UTC)
        from unittest.mock import patch

        with patch.object(
            ParquetStore,
            "_get_utc_now",
            return_value=frozen_now,
        ):
            parquet_store.cleanup_older_than(days=1)

        assert "Deleted archived file (age > 1 days)" in caplog.text


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestErrorHandling:
    """Tests for error handling in ParquetStore."""

    def test_missing_pyarrow_dependency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test ParquetStore operations fail gracefully when pyarrow is missing."""
        store = ParquetStore(tmp_path / "archive")

        # Mock import_module to raise ModuleNotFoundError
        def mock_import_module(name: str) -> None:
            if name == "pyarrow" or name == "pyarrow.parquet":
                raise ModuleNotFoundError(f"No module named '{name}'")
            raise ModuleNotFoundError(f"No module named '{name}'")

        monkeypatch.setattr("importlib.import_module", mock_import_module)

        with pytest.raises(ConfigError, match="pyarrow dependency is required"):
            store._import_pyarrow()

    def test_parquet_store_error_hierarchy(self) -> None:
        """Test ParquetStoreError inherits from ConfigError."""
        error = ParquetStoreError("test error")
        assert isinstance(error, ConfigError)


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


@pytest.mark.xdist_group("parquet_store")
class TestEdgeCases:
    """Tests for edge cases and boundary values."""

    def test_write_bars_with_different_symbols(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test write_bars with different symbols creates separate partitions."""
        pytest.importorskip("pyarrow")

        bar1 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        bar2 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="NIFTY50",
            open=create_price("200.00"),
            high=create_price("201.00"),
            low=create_price("199.00"),
            close=create_price("200.50"),
            volume=create_quantity("2500"),
            source="unit-test",
        )

        file1 = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar1],
        )
        file2 = parquet_store.write_bars(
            symbol="NIFTY50",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar2],
        )

        # Files should be in different directories
        assert "BANKNIFTY" in str(file1)
        assert "NIFTY50" in str(file2)

    def test_write_bars_with_different_exchanges(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test write_bars with different exchanges creates separate partitions."""
        pytest.importorskip("pyarrow")

        bar1 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        bar2 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.BSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        file1 = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar1],
        )
        file2 = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.BSE,
            timeframe="1m",
            bars=[bar2],
        )

        # Files should be in different directories
        assert "NSE" in str(file1)
        assert "BSE" in str(file2)

    def test_write_bars_with_different_timeframes(
        self, parquet_store: ParquetStore
    ) -> None:
        """Test write_bars with different timeframes creates separate partitions."""
        pytest.importorskip("pyarrow")

        bar1 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )
        bar2 = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.00"),
            high=create_price("101.00"),
            low=create_price("99.00"),
            close=create_price("100.50"),
            volume=create_quantity("1500"),
            source="unit-test",
        )

        file1 = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar1],
        )
        file2 = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="5m",
            bars=[bar2],
        )

        # Files should be in different directories
        assert "1m" in str(file1)
        assert "5m" in str(file2)

    def test_decimal_precision_preserved(self, parquet_store: ParquetStore) -> None:
        """Test that Decimal precision is preserved in round-trip."""
        pytest.importorskip("pyarrow")

        bar = OHLCVBar(
            timestamp=create_timestamp(datetime(2026, 1, 15, 10, 0, tzinfo=UTC)),
            exchange=Exchange.NSE,
            symbol="BANKNIFTY",
            open=create_price("100.123456789"),
            high=create_price("101.987654321"),
            low=create_price("99.555555555"),
            close=create_price("100.999999999"),
            volume=create_quantity("1500.123456789"),
            source="unit-test",
        )

        file_path = parquet_store.write_bars(
            symbol="BANKNIFTY",
            exchange=Exchange.NSE,
            timeframe="1m",
            bars=[bar],
        )

        loaded = parquet_store.read_bars(file_path)
        assert len(loaded) == 1
        assert loaded[0].open == create_price("100.123456789")
        assert loaded[0].high == create_price("101.987654321")
        assert loaded[0].low == create_price("99.555555555")
        assert loaded[0].close == create_price("100.999999999")
        assert loaded[0].volume == create_quantity("1500.123456789")
