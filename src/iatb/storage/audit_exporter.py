"""
Audit trail exporter with multiple format support and scheduling.

Provides automated export of audit data to CSV, JSON, and PDF formats
with configurable retention policies and scheduling capabilities.
"""

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_timestamp
from iatb.storage.sqlite_store import SQLiteStore, TradeAuditRecord

if TYPE_CHECKING:
    pass


class ExportFormat(str, Enum):
    """Supported export formats for audit trails."""

    CSV = "csv"
    JSON = "json"
    PDF = "pdf"


class ScheduleFrequency(str, Enum):
    """Supported scheduling frequencies for exports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True)
class ExportConfig:
    """Configuration for audit export operations."""

    output_dir: Path
    retention_days: int = 30
    format: ExportFormat = ExportFormat.CSV
    include_metadata: bool = True
    compress: bool = False
    filename_prefix: str = "audit_export"

    def __post_init__(self) -> None:
        if self.retention_days <= 0:
            msg = "retention_days must be positive"
            raise ConfigError(msg)
        object.__setattr__(self, "output_dir", Path(self.output_dir))


@dataclass(frozen=True)
class ExportResult:
    """Result of an export operation."""

    success: bool
    file_path: Path | None
    records_exported: int
    format: ExportFormat
    timestamp: Timestamp
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.success and self.file_path is None:
            msg = "file_path required for successful export"
            raise ConfigError(msg)
        if not self.success and self.error_message is None:
            msg = "error_message required for failed export"
            raise ConfigError(msg)


@dataclass(frozen=True)
class AuditExportRecord:
    """Normalized audit record for export across all formats."""

    trade_id: str
    timestamp: str
    exchange: str
    symbol: str
    side: str
    quantity: str
    price: str
    status: str
    strategy_id: str
    metadata: dict[str, str] | None = None

    @classmethod
    def from_trade_audit_record(
        cls,
        record: TradeAuditRecord,
        include_metadata: bool = True,
    ) -> "AuditExportRecord":
        """Create export record from TradeAuditRecord."""
        return cls(
            trade_id=record.trade_id,
            timestamp=record.timestamp.isoformat(),
            exchange=record.exchange.value,
            symbol=record.symbol,
            side=record.side.value,
            quantity=str(record.quantity),
            price=str(record.price),
            status=record.status.value,
            strategy_id=record.strategy_id,
            metadata=record.metadata if include_metadata else None,
        )


class AuditExporter:
    """Export audit trail data to multiple formats with scheduling support."""

    def __init__(
        self,
        store: SQLiteStore,
        config: ExportConfig,
    ) -> None:
        """Initialize exporter with store and configuration."""
        self._store = store
        self._config = config
        self._output_dir = config.output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(  # noqa: A002
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ExportResult:
        """Export audit records to CSV format."""
        try:
            records = self._fetch_records(start_time, end_time)
            timestamp = create_timestamp(datetime.now(UTC))
            filename = self._generate_filename(ExportFormat.CSV, timestamp)
            file_path = self._output_dir / filename

            self._write_csv(file_path, records)

            return ExportResult(
                success=True,
                file_path=file_path,
                records_exported=len(records),
                format=ExportFormat.CSV,
                timestamp=timestamp,
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                file_path=None,
                records_exported=0,
                format=ExportFormat.CSV,
                timestamp=create_timestamp(datetime.now(UTC)),
                error_message=str(exc),
            )

    def export_json(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ExportResult:
        """Export audit records to JSON format."""
        try:
            records = self._fetch_records(start_time, end_time)
            timestamp = create_timestamp(datetime.now(UTC))
            filename = self._generate_filename(ExportFormat.JSON, timestamp)
            file_path = self._output_dir / filename

            self._write_json(file_path, records)

            return ExportResult(
                success=True,
                file_path=file_path,
                records_exported=len(records),
                format=ExportFormat.JSON,
                timestamp=timestamp,
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                file_path=None,
                records_exported=0,
                format=ExportFormat.JSON,
                timestamp=create_timestamp(datetime.now(UTC)),
                error_message=str(exc),
            )

    def export_pdf(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ExportResult:
        """Export audit records to PDF format (requires reportlab)."""
        try:
            records = self._fetch_records(start_time, end_time)
            timestamp = create_timestamp(datetime.now(UTC))
            filename = self._generate_filename(ExportFormat.PDF, timestamp)
            file_path = self._output_dir / filename

            self._write_pdf(file_path, records)

            return ExportResult(
                success=True,
                file_path=file_path,
                records_exported=len(records),
                format=ExportFormat.PDF,
                timestamp=timestamp,
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                file_path=None,
                records_exported=0,
                format=ExportFormat.PDF,
                timestamp=create_timestamp(datetime.now(UTC)),
                error_message=str(exc),
            )

    def export(  # noqa: A002
        self,
        format: ExportFormat | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ExportResult:
        """Export audit records using configured or specified format."""
        export_format = format or self._config.format

        if export_format == ExportFormat.CSV:
            return self.export_csv(start_time, end_time)
        elif export_format == ExportFormat.JSON:
            return self.export_json(start_time, end_time)
        else:  # noqa: RET505
            # ExportFormat.PDF is the only remaining case
            return self.export_pdf(start_time, end_time)

    def apply_retention_policy(self) -> int:
        """Remove exported files older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=self._config.retention_days)
        removed_count = 0

        for file_path in self._output_dir.iterdir():
            if not file_path.is_file():
                continue
            try:
                file_mtime = datetime.fromtimestamp(
                    file_path.stat().st_mtime,
                    tz=UTC,
                )
                if file_mtime < cutoff:
                    file_path.unlink()
                    removed_count += 1
            except Exception:  # noqa: S112
                continue

        return removed_count

    def _fetch_records(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[TradeAuditRecord]:
        """Fetch trade records from storage with optional time range."""
        records = self._store.list_trades(limit=10000)

        if start_time is not None:
            if start_time.tzinfo is None:
                msg = "start_time must be timezone-aware"
                raise ConfigError(msg)
            records = [r for r in records if r.timestamp >= start_time.astimezone(UTC)]

        if end_time is not None:
            if end_time.tzinfo is None:
                msg = "end_time must be timezone-aware"
                raise ConfigError(msg)
            records = [r for r in records if r.timestamp <= end_time.astimezone(UTC)]

        # Sort by timestamp to ensure consistent ordering
        return sorted(records, key=lambda r: r.timestamp)

    def _generate_filename(
        self,
        format: ExportFormat,
        timestamp: datetime,
    ) -> str:
        """Generate filename with timestamp and format extension."""
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"{self._config.filename_prefix}_{ts_str}.{format.value}"

    def _write_csv(
        self,
        file_path: Path,
        records: list[TradeAuditRecord],
    ) -> None:
        """Write records to CSV file."""
        export_records = [
            AuditExportRecord.from_trade_audit_record(
                r,
                self._config.include_metadata,
            )
            for r in records
        ]

        with file_path.open("w", newline="", encoding="utf-8") as f:
            if not export_records:
                writer: csv.DictWriter[str] = csv.DictWriter(f, fieldnames=[])
                writer.writeheader()
                return

            fieldnames = [
                "trade_id",
                "timestamp",
                "exchange",
                "symbol",
                "side",
                "quantity",
                "price",
                "status",
                "strategy_id",
            ]

            if self._config.include_metadata:
                fieldnames.append("metadata")

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for rec in export_records:
                row = {
                    "trade_id": rec.trade_id,
                    "timestamp": rec.timestamp,
                    "exchange": rec.exchange,
                    "symbol": rec.symbol,
                    "side": rec.side,
                    "quantity": rec.quantity,
                    "price": rec.price,
                    "status": rec.status,
                    "strategy_id": rec.strategy_id,
                }

                if self._config.include_metadata and rec.metadata:
                    row["metadata"] = json.dumps(rec.metadata)

                writer.writerow(row)

    def _write_json(
        self,
        file_path: Path,
        records: list[TradeAuditRecord],
    ) -> None:
        """Write records to JSON file."""
        export_records = [
            AuditExportRecord.from_trade_audit_record(
                r,
                self._config.include_metadata,
            )
            for r in records
        ]

        data = {
            "export_timestamp": datetime.now(UTC).isoformat(),
            "record_count": len(export_records),
            "records": [
                {
                    "trade_id": r.trade_id,
                    "timestamp": r.timestamp,
                    "exchange": r.exchange,
                    "symbol": r.symbol,
                    "side": r.side,
                    "quantity": r.quantity,
                    "price": r.price,
                    "status": r.status,
                    "strategy_id": r.strategy_id,
                    "metadata": r.metadata if self._config.include_metadata else None,
                }
                for r in export_records
            ],
        }

        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _write_pdf(
        self,
        file_path: Path,
        records: list[TradeAuditRecord],
    ) -> None:
        """Write records to PDF file using tabula or reportlab."""
        try:
            from reportlab.lib import colors  # type: ignore[import-untyped]
            from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
            from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
            from reportlab.platypus import (  # type: ignore[import-untyped]
                Paragraph,
                SimpleDocTemplate,
                Table,
                TableStyle,
            )

            export_records = [
                AuditExportRecord.from_trade_audit_record(
                    r,
                    self._config.include_metadata,
                )
                for r in records
            ]

            doc = SimpleDocTemplate(str(file_path), pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()

            title = Paragraph(
                f"Audit Trail Export - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}",
                styles["Heading1"],
            )
            elements.append(title)

            subtitle = Paragraph(
                f"Total Records: {len(export_records)}",
                styles["Heading2"],
            )
            elements.append(subtitle)

            if export_records:
                headers = [
                    "Trade ID",
                    "Timestamp",
                    "Exchange",
                    "Symbol",
                    "Side",
                    "Quantity",
                    "Price",
                    "Status",
                    "Strategy ID",
                ]

                if self._config.include_metadata:
                    headers.append("Metadata")

                data = [headers]

                for rec in export_records:
                    row = [
                        rec.trade_id,
                        rec.timestamp,
                        rec.exchange,
                        rec.symbol,
                        rec.side,
                        rec.quantity,
                        rec.price,
                        rec.status,
                        rec.strategy_id,
                    ]

                    if self._config.include_metadata:
                        metadata_str = json.dumps(rec.metadata) if rec.metadata else "None"
                        if len(metadata_str) > 100:
                            metadata_str = metadata_str[:100] + "..."
                        row.append(metadata_str)

                    data.append(row)

                table = Table(data)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                            ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ]
                    )
                )
                elements.append(table)

            doc.build(elements)

        except ImportError as exc:
            msg = "reportlab library not installed. " "Install with: pip install reportlab"
            raise ConfigError(msg) from exc
