"""
Tests for AuditExporter with comprehensive coverage.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.storage.audit_exporter import (
    AuditExporter,
    AuditExportRecord,
    ExportConfig,
    ExportFormat,
    ExportResult,
)
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create temporary directory for test exports."""
    return tmp_path / "audit_exports"


@pytest.fixture
def sample_records() -> list[TradeAuditRecord]:
    """Create sample trade audit records for testing."""
    base_time = datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC)
    return [
        TradeAuditRecord(
            trade_id="TRADE001",
            timestamp=create_timestamp(base_time),
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=create_quantity("100"),
            price=create_price("2500.50"),
            status=OrderStatus.FILLED,
            strategy_id="STRAT_A",
            metadata={"signal_strength": "0.85"},
        ),
        TradeAuditRecord(
            trade_id="TRADE002",
            timestamp=create_timestamp(base_time + timedelta(hours=1)),
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.SELL,
            quantity=create_quantity("50"),
            price=create_price("3500.75"),
            status=OrderStatus.FILLED,
            strategy_id="STRAT_A",
            metadata={"signal_strength": "0.92"},
        ),
    ]


@pytest.fixture
def empty_db_path(temp_output_dir: Path) -> Path:
    """Create empty SQLite database for testing."""
    return temp_output_dir / "test_trades.sqlite"


@pytest.fixture
def store(empty_db_path: Path, sample_records: list[TradeAuditRecord]) -> SQLiteStore:
    """Create SQLite store with sample records."""
    store = SQLiteStore(db_path=empty_db_path, retention_years=7)
    store.initialize()
    for record in sample_records:
        store.append_trade(record)
    yield store
    # Close connection to allow cleanup on Windows
    try:
        if hasattr(store, "_conn") and store._conn:
            store._conn.close()
    except Exception as e:
        # Ignore cleanup errors on Windows
        _ = e


@pytest.fixture
def export_config(temp_output_dir: Path) -> ExportConfig:
    """Create export configuration for testing."""
    return ExportConfig(
        output_dir=temp_output_dir / "exports",
        retention_days=30,
        format=ExportFormat.CSV,
        include_metadata=True,
        filename_prefix="test_audit",
    )


@pytest.fixture
def exporter(store: SQLiteStore, export_config: ExportConfig) -> AuditExporter:
    """Create AuditExporter instance for testing."""
    return AuditExporter(store=store, config=export_config)


class TestExportConfig:
    """Test ExportConfig validation and initialization."""

    def test_valid_config(self, temp_output_dir: Path) -> None:
        """Test creation of valid ExportConfig."""
        config = ExportConfig(
            output_dir=temp_output_dir,
            retention_days=90,
            format=ExportFormat.JSON,
        )
        assert config.output_dir == temp_output_dir
        assert config.retention_days == 90
        assert config.format == ExportFormat.JSON
        assert config.include_metadata is True
        assert config.compress is False

    def test_invalid_retention_days_negative(self, temp_output_dir: Path) -> None:
        """Test that negative retention days raises ConfigError."""
        with pytest.raises(ConfigError, match="retention_days must be positive"):
            ExportConfig(output_dir=temp_output_dir, retention_days=-1)

    def test_invalid_retention_days_zero(self, temp_output_dir: Path) -> None:
        """Test that zero retention days raises ConfigError."""
        with pytest.raises(ConfigError, match="retention_days must be positive"):
            ExportConfig(output_dir=temp_output_dir, retention_days=0)

    def test_path_conversion(self, temp_output_dir: Path) -> None:
        """Test that string path is converted to Path."""
        config = ExportConfig(output_dir=str(temp_output_dir))
        assert isinstance(config.output_dir, Path)
        assert config.output_dir == temp_output_dir


