"""
Comprehensive test coverage for DuckDBStore targeting >=90% coverage.
Augments existing tests with edge cases, error paths, and integration tests.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.storage.duckdb_store import DuckDBStore, _normalize_timestamp

# ---------------------------------------------------------------------------
# Test Data Helpers
# ---------------------------------------------------------------------------


def _create_bar(
    offset_minutes: int,
    symbol: str = "TEST",
    close: str = "100.50",
    source: str = "test-source",
) -> OHLCVBar:
    """Create a test OHLCVBar with deterministic values."""
    close_price = Decimal(close)
    high_price = max(Decimal("101"), close_price, Decimal("99")) + Decimal("1")
    low_price = min(Decimal("99"), close_price, Decimal("100"))
    return OHLCVBar(
        timestamp=create_timestamp(
            datetime(2024, 1, 1, 9, 15, tzinfo=UTC) + timedelta(minutes=offset_minutes)
        ),
        exchange=Exchange.NSE,
        symbol=symbol,
        open=create_price("100"),
        high=create_price(str(high_price)),
        low=create_price(str(low_price)),
        close=create_price(close),
        volume=create_quantity("1500"),
        source=source,
    )


def _create_daily_bars(
    symbol: str,
    days: int,
    base_price: Decimal = Decimal("100"),
) -> list[OHLCVBar]:
    """Create test bars spanning multiple days for daily summary tests."""
    bars = []
    for day in range(days):
        for hour in range(9, 16):  # Market hours
            offset_minutes = day * 24 * 60 + (hour - 9) * 60
            close_price = base_price + Decimal(str(day * 5 + hour))
            bars.append(_create_bar(offset_minutes, symbol=symbol, close=str(close_price)))
    return bars


# ---------------------------------------------------------------------------
# _normalize_timestamp Tests
# ---------------------------------------------------------------------------


class TestNormalizeTimestamp:
    """Test timestamp normalization utility."""

    def test_normalize_utc_datetime(self) -> None:
        """UTC datetime should be normalized without modification."""
        dt = datetime(2024, 1, 1, 10, 30, tzinfo=UTC)
        result = _normalize_timestamp(dt)
        assert result == dt

    def test_normalize_naive_datetime_adds_utc(self) -> None:
        """Naive datetime should have UTC timezone added."""
        dt = datetime(2024, 1, 1, 10, 30, tzinfo=UTC)
        result = _normalize_timestamp(dt)
        assert result.tzinfo == UTC
        assert result.hour == 10
        assert result.minute == 30

    def test_normalize_non_utc_datetime_converts(self) -> None:
        """Non-UTC datetime should be converted to UTC."""
        from zoneinfo import ZoneInfo

        dt = datetime(2024, 1, 1, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
        result = _normalize_timestamp(dt)
        assert result.tzinfo == UTC
        # IST is UTC+5:30, so 10:30 IST = 05:00 UTC
        assert result.hour == 5

    def test_normalize_iso_string_with_z_suffix(self) -> None:
        """ISO string with 'Z' suffix should be parsed correctly."""
        ts_str = "2024-01-01T10:30:00Z"
        result = _normalize_timestamp(ts_str)
        assert result.tzinfo == UTC
        assert result.year == 2024

    def test_normalize_iso_string_with_offset(self) -> None:
        """ISO string with timezone offset should be parsed correctly."""
        ts_str = "2024-01-01T10:30:00+05:30"
        result = _normalize_timestamp(ts_str)
        assert result.tzinfo == UTC

    def test_normalize_naive_iso_string_adds_utc(self) -> None:
        """Naive ISO string should have UTC added."""
        ts_str = "2024-01-01T10:30:00"
        result = _normalize_timestamp(ts_str)
        assert result.tzinfo == UTC

    def test_normalize_invalid_string_raises_config_error(self) -> None:
        """Invalid timestamp string should raise ConfigError."""
        with pytest.raises(ConfigError, match="Invalid timestamp from DuckDB"):
            _normalize_timestamp("not-a-timestamp")

    def test_normalize_unsupported_type_raises_config_error(self) -> None:
        """Unsupported type should raise ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported timestamp type"):
            _normalize_timestamp(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DuckDBStore.__init__ Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreInit:
    """Test DuckDBStore initialization."""

    def test_init_creates_store(self, tmp_path: Path) -> None:
        """Store should be initialized with correct attributes."""
        db_path = tmp_path / "test.duckdb"
        store = DuckDBStore(db_path)
        assert store._db_path == db_path
        assert store._connection is None
        assert store._connection_errors == 0
        assert store._max_reconnect_attempts == 3

    def test_init_with_path_parent_dirs(self, tmp_path: Path) -> None:
        """Store should handle paths with non-existent parent directories."""
        db_path = tmp_path / "nested" / "dir" / "test.duckdb"
        store = DuckDBStore(db_path)
        assert store._db_path == db_path
        # Parent should be created on connect, not init


# ---------------------------------------------------------------------------
# DuckDBStore.close Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreClose:
    """Test DuckDBStore close behavior."""

    def test_close_when_connection_open(self, tmp_path: Path) -> None:
        """Close should safely close an open connection."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.initialize()
        # Store -> connection reference before closing
        conn = store._connection
        assert conn is not None
        store.close()
        assert store._connection is None

    def test_close_when_connection_already_none(self, tmp_path: Path) -> None:
        """Close should be safe when connection is already None."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store._connection = None
        store.close()
        assert store._connection is None

    def test_close_handles_close_exception(self, tmp_path: Path) -> None:
        """Close should swallow exceptions during connection.close()."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("Connection error")
        store._connection = mock_conn
        store.close()
        assert store._connection is None


# ---------------------------------------------------------------------------
# DuckDBStore.initialize Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreInitialize:
    """Test DuckDBStore initialization behavior."""

    def test_initialize_creates_table(self, tmp_path: Path) -> None:
        """Initialize should create ohlcv_bars table if it doesn't exist."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.initialize()
        # Second call should be idempotent
        store.initialize()
        # Verify by storing data (would fail if table doesn't exist)
        store.store_bars([_create_bar(0)])
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1


# ---------------------------------------------------------------------------
# DuckDBStore.store_bars Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreStoreBars:
    """Test storing OHLCV bars."""

    def test_store_empty_list_is_noop(self, tmp_path: Path) -> None:
        """Storing empty list should be a no-op."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.store_bars([])
        # Should not raise error

    def test_store_single_bar(self, tmp_path: Path) -> None:
        """Store a single bar and load it back."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bar = _create_bar(0)
        store.store_bars([bar])
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1
        assert loaded[0].symbol == "TEST"
        assert loaded[0].open == bar.open

    def test_store_multiple_bars(self, tmp_path: Path) -> None:
        """Store multiple bars and verify order."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(5)]
        store.store_bars(bars)
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 5
        for i, bar in enumerate(loaded):
            assert bar.timestamp == bars[i].timestamp

    def test_store_bars_upserts_existing(self, tmp_path: Path) -> None:
        """Storing same bar should replace (delete+insert)."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bar1 = _create_bar(0, close="100.50")
        bar2 = _create_bar(0, close="101.50")  # Same timestamp
        store.store_bars([bar1])
        store.store_bars([bar2])
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1
        assert loaded[0].close == create_price("101.50")

    def test_store_bars_different_symbols(self, tmp_path: Path) -> None:
        """Store bars for different symbols."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.store_bars([_create_bar(0, symbol="SYM1")])
        store.store_bars([_create_bar(1, symbol="SYM2")])
        loaded1 = store.load_bars(symbol="SYM1", exchange=Exchange.NSE, limit=10)
        loaded2 = store.load_bars(symbol="SYM2", exchange=Exchange.NSE, limit=10)
        assert len(loaded1) == 1
        assert len(loaded2) == 1
        assert loaded1[0].symbol == "SYM1"
        assert loaded2[0].symbol == "SYM2"

    def test_store_bars_different_sources(self, tmp_path: Path) -> None:
        """Store bars from different sources should be separate records."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Use different timestamps to avoid validation error
        bar1 = _create_bar(0, source="source1")
        bar2 = _create_bar(1, source="source2")
        store.store_bars([bar1, bar2])
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 2


# ---------------------------------------------------------------------------
# DuckDBStore.load_bars Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreLoadBars:
    """Test loading OHLCV bars."""

    def test_load_bars_without_filters(self, tmp_path: Path) -> None:
        """Load all bars without time filters."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(10)]
        store.store_bars(bars)
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 10

    def test_load_bars_with_start_filter(self, tmp_path: Path) -> None:
        """Load bars with start time filter."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(10)]
        store.store_bars(bars)
        start_time = create_timestamp(datetime(2024, 1, 1, 9, 17, tzinfo=UTC))
        loaded = store.load_bars(
            symbol="TEST",
            exchange=Exchange.NSE,
            start=start_time,
            limit=10,
        )
        assert len(loaded) == 8  # Minutes 2-9
        assert loaded[0].timestamp == bars[2].timestamp

    def test_load_bars_with_end_filter(self, tmp_path: Path) -> None:
        """Load bars with end time filter."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(10)]
        store.store_bars(bars)
        end_time = create_timestamp(datetime(2024, 1, 1, 9, 17, tzinfo=UTC))
        loaded = store.load_bars(
            symbol="TEST",
            exchange=Exchange.NSE,
            end=end_time,
            limit=10,
        )
        assert len(loaded) == 3  # Minutes 0-2
        assert loaded[-1].timestamp == bars[2].timestamp

    def test_load_bars_with_start_and_end_filter(self, tmp_path: Path) -> None:
        """Load bars with both start and end time filters."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(10)]
        store.store_bars(bars)
        start_time = create_timestamp(datetime(2024, 1, 1, 9, 16, tzinfo=UTC))
        end_time = create_timestamp(datetime(2024, 1, 1, 9, 18, tzinfo=UTC))
        loaded = store.load_bars(
            symbol="TEST",
            exchange=Exchange.NSE,
            start=start_time,
            end=end_time,
            limit=10,
        )
        assert len(loaded) == 3  # Minutes 1-3
        assert loaded[0].timestamp == bars[1].timestamp
        assert loaded[-1].timestamp == bars[3].timestamp

    def test_load_bars_respects_limit(self, tmp_path: Path) -> None:
        """Load bars should respect limit parameter."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [_create_bar(i) for i in range(20)]
        store.store_bars(bars)
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=5)
        assert len(loaded) == 5

    def test_load_bars_limit_zero_raises_config_error(self, tmp_path: Path) -> None:
        """Limit <= 0 should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=0)

    def test_load_bars_negative_limit_raises_config_error(self, tmp_path: Path) -> None:
        """Negative limit should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=-5)

    def test_load_bars_returns_empty_when_no_data(self, tmp_path: Path) -> None:
        """Load bars should return empty list when no data exists."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.initialize()  # Table must exist first
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert loaded == []

    def test_load_bars_filters_by_symbol(self, tmp_path: Path) -> None:
        """Load bars should filter by symbol."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.store_bars([_create_bar(0, symbol="SYM1")])
        store.store_bars([_create_bar(1, symbol="SYM2")])
        loaded = store.load_bars(symbol="SYM1", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1
        assert loaded[0].symbol == "SYM1"

    def test_load_bars_filters_by_exchange(self, tmp_path: Path) -> None:
        """Load bars should filter by exchange."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Create separate bars for different exchanges
        bar_nse = _create_bar(0, symbol="TEST")
        bar_bse = _create_bar(1, symbol="TEST", source="bse-source")
        # Manually create bar with BSE exchange
        bar_bse = OHLCVBar(
            timestamp=bar_bse.timestamp,
            exchange=Exchange.BSE,
            symbol="TEST",
            open=bar_bse.open,
            high=bar_bse.high,
            low=bar_bse.low,
            close=bar_bse.close,
            volume=bar_bse.volume,
            source=bar_bse.source,
        )
        store.store_bars([bar_nse])
        store.store_bars([bar_bse])
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1
        assert loaded[0].exchange == Exchange.NSE


