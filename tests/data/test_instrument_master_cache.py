"""
Tests for instrument master cache size enforcement and auto-vacuum.
"""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from iatb.core.enums import Exchange
from iatb.data.instrument import Instrument, InstrumentType
from iatb.data.instrument_master import _MAX_CACHE_SIZE_MB, InstrumentMaster


class TestInstrumentMasterCacheSize:
    """Test cache size enforcement and auto-vacuum functionality."""

    def test_get_db_size_mb_empty_db(self) -> None:
        """Test getting database size for empty database."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))
            size = master._get_db_size_mb()
            assert size >= Decimal("0")
            assert size < Decimal("1")  # Empty DB should be < 1MB

    def test_get_db_size_mb_after_insert(self) -> None:
        """Test getting database size after inserting instruments."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            # Insert a test instrument
            instrument = Instrument(
                instrument_token=12345,
                exchange_token=54321,
                trading_symbol="TEST",
                name="Test Instrument",
                exchange=Exchange.NSE,
                segment="EQ",
                instrument_type=InstrumentType.EQUITY,
                lot_size=Decimal("1"),
                tick_size=Decimal("0.05"),
                strike=None,
                expiry=None,
            )

            with master._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO instruments (
                        instrument_token, exchange_token, trading_symbol, name,
                        exchange, segment, instrument_type, lot_size, tick_size,
                        strike, expiry, fetched_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        instrument.instrument_token,
                        instrument.exchange_token,
                        instrument.trading_symbol,
                        instrument.name,
                        instrument.exchange.value,
                        instrument.segment,
                        instrument.instrument_type.value,
                        str(instrument.lot_size),
                        str(instrument.tick_size),
                        str(instrument.strike) if instrument.strike else None,
                        instrument.expiry.isoformat() if instrument.expiry else None,
                        "2024-01-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

            size = master._get_db_size_mb()
            assert size > Decimal("0")
            assert size < Decimal("1")  # Single record should be < 1MB

    def test_enforce_cache_size_limit_under_limit(self) -> None:
        """Test cache size enforcement when under limit."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            # Should not raise or log warnings when under limit
            master._enforce_cache_size_limit()

            # Verify no records deleted
            with master._connect() as conn:
                count = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
            assert count == 0

    def test_enforce_cache_size_limit_at_limit(self) -> None:
        """Test cache size enforcement when at limit (simulated)."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))
            db_path = Path(tmpdir) / "instruments.sqlite"

            # Mock database file size by writing a large file
            # This simulates a database at the size limit
            with db_path.open("ab") as f:
                f.seek((_MAX_CACHE_SIZE_MB + 1) * 1024 * 1024 - 1)
                f.write(b"\0")

            # Should trigger pruning
            master._enforce_cache_size_limit()

            # Database should still exist
            assert db_path.exists()

    def test_initialize_db_sets_auto_vacuum(self) -> None:
        """Test that auto-vacuum is enabled during initialization."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            with master._connect() as conn:
                # Check auto_vacuum setting
                result = conn.execute("PRAGMA auto_vacuum").fetchone()
                assert result[0] == 1  # FULL mode

            # Re-initialize to test idempotency
            master._initialize_db()

            with master._connect() as conn:
                result = conn.execute("PRAGMA auto_vacuum").fetchone()
                assert result[0] == 1

    def test_vacuum_if_needed(self) -> None:
        """Test VACUUM execution when needed."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            # Insert some data
            with master._connect() as conn:
                conn.execute(
                    """INSERT INTO instruments (
                        instrument_token, exchange_token, trading_symbol, name,
                        exchange, segment, instrument_type, lot_size, tick_size,
                        strike, expiry, fetched_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        1,
                        1,
                        "TEST",
                        "Test",
                        "NSE",
                        "EQ",
                        "STOCK",
                        "1",
                        "0.05",
                        None,
                        None,
                        "2024-01-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

            # Vacuum should not trigger (size too small)
            master._vacuum_if_needed()

    def test_get_cache_stats(self) -> None:
        """Test getting cache statistics."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))
            stats = master.get_cache_stats()

            assert "count" in stats
            assert "size_mb" in stats
            assert "max_size_mb" in stats
            assert stats["max_size_mb"] == Decimal(str(_MAX_CACHE_SIZE_MB))
            assert stats["count"] >= 0
            assert stats["size_mb"] >= Decimal("0")

    def test_get_cache_stats_with_data(self) -> None:
        """Test getting cache statistics with actual data."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            # Insert test data
            with master._connect() as conn:
                for i in range(10):
                    conn.execute(
                        """INSERT INTO instruments (
                            instrument_token, exchange_token, trading_symbol, name,
                            exchange, segment, instrument_type, lot_size, tick_size,
                            strike, expiry, fetched_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            i,
                            i,
                            f"TEST{i}",
                            f"Test {i}",
                            "NSE",
                            "EQ",
                            "STOCK",
                            "1",
                            "0.05",
                            None,
                            None,
                            "2024-01-01T00:00:00+00:00",
                        ),
                    )
                conn.commit()

            stats = master.get_cache_stats()
            assert stats["count"] == 10
            assert stats["size_mb"] > Decimal("0")

    def test_cache_size_constants(self) -> None:
        """Test that cache size constants are properly defined."""
        assert _MAX_CACHE_SIZE_MB == 50
        assert isinstance(_MAX_CACHE_SIZE_MB, int)

    def test_commit_after_load_from_csv(self) -> None:
        """Test that load_from_csv commits changes."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            # Create a test CSV file
            csv_path = Path(tmpdir) / "test_instruments.csv"
            csv_path.write_text(
                "instrument_token,exchange_token,tradingsymbol,name,segment,instrument_type,lot_size,tick_size,strike,expiry\n"
                "12345,54321,TEST,Test Instrument,EQ,EQ,1,0.05,,\n"
            )

            master = InstrumentMaster(Path(tmpdir))
            count = master.load_from_csv(csv_path, Exchange.NSE)

            assert count > 0

            # Verify data is persisted
            with master._connect() as conn:
                result = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()
            assert result[0] > 0

    def test_commit_after_load_from_provider(self) -> None:
        """Test that load_from_provider commits changes."""
        from unittest.mock import AsyncMock, MagicMock

        from iatb.data.instrument import InstrumentProvider

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            # Create mock provider
            mock_provider = MagicMock(spec=InstrumentProvider)
            mock_provider.fetch_instruments = AsyncMock(
                return_value=[
                    Instrument(
                        instrument_token=12345,
                        exchange_token=54321,
                        trading_symbol="TEST",
                        name="Test Instrument",
                        exchange=Exchange.NSE,
                        segment="EQ",
                        instrument_type=InstrumentType.EQUITY,
                        lot_size=Decimal("1"),
                        tick_size=Decimal("0.05"),
                        strike=None,
                        expiry=None,
                    )
                ]
            )

            # Run async test
            import asyncio

            async def run_test() -> None:
                count = await master.load_from_provider(mock_provider, Exchange.NSE)
                assert count > 0

            asyncio.run(run_test())

            # Verify data is persisted
            with master._connect() as conn:
                result = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()
            assert result[0] > 0

    def test_page_size_setting(self) -> None:
        """Test that page_size is set during initialization."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:  # type: ignore[call-arg]
            master = InstrumentMaster(Path(tmpdir))

            with master._connect() as conn:
                result = conn.execute("PRAGMA page_size").fetchone()
                assert result[0] == 4096  # 4KB page size