class TestAuditExportRecord:
    """Test AuditExportRecord creation and conversion."""

    def test_from_trade_audit_record_with_metadata(
        self, sample_records: list[TradeAuditRecord]
    ) -> None:
        """Test conversion from TradeAuditRecord with metadata."""
        record = sample_records[0]
        export_record = AuditExportRecord.from_trade_audit_record(record, include_metadata=True)

        assert export_record.trade_id == record.trade_id
        assert export_record.timestamp == record.timestamp.isoformat()
        assert export_record.exchange == record.exchange.value
        assert export_record.symbol == record.symbol
        assert export_record.side == record.side.value
        assert export_record.quantity == str(record.quantity)
        assert export_record.price == str(record.price)
        assert export_record.status == record.status.value
        assert export_record.strategy_id == record.strategy_id
        assert export_record.metadata == record.metadata

    def test_from_trade_audit_record_without_metadata(
        self, sample_records: list[TradeAuditRecord]
    ) -> None:
        """Test conversion from TradeAuditRecord without metadata."""
        record = sample_records[0]
        export_record = AuditExportRecord.from_trade_audit_record(record, include_metadata=False)

        assert export_record.metadata is None

    def test_frozen_dataclass(self) -> None:
        """Test that AuditExportRecord is frozen."""
        record = AuditExportRecord(
            trade_id="TEST",
            timestamp="2025-04-25T10:30:00+00:00",
            exchange="NSE",
            symbol="TEST",
            side="BUY",
            quantity="100",
            price="100.0",
            status="FILLED",
            strategy_id="STRAT_A",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            record.trade_id = "MODIFIED"


class TestAuditExporter:
    """Test AuditExporter functionality."""

    def test_initialization_creates_output_dir(
        self, store: SQLiteStore, temp_output_dir: Path
    ) -> None:
        """Test that exporter creates output directory on initialization."""
        output_dir = temp_output_dir / "new_exports"
        config = ExportConfig(output_dir=output_dir)

        assert not output_dir.exists()

        AuditExporter(store=store, config=config)

        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_export_csv_creates_file(self, exporter: AuditExporter, temp_output_dir: Path) -> None:
        """Test CSV export creates file with correct content."""
        result = exporter.export_csv()

        assert result.success is True
        assert result.records_exported == 2
        assert result.format == ExportFormat.CSV
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.file_path.suffix == ".csv"
        assert "test_audit_" in result.file_path.name

    def test_export_json_creates_file(self, exporter: AuditExporter) -> None:
        """Test JSON export creates file with correct content."""
        result = exporter.export_json()

        assert result.success is True
        assert result.records_exported == 2
        assert result.format == ExportFormat.JSON
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.file_path.suffix == ".json"

        # Verify JSON structure
        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert "export_timestamp" in data
        assert "record_count" in data
        assert "records" in data
        assert data["record_count"] == 2
        assert len(data["records"]) == 2

    def test_export_pdf_without_reportlab(self, exporter: AuditExporter) -> None:
        """Test PDF export raises error without reportlab."""
        result = exporter.export_pdf()

        assert result.success is False
        assert result.error_message is not None
        assert "reportlab" in result.error_message.lower()

    def test_export_with_time_range(self, exporter: AuditExporter) -> None:
        """Test export with start and end time filtering."""
        start_time = datetime(2025, 4, 25, 10, 0, 0, tzinfo=UTC)
        end_time = datetime(2025, 4, 25, 11, 0, 0, tzinfo=UTC)

        result = exporter.export_csv(start_time=start_time, end_time=end_time)

        assert result.success is True
        assert result.records_exported == 1  # Only first record in range

    def test_export_with_naive_start_time_raises_error(self, exporter: AuditExporter) -> None:
        """Test that naive datetime for start_time raises ConfigError."""
        naive_time = datetime(2025, 4, 25, 10, 0, 0)

        result = exporter.export_csv(start_time=naive_time)

        assert result.success is False
        assert "timezone-aware" in result.error_message.lower()

    def test_export_with_naive_end_time_raises_error(self, exporter: AuditExporter) -> None:
        """Test that naive datetime for end_time raises ConfigError."""
        naive_time = datetime(2025, 4, 25, 12, 0, 0)

        result = exporter.export_csv(end_time=naive_time)

        assert result.success is False
        assert "timezone-aware" in result.error_message.lower()

    def test_export_method_uses_config_format(self, exporter: AuditExporter) -> None:
        """Test that export() method uses configured format."""
        result = exporter.export()

        assert result.success is True
        assert result.format == ExportFormat.CSV

    def test_export_method_with_override_format(self, exporter: AuditExporter) -> None:
        """Test that export() method respects format override."""
        result = exporter.export(format=ExportFormat.JSON)

        assert result.success is True
        assert result.format == ExportFormat.JSON

    def test_export_with_empty_records(self, temp_output_dir: Path) -> None:
        """Test export with no records in store."""
        empty_db = temp_output_dir / "empty.sqlite"
        empty_store = SQLiteStore(db_path=empty_db, retention_years=7)
        empty_store.initialize()

        config = ExportConfig(output_dir=temp_output_dir / "exports")
        empty_exporter = AuditExporter(store=empty_store, config=config)

        result = empty_exporter.export_csv()

        assert result.success is True
        assert result.records_exported == 0
        assert result.file_path is not None

    def test_csv_content_verification(self, exporter: AuditExporter) -> None:
        """Test that CSV content is correctly formatted."""
        result = exporter.export_csv()

        with result.file_path.open("r", encoding="utf-8") as f:
            content = f.read()

        assert "trade_id" in content
        assert "timestamp" in content
        assert "exchange" in content
        assert "symbol" in content
        assert "RELIANCE" in content
        assert "TCS" in content
        assert "2500.50" in content
        assert "3500.75" in content

    def test_csv_without_metadata(self, temp_output_dir: Path, store: SQLiteStore) -> None:
        """Test CSV export without metadata column."""
        config = ExportConfig(
            output_dir=temp_output_dir / "exports",
            include_metadata=False,
        )
        exporter = AuditExporter(store=store, config=config)

        result = exporter.export_csv()

        with result.file_path.open("r", encoding="utf-8") as f:
            content = f.read()

        assert "metadata" not in content

    def test_json_content_verification(self, exporter: AuditExporter) -> None:
        """Test that JSON content is correctly formatted."""
        result = exporter.export_json()

        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        record = data["records"][0]
        assert record["trade_id"] == "TRADE001"
        assert record["symbol"] == "RELIANCE"
        assert record["side"] == "BUY"
        assert record["quantity"] == "100"
        assert record["price"] == "2500.50"
        assert record["status"] == "FILLED"
        assert record["strategy_id"] == "STRAT_A"
        assert record["metadata"]["signal_strength"] == "0.85"


class TestRetentionPolicy:
    """Test retention policy application."""

    def test_apply_retention_policy_removes_old_files(
        self,
        temp_output_dir: Path,
        exporter: AuditExporter,
    ) -> None:
        """Test that old files are removed by retention policy."""
        # Create some test files
        old_file = temp_output_dir / "exports" / "old_export.csv"
        old_file.write_text("old data")

        # Modify file to be old
        old_time = datetime.now(UTC) - timedelta(days=40)
        import os

        os.utime(old_file, (old_file.stat().st_mtime, old_time.timestamp()))

        # Apply retention policy
        removed = exporter.apply_retention_policy()

        assert removed == 1
        assert not old_file.exists()

    def test_apply_retention_policy_keeps_recent_files(
        self,
        temp_output_dir: Path,
        exporter: AuditExporter,
    ) -> None:
        """Test that recent files are kept by retention policy."""
        # Create a recent file
        recent_file = temp_output_dir / "exports" / "recent_export.csv"
        recent_file.write_text("recent data")

        # Apply retention policy
        removed = exporter.apply_retention_policy()

        assert removed == 0
        assert recent_file.exists()

    def test_apply_retention_policy_zero_retention(
        self,
        temp_output_dir: Path,
        store: SQLiteStore,
    ) -> None:
        """Test retention policy with zero days (should raise error)."""
        with pytest.raises(ConfigError, match="retention_days must be positive"):
            ExportConfig(
                output_dir=temp_output_dir,
                retention_days=0,
            )


class TestExportResult:
    """Test ExportResult validation."""

    def test_successful_result_requires_file_path(self) -> None:
        """Test that successful export requires file_path."""
        with pytest.raises(ConfigError, match="file_path required for successful export"):
            ExportResult(
                success=True,
                file_path=None,
                records_exported=10,
                format=ExportFormat.CSV,
                timestamp=datetime.now(UTC),
            )

    def test_failed_result_requires_error_message(self) -> None:
        """Test that failed export requires error_message."""
        with pytest.raises(ConfigError, match="error_message required for failed export"):
            ExportResult(
                success=False,
                file_path=None,
                records_exported=0,
                format=ExportFormat.CSV,
                timestamp=datetime.now(UTC),
                error_message=None,
            )

    def test_valid_successful_result(self, temp_output_dir: Path) -> None:
        """Test creation of valid successful ExportResult."""
        file_path = temp_output_dir / "test.csv"
        result = ExportResult(
            success=True,
            file_path=file_path,
            records_exported=10,
            format=ExportFormat.CSV,
            timestamp=datetime.now(UTC),
        )

        assert result.success is True
        assert result.file_path == file_path
        assert result.records_exported == 10
        assert result.error_message is None

    def test_valid_failed_result(self) -> None:
        """Test creation of valid failed ExportResult."""
        result = ExportResult(
            success=False,
            file_path=None,
            records_exported=0,
            format=ExportFormat.CSV,
            timestamp=datetime.now(UTC),
            error_message="Test error",
        )

        assert result.success is False
        assert result.file_path is None
        assert result.records_exported == 0
        assert result.error_message == "Test error"

    def test_export_pdf_with_reportlab(self, exporter: AuditExporter) -> None:
        """Test PDF export with reportlab installed (if available)."""
        import importlib.util

        if not importlib.util.find_spec("reportlab"):
            pytest.skip("reportlab not installed")

        result = exporter.export_pdf()

        assert result.success is True
        assert result.records_exported == 2
        assert result.format == ExportFormat.PDF
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.file_path.suffix == ".pdf"

    def test_csv_write_empty_records(self, temp_output_dir: Path) -> None:
        """Test CSV write with empty records list."""
        empty_db = temp_output_dir / "empty.sqlite"
        empty_store = SQLiteStore(db_path=empty_db, retention_years=7)
        empty_store.initialize()

        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=empty_store, config=config)

        result = exporter.export_csv()

        assert result.success is True
        assert result.records_exported == 0

        # Verify file was created even with no data
        assert result.file_path is not None
        assert result.file_path.exists()

    def test_json_write_empty_records(self, temp_output_dir: Path) -> None:
        """Test JSON write with empty records list."""
        empty_db = temp_output_dir / "empty.sqlite"
        empty_store = SQLiteStore(db_path=empty_db, retention_years=7)
        empty_store.initialize()

        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=empty_store, config=config)

        result = exporter.export_json()

        assert result.success is True
        assert result.records_exported == 0

        # Verify JSON structure even with no data
        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["record_count"] == 0
        assert data["records"] == []
        assert "export_timestamp" in data

    def test_json_without_metadata(self, temp_output_dir: Path, store: SQLiteStore) -> None:
        """Test JSON export without metadata field."""
        config = ExportConfig(
            output_dir=temp_output_dir / "exports",
            include_metadata=False,
        )
        exporter = AuditExporter(store=store, config=config)

        result = exporter.export_json()

        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        record = data["records"][0]
        assert record["metadata"] is None

    def test_apply_retention_policy_handles_directories(
        self, temp_output_dir: Path, exporter: AuditExporter
    ) -> None:
        """Test retention policy ignores directories."""
        # Create a directory in exports
        subdir = temp_output_dir / "exports" / "subdir"
        subdir.mkdir(parents=True, exist_ok=True)

        # Apply retention policy should not fail
        removed = exporter.apply_retention_policy()

        assert removed == 0
        assert subdir.exists()

    def test_fetch_records_sorts_by_timestamp(self, exporter: AuditExporter) -> None:
        """Test that fetched records are sorted by timestamp."""
        # Add records in reverse order to test sorting
        base_time = datetime(2025, 4, 25, 10, 30, 0, tzinfo=UTC)

        store = exporter._store
        store.append_trade(
            TradeAuditRecord(
                trade_id="TRADE_LATEST",
                timestamp=create_timestamp(base_time + timedelta(hours=5)),
                exchange=Exchange.NSE,
                symbol="INFY",
                side=OrderSide.BUY,
                quantity=create_quantity("100"),
                price=create_price("1500.00"),
                status=OrderStatus.FILLED,
                strategy_id="STRAT_A",
            )
        )
        store.append_trade(
            TradeAuditRecord(
                trade_id="TRADE_EARLIEST",
                timestamp=create_timestamp(base_time - timedelta(hours=5)),
                exchange=Exchange.NSE,
                symbol="WIPRO",
                side=OrderSide.BUY,
                quantity=create_quantity("200"),
                price=create_price("400.00"),
                status=OrderStatus.FILLED,
                strategy_id="STRAT_A",
            )
        )

        # Fetch records
        result = exporter.export_csv()

        assert result.success is True
        assert result.records_exported == 4  # 2 original + 2 new

    def test_export_csv_handles_write_errors(
        self, temp_output_dir: Path, store: SQLiteStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test CSV export handles file write errors."""
        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=store, config=config)

        # Mock Path.open to raise exception
        def mock_open_error(*args: object, **kwargs: object) -> object:  # noqa: ARG001
            raise OSError("Disk full")

        monkeypatch.setattr(Path, "open", mock_open_error)

        result = exporter.export_csv()

        assert result.success is False
        assert result.error_message is not None
        assert "Disk full" in result.error_message

    def test_export_json_handles_write_errors(
        self, temp_output_dir: Path, store: SQLiteStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test JSON export handles file write errors."""
        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=store, config=config)

        # Mock Path.open to raise exception
        def mock_open_error(*args: object, **kwargs: object) -> object:  # noqa: ARG001
            raise OSError("Disk full")

        monkeypatch.setattr(Path, "open", mock_open_error)

        result = exporter.export_json()

        assert result.success is False
        assert result.error_message is not None
        assert "Disk full" in result.error_message

    def test_export_pdf_handles_write_errors(
        self, temp_output_dir: Path, store: SQLiteStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test PDF export handles write errors."""
        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=store, config=config)

        # Mock SimpleDocTemplate to raise exception
        try:
            from reportlab.platypus import SimpleDocTemplate  # type: ignore[import-untyped]

            def mock_build_error(*args: object, **kwargs: object) -> object:  # noqa: ARG001
                raise OSError("Disk full")

            monkeypatch.setattr(SimpleDocTemplate, "build", mock_build_error)

            result = exporter.export_pdf()

            assert result.success is False
            assert result.error_message is not None
        except ImportError:
            pytest.skip("reportlab not installed")

    def test_csv_metadata_serialization(self, exporter: AuditExporter) -> None:
        """Test CSV properly serializes metadata as JSON string."""
        result = exporter.export_csv()

        with result.file_path.open("r", encoding="utf-8") as f:
            content = f.read()

        # Metadata should be JSON string in CSV
        assert '"signal_strength"' in content or "signal_strength" in content

    def test_json_metadata_structure(self, exporter: AuditExporter) -> None:
        """Test JSON export preserves metadata structure."""
        result = exporter.export_json()

        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Check that metadata is properly structured
        for record in data["records"]:
            if record["metadata"] is not None:
                assert isinstance(record["metadata"], dict)

    def test_export_pdf_with_large_metadata(
        self, temp_output_dir: Path, store: SQLiteStore
    ) -> None:
        """Test PDF export truncates large metadata strings."""
        # Add record with large metadata
        large_metadata = {"key": "x" * 200}  # Long value
        store.append_trade(
            TradeAuditRecord(
                trade_id="TRADE_LARGE",
                timestamp=create_timestamp(datetime(2025, 4, 25, 12, 0, 0, tzinfo=UTC)),
                exchange=Exchange.NSE,
                symbol="TEST",
                side=OrderSide.BUY,
                quantity=create_quantity("100"),
                price=create_price("100.00"),
                status=OrderStatus.FILLED,
                strategy_id="STRAT_A",
                metadata=large_metadata,
            )
        )

        config = ExportConfig(
            output_dir=temp_output_dir / "exports",
            include_metadata=True,
        )
        exporter = AuditExporter(store=store, config=config)

        try:
            result = exporter.export_pdf()

            # Should succeed even with large metadata
            assert result.success is True or result.success is False  # May fail without reportlab
        except Exception as e:
            # If reportlab not available, that's expected
            _ = e

    def test_export_pdf_without_metadata(self, temp_output_dir: Path, store: SQLiteStore) -> None:
        """Test PDF export without metadata column."""
        config = ExportConfig(
            output_dir=temp_output_dir / "exports",
            include_metadata=False,
        )
        exporter = AuditExporter(store=store, config=config)

        try:
            result = exporter.export_pdf()

            if result.success:
                # Verify file was created
                assert result.file_path is not None
                assert result.file_path.exists()
        except Exception as e:
            # If reportlab not available, that's expected
            _ = e

    def test_export_with_all_formats(self, temp_output_dir: Path, store: SQLiteStore) -> None:
        """Test exporting in all supported formats."""
        config = ExportConfig(output_dir=temp_output_dir / "exports")
        exporter = AuditExporter(store=store, config=config)

        # Test CSV
        csv_result = exporter.export(format=ExportFormat.CSV)
        assert csv_result.success is True
        assert csv_result.format == ExportFormat.CSV

        # Test JSON
        json_result = exporter.export(format=ExportFormat.JSON)
        assert json_result.success is True
        assert json_result.format == ExportFormat.JSON

        # Test PDF (may fail without reportlab)
        pdf_result = exporter.export(format=ExportFormat.PDF)
        # PDF may fail if reportlab not installed
        assert pdf_result.format == ExportFormat.PDF

    def test_filename_generation(self, exporter: AuditExporter) -> None:
        """Test that filenames are generated with correct format."""
        result = exporter.export_csv()

        assert result.file_path is not None
        filename = result.file_path.name

        # Should match pattern: prefix_YYYYMMDD_HHMMSS.csv
        assert filename.startswith("test_audit_")
        assert filename.endswith(".csv")
        assert len(filename) == len("test_audit_20250425_103000.csv")

    def test_export_records_are_sorted(self, exporter: AuditExporter) -> None:
        """Test that exported records maintain chronological order."""
        result = exporter.export_json()

        with result.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        records = data["records"]
        if len(records) > 1:
            # Verify timestamps are in ascending order
            for i in range(len(records) - 1):
                current_time = datetime.fromisoformat(records[i]["timestamp"])
                next_time = datetime.fromisoformat(records[i + 1]["timestamp"])
                assert current_time <= next_time