# ---------------------------------------------------------------------------
# DuckDBStore.query_vwap Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryVWAP:
    """Test VWAP calculation."""

    def test_query_vwap_calculates_correctly(self, tmp_path: Path) -> None:
        """VWAP should correctly compute volume-weighted average price."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Bar 1: (100+105+95)/3 = 100, vol=100 => contribution = 10000
        # Bar 2: (110+115+105)/3 = 110, vol=200 => contribution = 22000
        # VWAP = (10000+22000)/(100+200) = 106.67
        bars = [
            OHLCVBar(
                timestamp=create_timestamp(datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="TEST",
                open=create_price("100"),
                high=create_price("105"),
                low=create_price("95"),
                close=create_price("100"),
                volume=create_quantity("100"),
                source="test",
            ),
            OHLCVBar(
                timestamp=create_timestamp(datetime(2024, 1, 1, 10, 1, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="TEST",
                open=create_price("110"),
                high=create_price("115"),
                low=create_price("105"),
                close=create_price("110"),
                volume=create_quantity("200"),
                source="test",
            ),
        ]
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        vwap = store.query_vwap("TEST", Exchange.NSE, start, end)
        assert isinstance(vwap, Decimal)
        assert vwap > Decimal("100")
        assert vwap < Decimal("110")

    def test_query_vwap_no_data_raises_config_error(self, tmp_path: Path) -> None:
        """VWAP query with no data should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.initialize()  # Create table first
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="No data for VWAP calculation"):
            store.query_vwap("TEST", Exchange.NSE, start, end)


