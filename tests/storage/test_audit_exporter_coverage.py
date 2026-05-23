"""
Coverage-augmentation tests for AuditExporter uncovered branches.

Targets:
  - _build_pdf_table_data (metadata, no-metadata, large-metadata truncation)
  - _create_pdf_table (mocked reportlab)
  - _write_pdf / export_pdf success path (mocked reportlab)
  - apply_retention_policy per-file exception handling (lines 254-255)
"""

from __future__ import annotations

import sys as _sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange, OrderSide, OrderStatus
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.storage.audit_exporter import (
    AuditExporter,
    AuditExportRecord,
    ExportConfig,
    ExportFormat,
    ExportResult,
)
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def export_config_coverage(tmp_path: Path) -> ExportConfig:
    """ExportConfig with default settings for coverage tests."""
    return ExportConfig(
        output_dir=tmp_path / "exports",
        retention_days=30,
    )


@pytest.fixture()
def records_coverage() -> list[TradeAuditRecord]:
    """Sample trade records for coverage tests."""
    base = datetime(2025, 5, 1, 10, 0, 0, tzinfo=UTC)
    records: list[TradeAuditRecord] = []
    for idx in range(2):
        records.append(
            TradeAuditRecord(
                trade_id=f"T{idx:03d}",
                timestamp=create_timestamp(base + timedelta(hours=idx)),
                exchange=Exchange.NSE,
                symbol=f"SYM{idx}",
                side=OrderSide.BUY if idx % 2 == 0 else OrderSide.SELL,
                quantity=create_quantity("100"),
                price=create_price("2500.50"),
                status=OrderStatus.FILLED,
                strategy_id="ST_A",
                metadata={"sig": f"{0.5 + idx * 0.1}"},
            )
        )
    return records


@pytest.fixture()
def store_coverage(
    tmp_path: Path, records_coverage: list[TradeAuditRecord]
) -> SQLiteStore:
    """SQLiteStore pre-populated for coverage tests."""
    db = tmp_path / "cov.sqlite"
    store = SQLiteStore(db_path=db, retention_years=7)
    store.initialize()
    for rec in records_coverage:
        store.append_trade(rec)
    return store


@pytest.fixture()
def exporter_coverage(
    store_coverage: SQLiteStore, export_config_coverage: ExportConfig
) -> AuditExporter:
    """AuditExporter instance for coverage tests."""
    return AuditExporter(store=store_coverage, config=export_config_coverage)


