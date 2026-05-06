"""
Parquet-backed archival storage for normalized OHLCV bars.
"""

import importlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.data.validator import validate_ohlcv_series

logger = logging.getLogger(__name__)


class ParquetStoreError(ConfigError):
    """Raised when ParquetStore operations fail."""

    pass


def _parse_timestamp(raw_value: object) -> Timestamp:
    if isinstance(raw_value, datetime):
        parsed = raw_value if raw_value.tzinfo is not None else raw_value.replace(tzinfo=UTC)
        return create_timestamp(parsed.astimezone(UTC))
    if isinstance(raw_value, str):
        normalized = raw_value[:-1] + "+00:00" if raw_value.endswith("Z") else raw_value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            msg = f"Invalid parquet timestamp: {raw_value!r}"
            raise ConfigError(msg) from exc
        parsed = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        return create_timestamp(parsed.astimezone(UTC))
    msg = f"Unsupported parquet timestamp type: {type(raw_value).__name__}"
    raise ConfigError(msg)


def _allowed_compression(code: str) -> str:
    # https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html  # noqa: E501
    allowed: set[str] = {"NONE", "SNAPPY", "GZIP", "BROTLI", "LZ4", "ZSTD", "ZLIB"}
    if code not in allowed:
        raise ConfigError(
            f"Unsupported parquet compression '{code}'. " f"Allowed: {sorted(allowed)}"
        )
    return code