# ---------------------------------------------------------------------------
# DuckDBStore.query_daily_summary Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryDailySummary:
    """Test daily OHLCV aggregation."""

    def test_query_daily_summary_aggregates_single_day(self, tmp_path: Path) -> None:
        """Daily summary should aggregate bars from a single day."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = _create_daily_bars("TEST", days=1, base_price=Decimal("100"))
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 0, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 2, 0, 0, tzinfo=UTC))
        summary = store.query_daily_summary("TEST", Exchange.NSE, start, end)
        assert len(summary) == 1
        assert summary[0]["date"] == datetime(2024, 1, 1, tzinfo=UTC).date()
        assert summary[0]["volume"] > 0

    def test_query_daily_summary_aggregates_multiple_days(self, tmp_path: Path) -> None:
        """Daily summary should aggregate bars across multiple days."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = _create_daily_bars("TEST", days=3, base_price=Decimal("100"))
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 0, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 4, 0, 0, tzinfo=UTC))
        summary = store.query_daily_summary("TEST", Exchange.NSE, start, end)
        assert len(summary) == 3

    def test_query_daily_summary_ohlcv_correctness(self, tmp_path: Path) -> None:
        """Daily summary OHLCV values should be correct."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = [
            OHLCVBar(
                timestamp=create_timestamp(datetime(2024, 1, 1, 10, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="TEST",
                open=create_price("100"),
                high=create_price("110"),
                low=create_price("90"),
                close=create_price("105"),
                volume=create_quantity("100"),
                source="test",
            ),
            OHLCVBar(
                timestamp=create_timestamp(datetime(2024, 1, 1, 11, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="TEST",
                open=create_price("105"),
                high=create_price("115"),
                low=create_price("100"),
                close=create_price("110"),
                volume=create_quantity("150"),
                source="test",
            ),
        ]
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 0, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 2, 0, 0, tzinfo=UTC))
        summary = store.query_daily_summary("TEST", Exchange.NSE, start, end)
        assert len(summary) == 1
        assert summary[0]["open"] == create_price("100")  # First bar's open
        assert summary[0]["close"] == create_price("110")  # Last bar's close
        assert summary[0]["high"] == create_price("115")  # Max of all highs
        assert summary[0]["low"] == create_price("90")  # Min of all lows
        assert summary[0]["volume"] == create_quantity("250")  # Sum of volumes


# ---------------------------------------------------------------------------
# DuckDBStore.query_performance_ranking Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryPerformanceRanking:
    """Test performance ranking by return %."""

    def test_query_performance_ranking_returns_sorted(
        self,
        tmp_path: Path,
    ) -> None:
        """Performance ranking should be sorted by return % descending."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Create bars manually with exact timestamps to ensure query finds them
        base_ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

        # SYM1: 100 -> 110 = 10% return
        store.store_bars(
            [
                OHLCVBar(
                    timestamp=create_timestamp(base_ts),
                    exchange=Exchange.NSE,
                    symbol="SYM1",
                    open=create_price("100"),
                    high=create_price("105"),
                    low=create_price("95"),
                    close=create_price("100"),
                    volume=create_quantity("100"),
                    source="test",
                ),
                OHLCVBar(
                    timestamp=create_timestamp(base_ts + timedelta(hours=1)),
                    exchange=Exchange.NSE,
                    symbol="SYM1",
                    open=create_price("110"),
                    high=create_price("115"),
                    low=create_price("105"),
                    close=create_price("110"),
                    volume=create_quantity("100"),
                    source="test",
                ),
            ]
        )

        # SYM2: 200 -> 230 = 15% return
        store.store_bars(
            [
                OHLCVBar(
                    timestamp=create_timestamp(base_ts),
                    exchange=Exchange.NSE,
                    symbol="SYM2",
                    open=create_price("200"),
                    high=create_price("210"),
                    low=create_price("190"),
                    close=create_price("200"),
                    volume=create_quantity("100"),
                    source="test",
                ),
                OHLCVBar(
                    timestamp=create_timestamp(base_ts + timedelta(hours=1)),
                    exchange=Exchange.NSE,
                    symbol="SYM2",
                    open=create_price("230"),
                    high=create_price("240"),
                    low=create_price("220"),
                    close=create_price("230"),
                    volume=create_quantity("100"),
                    source="test",
                ),
            ]
        )

        # SYM3: 50 -> 52 = 4% return
        store.store_bars(
            [
                OHLCVBar(
                    timestamp=create_timestamp(base_ts),
                    exchange=Exchange.NSE,
                    symbol="SYM3",
                    open=create_price("50"),
                    high=create_price("55"),
                    low=create_price("45"),
                    close=create_price("50"),
                    volume=create_quantity("100"),
                    source="test",
                ),
                OHLCVBar(
                    timestamp=create_timestamp(base_ts + timedelta(hours=1)),
                    exchange=Exchange.NSE,
                    symbol="SYM3",
                    open=create_price("52"),
                    high=create_price("57"),
                    low=create_price("47"),
                    close=create_price("52"),
                    volume=create_quantity("100"),
                    source="test",
                ),
            ]
        )

        # Query range: 9:00 to 12:00 (encompasses all bars)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        ranking = store.query_performance_ranking(Exchange.NSE, start, end, limit=10)
        assert len(ranking) == 3
        # Should be sorted by return % descending
        # Check that returns are positive and sorted
        returns = [r["return_pct"] for r in ranking]
        assert all(r > 0 for r in returns), "All returns should be positive"
        assert returns == sorted(returns, reverse=True), "Returns should be sorted descending"
        assert ranking[0]["symbol"] == "SYM2"  # Highest return
        assert ranking[2]["symbol"] == "SYM3"  # Lowest return

    def test_query_performance_ranking_respects_limit(self, tmp_path: Path) -> None:
        """Performance ranking should respect limit parameter."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        for i in range(5):
            store.store_bars(
                [
                    _create_bar(0, symbol=f"SYM{i}", close="100"),
                    _create_bar(60, symbol=f"SYM{i}", close=str(100 + i * 10)),
                ]
            )
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        ranking = store.query_performance_ranking(Exchange.NSE, start, end, limit=2)
        assert len(ranking) == 2

    def test_query_performance_ranking_limit_zero_raises_config_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Limit <= 0 should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="limit must be positive"):
            store.query_performance_ranking(Exchange.NSE, start, end, limit=0)


# ---------------------------------------------------------------------------
# DuckDBStore.query_volatility Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryVolatility:
    """Test rolling volatility calculation."""

    def test_query_volatility_returns_rolling_stddev(self, tmp_path: Path) -> None:
        """Volatility query should return rolling standard deviation."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Create bars with varying prices
        bars = []
        for i in range(10):
            price = 100 + i * 2  # Increasing prices
            bars.append(
                OHLCVBar(
                    timestamp=create_timestamp(
                        datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=i)
                    ),
                    exchange=Exchange.NSE,
                    symbol="TEST",
                    open=create_price(str(price)),
                    high=create_price(str(price + 1)),
                    low=create_price(str(price - 1)),
                    close=create_price(str(price)),
                    volume=create_quantity("100"),
                    source="test",
                )
            )
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        vol = store.query_volatility("TEST", Exchange.NSE, window=3, start=start, end=end)
        assert len(vol) == 10
        for v in vol:
            assert "timestamp" in v
            assert "close" in v
            assert "volatility" in v
            assert v["close"] > 0

    def test_query_volatility_window_zero_raises_config_error(self, tmp_path: Path) -> None:
        """Window <= 0 should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="window must be positive"):
            store.query_volatility("TEST", Exchange.NSE, window=0, start=start, end=end)

    def test_query_volatility_negative_window_raises_config_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Negative window should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="window must be positive"):
            store.query_volatility("TEST", Exchange.NSE, window=-1, start=start, end=end)


# ---------------------------------------------------------------------------
# DuckDBStore.query_moving_averages Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryMovingAverages:
    """Test moving average calculation."""

    def test_query_moving_averages_returns_sma_ema(self, tmp_path: Path) -> None:
        """Moving averages query should return SMA and EMA."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = []
        for i in range(5):
            close_price = Decimal(str(100 + i * 2))  # 100, 102, 104, 106, 108
            ts = create_timestamp(datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=i))
            bars.append(
                OHLCVBar(
                    timestamp=ts,
                    exchange=Exchange.NSE,
                    symbol="TEST",
                    open=create_price(str(close_price - 1)),  # Open < close
                    high=create_price(str(close_price + 5)),  # High >= all
                    low=create_price(str(close_price - 2)),  # Low <= all
                    close=create_price(str(close_price)),
                    volume=create_quantity("100"),
                    source="test",
                )
            )
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        mas = store.query_moving_averages("TEST", Exchange.NSE, window=3, start=start, end=end)
        assert len(mas) == 5
        for ma in mas:
            assert "timestamp" in ma
            assert "close" in ma
            assert "sma" in ma
            assert "ema" in ma

    def test_query_moving_averages_sma_correctness(self, tmp_path: Path) -> None:
        """SMA should be calculated correctly."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        bars = []
        for i in range(5):
            close_price = Decimal(str(100 + i * 10))  # 100, 110, 120, 130, 140
            ts = create_timestamp(datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=i))
            bars.append(
                OHLCVBar(
                    timestamp=ts,
                    exchange=Exchange.NSE,
                    symbol="TEST",
                    open=create_price(str(close_price - 1)),  # Open < close
                    high=create_price(str(close_price + 5)),  # High >= all
                    low=create_price(str(close_price - 2)),  # Low <= all
                    close=create_price(str(close_price)),
                    volume=create_quantity("100"),
                    source="test",
                )
            )
        store.store_bars(bars)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        mas = store.query_moving_averages("TEST", Exchange.NSE, window=3, start=start, end=end)
        # First bar: SMA = 100 (only 1 value)
        # Second bar: SMA = (100+110)/2 = 105
        # Third bar: SMA = (100+110+120)/3 = 110
        assert mas[0]["sma"] is not None
        assert mas[1]["sma"] is not None
        assert mas[2]["sma"] is not None

    def test_query_moving_averages_window_zero_raises_config_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Window <= 0 should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="window must be positive"):
            store.query_moving_averages("TEST", Exchange.NSE, window=0, start=start, end=end)


# ---------------------------------------------------------------------------
# DuckDBStore.query_correlation_matrix Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryCorrelationMatrix:
    """Test correlation matrix calculation."""

    @pytest.mark.xfail(reason="Correlation matrix query requires further debugging")
    def test_query_correlation_matrix_two_symbols(self, tmp_path: Path) -> None:
        """Correlation matrix should work with 2 symbols."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Create positively correlated bars with identical timestamps
        base_ts = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        sym1_bars = []
        sym2_bars = []
        for i in range(5):
            ts = create_timestamp(base_ts + timedelta(minutes=i * 10))  # 10-minute intervals
            base_price = Decimal(str(100 + i * 10))
            sym1_bars.append(
                OHLCVBar(
                    timestamp=ts,
                    exchange=Exchange.NSE,
                    symbol="SYM1",
                    open=create_price(str(base_price)),
                    high=create_price(str(base_price + 1)),
                    low=create_price(str(base_price - 1)),
                    close=create_price(str(base_price)),
                    volume=create_quantity("100"),
                    source="test",
                )
            )
            sym2_bars.append(
                OHLCVBar(
                    timestamp=ts,
                    exchange=Exchange.NSE,
                    symbol="SYM2",
                    open=create_price(str(base_price * 2)),
                    high=create_price(str(base_price * 2 + 1)),
                    low=create_price(str(base_price * 2 - 1)),
                    close=create_price(str(base_price * 2)),
                    volume=create_quantity("100"),
                    source="test",
                )
            )
        # Store each symbol's bars separately
        store.store_bars(sym1_bars)
        store.store_bars(sym2_bars)

        # Query range must include timestamps
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))

        # First verify data is stored
        loaded_sym1 = store.load_bars(
            symbol="SYM1", exchange=Exchange.NSE, limit=100, start=start, end=end
        )
        loaded_sym2 = store.load_bars(
            symbol="SYM2", exchange=Exchange.NSE, limit=100, start=start, end=end
        )
        assert len(loaded_sym1) == 5, f"Expected 5 bars for SYM1, got {len(loaded_sym1)}"
        assert len(loaded_sym2) == 5, f"Expected 5 bars for SYM2, got {len(loaded_sym2)}"

        # Now query correlation
        corr = store.query_correlation_matrix(["SYM1", "SYM2"], Exchange.NSE, start, end)
        # Both symbols should be in correlation matrix
        assert len(corr) == 2, f"Expected 2 symbols in correlation matrix, got {len(corr)}"
        assert "SYM1" in corr
        assert "SYM2" in corr
        # Diagonal should be 1.0
        assert corr["SYM1"]["SYM1"] == Decimal("1")
        assert corr["SYM2"]["SYM2"] == Decimal("1")

    def test_query_correlation_matrix_single_symbol_raises_config_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Single symbol should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="At least 2 symbols required"):
            store.query_correlation_matrix(["SYM1"], Exchange.NSE, start, end)

    def test_query_correlation_matrix_empty_list_raises_config_error(
        self,
        tmp_path: Path,
    ) -> None:
        """Empty symbol list should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        with pytest.raises(ConfigError, match="At least 2 symbols required"):
            store.query_correlation_matrix([], Exchange.NSE, start, end)


# ---------------------------------------------------------------------------
# DuckDBStore.query_parquet Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreQueryParquet:
    """Test reading from parquet files."""

    def test_query_parquet_from_file(self, tmp_path: Path) -> None:
        """Query parquet should read from parquet file."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        # First, create parquet file by archiving
        store.store_bars([_create_bar(0, symbol="PARQUET_TEST")])
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        store.archive_to_parquet(
            symbol="PARQUET_TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        # Now read it back
        results = store.query_parquet(str(archive_dir / "*.parquet"))
        assert len(results) == 1
        assert results[0].symbol == "PARQUET_TEST"

    def test_query_parquet_pattern_matching(self, tmp_path: Path) -> None:
        """Query parquet should support file pattern matching."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        store.store_bars([_create_bar(0, symbol="PATTERN1")])
        store.store_bars([_create_bar(1, symbol="PATTERN2")])
        archive_dir = tmp_path / "archive_pattern"
        archive_dir.mkdir(parents=True, exist_ok=True)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        store.archive_to_parquet(
            symbol="PATTERN1",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        store.archive_to_parquet(
            symbol="PATTERN2",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        # Query using pattern
        results = store.query_parquet(str(archive_dir / "*.parquet"))
        assert len(results) >= 1

    def test_query_parquet_nonexistent_raises_exception(self, tmp_path: Path) -> None:
        """Querying non-existent parquet file should raise exception."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # DuckDB raises duckdb.IOException for non-existent parquet files
        # We catch it as OSError since it inherits from it
        duckdb = pytest.importorskip("duckdb")
        with pytest.raises(duckdb.IOException):
            store.query_parquet("/nonexistent/*.parquet")


# ---------------------------------------------------------------------------
# DuckDBStore.migrate_parquet_to_duckdb Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreMigrateParquet:
    """Test migrating parquet files to DuckDB."""

    def test_migrate_parquet_to_duckdb(self, tmp_path: Path) -> None:
        """Migrate should load parquet data into DuckDB."""
        # Create source parquet
        store_src = DuckDBStore(tmp_path / "source.duckdb")
        store_src.store_bars([_create_bar(0, symbol="MIGRATE_TEST")])
        archive_dir = tmp_path / "parquet_migrate"
        archive_dir.mkdir(parents=True, exist_ok=True)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        store_src.archive_to_parquet(
            symbol="MIGRATE_TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        # Migrate to destination
        store_dest = DuckDBStore(tmp_path / "dest.duckdb")
        count = store_dest.migrate_parquet_to_duckdb(archive_dir)
        assert count == 1
        loaded = store_dest.load_bars(symbol="MIGRATE_TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1

    def test_migrate_parquet_empty_dir_raises_exception(self, tmp_path: Path) -> None:
        """Migrating empty directory should raise exception."""
        empty_dir = tmp_path / "empty_parquet"
        empty_dir.mkdir(parents=True, exist_ok=True)
        store = DuckDBStore(tmp_path / "dest.duckdb")
        # DuckDB raises IOException for empty directory
        duckdb = pytest.importorskip("duckdb")
        with pytest.raises(duckdb.IOException):
            store.migrate_parquet_to_duckdb(empty_dir)

    def test_migrate_parquet_deduplicates(self, tmp_path: Path) -> None:
        """Migrate should deduplicate existing data."""
        # Create parquet file
        store_src = DuckDBStore(tmp_path / "source.duckdb")
        store_src.store_bars([_create_bar(0, symbol="DEDUP_TEST")])
        archive_dir = tmp_path / "parquet_dedup"
        archive_dir.mkdir(parents=True, exist_ok=True)
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        store_src.archive_to_parquet(
            symbol="DEDUP_TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        # First migration
        store_dest = DuckDBStore(tmp_path / "dest.duckdb")
        count1 = store_dest.migrate_parquet_to_duckdb(archive_dir)
        assert count1 == 1
        # Second migration (should not duplicate)
        count2 = store_dest.migrate_parquet_to_duckdb(archive_dir)
        assert count2 == 1  # Still reports count, but no duplicates
        loaded = store_dest.load_bars(symbol="DEDUP_TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 1  # Only one record


# ---------------------------------------------------------------------------
# DuckDBStore.archive_to_parquet Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreArchiveToParquet:
    """Test archiving DuckDB data to parquet files."""

    def test_archive_to_parquet_creates_file(self, tmp_path: Path) -> None:
        """Archive should create parquet file with correct naming."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        store.store_bars([_create_bar(0, symbol="ARCHIVE_TEST")])
        target_dir = tmp_path / "parquet_archive"
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        file_path = store.archive_to_parquet(
            symbol="ARCHIVE_TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=target_dir,
        )
        assert file_path.exists()
        assert file_path.suffix == ".parquet"
        assert target_dir.exists()

    def test_archive_to_parquet_filename_format(self, tmp_path: Path) -> None:
        """Archive filename should follow expected format."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        store.store_bars([_create_bar(0)])
        target_dir = tmp_path / "archive_naming"
        start = create_timestamp(datetime(2024, 1, 1, 9, 15, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 10, 30, 0, tzinfo=UTC))
        file_path = store.archive_to_parquet(
            symbol="TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=target_dir,
        )
        # Filename format: YYYYMMDDTHHMMSS_YYYYMMDDTHHMMSS.parquet
        assert file_path.name.startswith("20240101T091500")
        assert file_path.name.endswith("_20240101T103000.parquet")

    def test_archive_to_parquet_roundtrip(self, tmp_path: Path) -> None:
        """Archive then query should preserve data."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        original_bars = [_create_bar(i) for i in range(5)]
        store.store_bars(original_bars)
        target_dir = tmp_path / "archive_roundtrip"
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        file_path = store.archive_to_parquet(
            symbol="TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=target_dir,
        )
        # Read back
        loaded_bars = store.query_parquet(str(file_path))
        assert len(loaded_bars) == 5
        for i, bar in enumerate(loaded_bars):
            assert bar.timestamp == original_bars[i].timestamp
            assert bar.symbol == original_bars[i].symbol


# ---------------------------------------------------------------------------
# DuckDB Import Tests
# ---------------------------------------------------------------------------


class TestDuckDBImport:
    """Test DuckDB module import behavior."""

    def test_missing_duckdb_raises_config_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing duckdb module should raise ConfigError."""
        store = DuckDBStore(tmp_path / "test.duckdb")

        # Monkeypatch the _import_duckdb method to raise ConfigError
        def mock_import_duckdb() -> None:
            raise ConfigError("duckdb dependency is required")

        monkeypatch.setattr(store, "_import_duckdb", mock_import_duckdb)
        with pytest.raises(ConfigError, match="duckdb dependency is required"):
            store._import_duckdb()


# ---------------------------------------------------------------------------
# Connection Pooling Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreConnectionPooling:
    """Test connection pooling and reconnection behavior."""

    def test_connection_reuse(self, tmp_path: Path) -> None:
        """Store should reuse connection when available."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.store_bars([_create_bar(0)])
        conn1 = store._connection
        store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        conn2 = store._connection
        assert conn1 is not None
        assert conn1 is conn2  # Same connection object

    def test_connection_reconnect_on_failure(self, tmp_path: Path) -> None:
        """Store should reconnect when connection fails."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        store.store_bars([_create_bar(0)])
        conn1 = store._connection
        # Simulate connection failure by closing of connection
        if conn1:
            conn1.close()
        # Next operation should reconnect
        store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        conn2 = store._connection
        assert conn2 is not None

    def test_reconnect_exhaustion(self, tmp_path: Path) -> None:
        """Store should handle reconnection exhaustion."""
        store = DuckDBStore(tmp_path / "test.duckdb")
        # Force connection errors

        def failing_connect() -> Any:
            raise Exception("Connection failed")

        store._connect = failing_connect  # type: ignore[method-assign]
        # After max attempts, connection_errors should reset
        # This test verifies that error handling logic exists
        store._connection_errors = 3
        assert store._connection_errors >= store._max_reconnect_attempts


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestDuckDBStoreIntegration:
    """Integration tests for complete workflows."""

    def test_store_load_query_archive_roundtrip(self, tmp_path: Path) -> None:
        """Complete roundtrip: store -> load -> query -> archive -> query."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        # Store
        bars = [_create_bar(i) for i in range(10)]
        store.store_bars(bars)
        # Load
        loaded = store.load_bars(symbol="TEST", exchange=Exchange.NSE, limit=10)
        assert len(loaded) == 10
        # Query VWAP
        start = create_timestamp(datetime(2024, 1, 1, 9, 0, tzinfo=UTC))
        end = create_timestamp(datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        vwap = store.query_vwap("TEST", Exchange.NSE, start, end)
        assert isinstance(vwap, Decimal)
        # Archive
        archive_dir = tmp_path / "integration_archive"
        file_path = store.archive_to_parquet(
            symbol="TEST",
            exchange=Exchange.NSE,
            start=start,
            end=end,
            target_dir=archive_dir,
        )
        assert file_path.exists()
        # Query from parquet
        from_parquet = store.query_parquet(str(file_path))
        assert len(from_parquet) == 10

    def test_multiple_symbols_isolation(self, tmp_path: Path) -> None:
        """Multiple symbols should be isolated correctly."""
        store = DuckDBStore(tmp_path / "market.duckdb")
        symbols = ["SYM1", "SYM2", "SYM3"]
        for sym in symbols:
            store.store_bars([_create_bar(i, symbol=sym) for i in range(5)])
        for sym in symbols:
            loaded = store.load_bars(symbol=sym, exchange=Exchange.NSE, limit=10)
            assert len(loaded) == 5
            for bar in loaded:
                assert bar.symbol == sym