@pytest.fixture()
def mock_reportlab(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Mock reportlab module in sys.modules for PDF coverage tests."""
    rl_colors = ModuleType("reportlab.lib.colors")
    rl_colors.grey = "#CCCCCC"
    rl_colors.whitesmoke = "#F5F5F5"
    rl_colors.beige = "#F5F5DC"
    rl_colors.black = "#000000"

    rl_pagesizes = ModuleType("reportlab.lib.pagesizes")
    rl_pagesizes.letter = (612.0, 792.0)

    rl_styles = ModuleType("reportlab.lib.styles")
    rl_styles.getSampleStyleSheet = MagicMock(
        return_value={"Heading1": MagicMock(), "Heading2": MagicMock()}
    )

    rl_platypus = ModuleType("reportlab.platypus")

    class FakeRlTable:
        def __init__(self, data: object) -> None:
            pass

        def setStyle(self, style: object) -> None:  # noqa: N802
            pass

    rl_platypus.Table = FakeRlTable
    rl_platypus.TableStyle = MagicMock
    rl_platypus.Paragraph = MagicMock

    class FakeSimpleDocTemplate:
        def __init__(self, filename: str, pagesize: object) -> None:
            self.filename = filename

        def build(self, elements: object) -> None:
            Path(self.filename).write_bytes(b"mock pdf content")

    rl_platypus.SimpleDocTemplate = FakeSimpleDocTemplate

    rl_lib = ModuleType("reportlab.lib")
    rl_lib.colors = rl_colors
    rl_lib.pagesizes = rl_pagesizes
    rl_lib.styles = rl_styles

    rl = ModuleType("reportlab")
    rl.lib = rl_lib
    rl.platypus = rl_platypus

    monkeypatch.setitem(_sys.modules, "reportlab", rl)
    monkeypatch.setitem(_sys.modules, "reportlab.lib", rl_lib)
    monkeypatch.setitem(_sys.modules, "reportlab.lib.colors", rl_colors)
    monkeypatch.setitem(_sys.modules, "reportlab.lib.pagesizes", rl_pagesizes)
    monkeypatch.setitem(_sys.modules, "reportlab.lib.styles", rl_styles)
    monkeypatch.setitem(_sys.modules, "reportlab.platypus", rl_platypus)

    yield

    for mod_name in (
        "reportlab",
        "reportlab.lib",
        "reportlab.lib.colors",
        "reportlab.lib.pagesizes",
        "reportlab.lib.styles",
        "reportlab.platypus",
    ):
        _sys.modules.pop(mod_name, None)


class TestBuildPdfTableData:
    """Cover _build_pdf_table_data (lines 389-426)."""

    def test_with_metadata(self, exporter_coverage: AuditExporter) -> None:
        export_records = [
            AuditExportRecord(
                trade_id="T001",
                timestamp="2025-05-01T10:00:00+00:00",
                exchange="NSE",
                symbol="SYM0",
                side="BUY",
                quantity="100",
                price="2500.50",
                status="FILLED",
                strategy_id="ST_A",
                metadata={"sig": "0.5"},
            )
        ]
        exporter_coverage._config = ExportConfig(
            output_dir=exporter_coverage._config.output_dir,
            include_metadata=True,
        )
        data = exporter_coverage._build_pdf_table_data(export_records)

        assert len(data) == 2
        assert len(data[0]) == 10
        assert data[0][9] == "Metadata"
        assert data[1][0] == "T001"

    def test_without_metadata(self, exporter_coverage: AuditExporter) -> None:
        export_records = [
            AuditExportRecord(
                trade_id="T001",
                timestamp="2025-05-01T10:00:00+00:00",
                exchange="NSE",
                symbol="SYM0",
                side="BUY",
                quantity="100",
                price="2500.50",
                status="FILLED",
                strategy_id="ST_A",
            )
        ]
        exporter_coverage._config = ExportConfig(
            output_dir=exporter_coverage._config.output_dir,
            include_metadata=False,
        )
        data = exporter_coverage._build_pdf_table_data(export_records)

        assert len(data) == 2
        assert len(data[0]) == 9
        assert "Metadata" not in data[0]

    def test_metadata_none_included_but_none(
        self, exporter_coverage: AuditExporter
    ) -> None:
        export_records = [
            AuditExportRecord(
                trade_id="T001",
                timestamp="2025-05-01T10:00:00+00:00",
                exchange="NSE",
                symbol="SYM0",
                side="BUY",
                quantity="100",
                price="2500.50",
                status="FILLED",
                strategy_id="ST_A",
                metadata=None,
            )
        ]
        exporter_coverage._config = ExportConfig(
            output_dir=exporter_coverage._config.output_dir,
            include_metadata=True,
        )
        data = exporter_coverage._build_pdf_table_data(export_records)

        assert len(data) == 2
        assert data[1][9] == "None"

    def test_large_metadata_truncation(self, exporter_coverage: AuditExporter) -> None:
        large_value = "x" * 200
        export_records = [
            AuditExportRecord(
                trade_id="T001",
                timestamp="2025-05-01T10:00:00+00:00",
                exchange="NSE",
                symbol="SYM0",
                side="BUY",
                quantity="100",
                price="2500.50",
                status="FILLED",
                strategy_id="ST_A",
                metadata={"large_key": large_value},
            )
        ]
        exporter_coverage._config = ExportConfig(
            output_dir=exporter_coverage._config.output_dir,
            include_metadata=True,
        )
        data = exporter_coverage._build_pdf_table_data(export_records)

        assert len(data) == 2
        metadata_cell = data[1][9]
        assert metadata_cell.endswith("...")
        assert len(metadata_cell) == 103

    def test_metadata_short_no_truncation(
        self, exporter_coverage: AuditExporter
    ) -> None:
        export_records = [
            AuditExportRecord(
                trade_id="T001",
                timestamp="2025-05-01T10:00:00+00:00",
                exchange="NSE",
                symbol="SYM0",
                side="BUY",
                quantity="100",
                price="2500.50",
                status="FILLED",
                strategy_id="ST_A",
                metadata={"k": "v"},
            )
        ]
        exporter_coverage._config = ExportConfig(
            output_dir=exporter_coverage._config.output_dir,
            include_metadata=True,
        )
        data = exporter_coverage._build_pdf_table_data(export_records)

        assert len(data) == 2
        metadata_cell = data[1][9]
        assert not metadata_cell.endswith("...")


class TestCreatePdfTable:
    """Cover _create_pdf_table (lines 428-450)."""

    def test_creates_table_with_style(self, mock_reportlab: None) -> None:
        from iatb.storage.audit_exporter import AuditExporter

        data = [["H1", "H2"], ["v1", "v2"]]
        table = AuditExporter._create_pdf_table(data)
        assert table is not None


class TestWritePdf:
    """Cover _write_pdf success path (lines 452-493)."""

    def test_write_pdf_with_records(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        mock_reportlab: None,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports", include_metadata=True)
        exporter = AuditExporter(store=store_coverage, config=config)

        records = store_coverage.list_trades(limit=10)
        file_path = tmp_path / "exports" / "test.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        exporter._write_pdf(file_path, records)
        assert file_path.exists()

    def test_write_pdf_without_metadata(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        mock_reportlab: None,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports", include_metadata=False)
        exporter = AuditExporter(store=store_coverage, config=config)

        records = store_coverage.list_trades(limit=10)
        file_path = tmp_path / "exports" / "test_no_meta.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        exporter._write_pdf(file_path, records)
        assert file_path.exists()

    def test_write_pdf_empty_records(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        mock_reportlab: None,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports", include_metadata=True)
        exporter = AuditExporter(store=store_coverage, config=config)

        file_path = tmp_path / "exports" / "empty.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        exporter._write_pdf(file_path, [])
        assert file_path.exists()


class TestExportPdfSuccess:
    """Cover export_pdf success path (line 204)."""

    def test_export_pdf_success(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        mock_reportlab: None,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports")
        exporter = AuditExporter(store=store_coverage, config=config)

        result = exporter.export_pdf()

        assert result.success is True
        assert result.records_exported == 2
        assert result.format == ExportFormat.PDF
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.file_path.suffix == ".pdf"

    def test_export_method_pdf_override(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        mock_reportlab: None,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports", format=ExportFormat.CSV)
        exporter = AuditExporter(store=store_coverage, config=config)

        result = exporter.export(format=ExportFormat.PDF)

        assert result.success is True
        assert result.format == ExportFormat.PDF


class TestRetentionPolicyExceptionHandling:
    """Cover apply_retention_policy exception handling (lines 254-255)."""

    def test_per_file_error_does_not_block_others(
        self,
        tmp_path: Path,
        exporter_coverage: AuditExporter,
    ) -> None:
        expired = datetime.now(UTC) - timedelta(days=60)
        export_dir = exporter_coverage._output_dir

        good_file = export_dir / "good.csv"
        good_file.write_text("good")
        import os as _os

        _os.utime(good_file, (expired.timestamp(), expired.timestamp()))

        bad_file = export_dir / "bad.csv"
        bad_file.write_text("bad")
        _os.utime(bad_file, (expired.timestamp(), expired.timestamp()))

        original_unlink = Path.unlink

        def mock_unlink(path_self: Path) -> None:
            if path_self.name == "bad.csv":
                raise OSError("Permission denied")
            original_unlink(path_self)

        with patch.object(Path, "unlink", mock_unlink):
            removed = exporter_coverage.apply_retention_policy()

        assert removed == 1
        assert not good_file.exists()
        assert bad_file.exists()

    def test_stat_error_does_not_block_deletion(
        self,
        tmp_path: Path,
        exporter_coverage: AuditExporter,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        expired = datetime.now(UTC) - timedelta(days=60)
        export_dir = exporter_coverage._output_dir

        good_file = export_dir / "stat_ok.csv"
        good_file.write_text("good")
        import os as _os

        _os.utime(good_file, (expired.timestamp(), expired.timestamp()))

        bad_file = export_dir / "stat_fail.csv"
        bad_file.write_text("bad")
        _os.utime(bad_file, (expired.timestamp(), expired.timestamp()))

        original_unlink = Path.unlink

        def mock_unlink(path_self: Path) -> None:
            if path_self.name == "stat_fail.csv":
                raise OSError("Permission denied")
            original_unlink(path_self)

        monkeypatch.setattr(Path, "unlink", mock_unlink)

        removed = exporter_coverage.apply_retention_policy()

        assert removed == 1
        assert not good_file.exists()
        assert bad_file.exists()

    def test_no_files_no_error(self, exporter_coverage: AuditExporter) -> None:
        removed = exporter_coverage.apply_retention_policy()
        assert removed == 0


class TestBuildCsvRow:
    """Cover _build_csv_row (lines 292-309)."""

    def test_with_metadata_included(self, exporter_coverage: AuditExporter) -> None:
        rec = AuditExportRecord(
            trade_id="T001",
            timestamp="2025-05-01T10:00:00+00:00",
            exchange="NSE",
            symbol="SYM0",
            side="BUY",
            quantity="100",
            price="2500.50",
            status="FILLED",
            strategy_id="ST_A",
            metadata={"sig": "0.5"},
        )
        row = AuditExporter._build_csv_row(rec, include_metadata=True)
        assert row["trade_id"] == "T001"
        assert "metadata" in row

    def test_without_metadata_flag(self, exporter_coverage: AuditExporter) -> None:
        rec = AuditExportRecord(
            trade_id="T002",
            timestamp="2025-05-01T10:00:00+00:00",
            exchange="NSE",
            symbol="SYM0",
            side="BUY",
            quantity="100",
            price="2500.50",
            status="FILLED",
            strategy_id="ST_A",
            metadata={"sig": "0.5"},
        )
        row = AuditExporter._build_csv_row(rec, include_metadata=False)
        assert row["trade_id"] == "T002"
        assert "metadata" not in row

    def test_metadata_none_with_include(self, exporter_coverage: AuditExporter) -> None:
        rec = AuditExportRecord(
            trade_id="T003",
            timestamp="2025-05-01T10:00:00+00:00",
            exchange="NSE",
            symbol="SYM0",
            side="BUY",
            quantity="100",
            price="2500.50",
            status="FILLED",
            strategy_id="ST_A",
            metadata=None,
        )
        row = AuditExporter._build_csv_row(rec, include_metadata=True)
        assert row["trade_id"] == "T003"
        assert "metadata" not in row


class TestFetchRecordsTimezone:
    """Cover _fetch_records with timezone-aware start/end (lines 267-277)."""

    def test_fetch_with_timezone_aware_start(
        self, exporter_coverage: AuditExporter
    ) -> None:
        from datetime import UTC as _UTC

        start = datetime(2025, 5, 1, 9, 0, 0, tzinfo=_UTC)
        records = exporter_coverage._fetch_records(start_time=start)
        assert all(r.timestamp >= start for r in records)

    def test_fetch_with_timezone_aware_end(
        self, exporter_coverage: AuditExporter
    ) -> None:
        from datetime import UTC as _UTC

        end = datetime(2025, 5, 1, 12, 0, 0, tzinfo=_UTC)
        records = exporter_coverage._fetch_records(end_time=end)
        assert all(r.timestamp <= end for r in records)

    def test_fetch_with_both_bounds(self, exporter_coverage: AuditExporter) -> None:
        from datetime import UTC as _UTC

        start = datetime(2025, 5, 1, 9, 0, 0, tzinfo=_UTC)
        end = datetime(2025, 5, 1, 12, 0, 0, tzinfo=_UTC)
        records = exporter_coverage._fetch_records(start_time=start, end_time=end)
        assert all(start <= r.timestamp <= end for r in records)


class TestExportResultPostInit:
    """Cover ExportResult.__post_init__ (lines 69-75)."""

    def test_success_without_file_path_raises(self) -> None:
        from iatb.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="file_path required"):
            ExportResult(
                success=True,
                file_path=None,
                records_exported=10,
                format=ExportFormat.CSV,
                timestamp=create_timestamp(datetime.now(UTC)),
            )

    def test_failure_without_error_message_raises(self) -> None:
        from iatb.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="error_message required"):
            ExportResult(
                success=False,
                file_path=None,
                records_exported=0,
                format=ExportFormat.CSV,
                timestamp=create_timestamp(datetime.now(UTC)),
                error_message=None,
            )


class TestExportPdfImportError:
    """Cover _write_pdf ImportError path (lines 504-509)."""

    def test_pdf_import_error_raises_config_error(
        self,
        tmp_path: Path,
        store_coverage: SQLiteStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = ExportConfig(output_dir=tmp_path / "exports")
        exporter = AuditExporter(store=store_coverage, config=config)

        reportlab_keys = [k for k in list(_sys.modules) if k.startswith("reportlab")]
        for key in reportlab_keys:
            monkeypatch.delitem(_sys.modules, key, raising=False)

        from iatb.core.exceptions import ConfigError

        file_path = tmp_path / "exports" / "fail.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ConfigError, match="reportlab library not installed"):
            exporter._write_pdf(file_path, [])