class ParquetStore:
    """Persist and query OHLCV bars in date-partitioned Parquet directories."""

    DEFAULT_COMPRESSION: Final[str] = "ZSTD"

    def __init__(self, root_dir: Path, compression: str = DEFAULT_COMPRESSION) -> None:
        self._root_dir = root_dir
        self._compression = _allowed_compression(compression)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def compression(self) -> str:
        return self._compression

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _import_pyarrow() -> tuple[Any, Any]:
        try:
            pyarrow = importlib.import_module("pyarrow")
            parquet = importlib.import_module("pyarrow.parquet")
            return pyarrow, parquet
        except ModuleNotFoundError as exc:
            msg = "pyarrow dependency is required for ParquetStore"
            raise ConfigError(msg) from exc

    def _partition_dir(self, *, symbol: str, exchange: Exchange, timeframe: str) -> Path:
        """Return the top-level partition directory for a symbol/exchange/timeframe."""
        return self._root_dir / exchange.value / symbol / timeframe

    def _date_partition_dir(
        self, *, symbol: str, exchange: Exchange, timeframe: str, when: Timestamp
    ) -> Path:
        """Return date-based partition directory: exchange/symbol/timeframe/YYYY/MM."""
        year_month = when.strftime("%Y/%m")
        return self._root_dir / exchange.value / symbol / timeframe / year_month

    @staticmethod
    def _build_filename(start: Timestamp, end: Timestamp) -> str:
        start_part = start.strftime("%Y%m%dT%H%M%S")
        end_part = end.strftime("%Y%m%dT%H%M%S")
        return f"{start_part}_{end_part}.parquet"

    # ------------------------------------------------------------------ #
    # Write / Read
    # ------------------------------------------------------------------ #

    def write_bars(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        bars: list[OHLCVBar],
    ) -> Path:
        if not bars:
            raise ConfigError("bars cannot be empty")
        validate_ohlcv_series(bars)
        partition = self._date_partition_dir(
            symbol=symbol, exchange=exchange, timeframe=timeframe, when=bars[0].timestamp
        )
        partition.mkdir(parents=True, exist_ok=True)
        filename = self._build_filename(bars[0].timestamp, bars[-1].timestamp)
        file_path = partition / filename
        pyarrow, parquet = self._import_pyarrow()
        table = pyarrow.table(self._bars_to_columns(bars))
        parquet.write_table(table, file_path, compression=self._compression)
        logger.info("Wrote %d bars to %s (compression=%s)", len(bars), file_path, self._compression)
        return file_path

    def read_bars(self, file_path: Path) -> list[OHLCVBar]:
        if not file_path.exists():
            raise ConfigError(f"Parquet file does not exist: {file_path}")
        _, parquet = self._import_pyarrow()
        table = parquet.read_table(file_path)
        return self._columns_to_bars(table.to_pydict())

    # ------------------------------------------------------------------ #
    # Listing
    # ------------------------------------------------------------------ #

    def list_parquet_files(self, *, symbol: str, exchange: Exchange, timeframe: str) -> list[Path]:
        partition = self._partition_dir(symbol=symbol, exchange=exchange, timeframe=timeframe)
        if not partition.exists():
            return []
        return sorted(partition.rglob("*.parquet"))

    def _list_parquet_files_between(
        self, *, symbol: str, exchange: Exchange, timeframe: str, start: datetime, end: datetime
    ) -> list[Path]:
        """List parquet files whose partition month overlaps with [start, end]."""
        all_files = self.list_parquet_files(symbol=symbol, exchange=exchange, timeframe=timeframe)
        if not all_files:
            return []

        start_year_month = (start.year, start.month)
        end_year_month = (end.year, end.month)

        selected: list[Path] = []
        for file_path in all_files:
            parts = file_path.relative_to(self._root_dir).parts
            if len(parts) >= 5:
                try:
                    file_year = int(parts[3])
                    file_month = int(parts[4])
                    file_year_month = (file_year, file_month)
                    if start_year_month <= file_year_month <= end_year_month:
                        selected.append(file_path)
                except (ValueError, IndexError):
                    continue
        return selected

    # ------------------------------------------------------------------ #
    # Range queries
    # ------------------------------------------------------------------ #

    def read_bars_range(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Query bars across date-spanning Parquet partitions."""
        if not start.tzinfo or not end.tzinfo:
            raise ConfigError("start and end must be timezone-aware datetimes")
        if end <= start:
            raise ConfigError("end must be after start")

        pyarrow, parquet = self._import_pyarrow()
        file_paths = self._list_parquet_files_between(
            symbol=symbol, exchange=exchange, timeframe=timeframe, start=start, end=end
        )
        if not file_paths:
            return []

        all_bars: list[OHLCVBar] = []
        for file_path in file_paths:
            try:
                table = parquet.read_table(file_path)
                columns = table.to_pydict()
                file_bars = self._columns_to_bars(columns)
                for bar in file_bars:
                    if start <= bar.timestamp <= end:
                        all_bars.append(bar)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to read %s: %s", file_path, exc)
                continue

        all_bars.sort(key=lambda b: b.timestamp)
        if all_bars:
            validate_ohlcv_series(all_bars)
        return all_bars

    # ------------------------------------------------------------------ #
    # Retention
    # ------------------------------------------------------------------ #

    def cleanup_older_than(self, *, days: int) -> list[Path]:
        """Delete parquet files whose newest bar is older than *days* from now."""
        if days < 0:
            raise ConfigError("days must be non-negative")

        cutoff = datetime.now(UTC) - timedelta(days=days)
        deleted: list[Path] = []

        for file_path in self._root_dir.rglob("*.parquet"):
            try:
                parquet_mod = importlib.import_module("pyarrow.parquet")
                table = parquet_mod.read_table(file_path)
                ta = table.column("timestamp_utc")
                ts_values = list(ta.to_pylist())
                if not ts_values:
                    continue
                newest_str = ts_values[-1]
                newest_ts = _parse_timestamp(newest_str)
                if newest_ts < cutoff:
                    file_path.unlink()
                    deleted.append(file_path)
                    logger.info("Deleted archived file (age > %d days): %s", days, file_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping cleanup for %s: %s", file_path, exc)
                continue

        return deleted

    # ------------------------------------------------------------------ #
    # Column conversion helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _bars_to_columns(bars: list[OHLCVBar]) -> dict[str, list[str]]:
        return {
            "exchange": [bar.exchange.value for bar in bars],
            "symbol": [bar.symbol for bar in bars],
            "timestamp_utc": [bar.timestamp.isoformat() for bar in bars],
            "open_price": [str(bar.open) for bar in bars],
            "high_price": [str(bar.high) for bar in bars],
            "low_price": [str(bar.low) for bar in bars],
            "close_price": [str(bar.close) for bar in bars],
            "volume": [str(bar.volume) for bar in bars],
            "source": [bar.source for bar in bars],
        }

    @staticmethod
    def _columns_to_bars(columns: dict[str, list[object]]) -> list[OHLCVBar]:
        required = {
            "exchange",
            "symbol",
            "timestamp_utc",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "source",
        }
        if required - columns.keys():
            raise ConfigError("Parquet columns missing required OHLCV fields")
        total_rows = len(columns["timestamp_utc"])
        return [ParquetStore._build_bar_from_columns(columns, index) for index in range(total_rows)]

    @staticmethod
    def _build_bar_from_columns(columns: dict[str, list[object]], index: int) -> OHLCVBar:
        return OHLCVBar(
            exchange=Exchange(str(columns["exchange"][index])),
            symbol=str(columns["symbol"][index]),
            timestamp=_parse_timestamp(columns["timestamp_utc"][index]),
            open=create_price(str(columns["open_price"][index])),
            high=create_price(str(columns["high_price"][index])),
            low=create_price(str(columns["low_price"][index])),
            close=create_price(str(columns["close_price"][index])),
            volume=create_quantity(str(columns["volume"][index])),
            source=str(columns["source"][index]),
        )
