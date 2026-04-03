"""
Parquet-backed archival storage for normalized OHLCV bars.
"""

import importlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar
from iatb.data.validator import validate_ohlcv_series


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


class ParquetStore:
    """Persist and query OHLCV bars in parquet partition directories."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def _import_pyarrow(self) -> tuple[Any, Any]:
        try:
            pyarrow = importlib.import_module("pyarrow")
            parquet = importlib.import_module("pyarrow.parquet")
            return pyarrow, parquet
        except ModuleNotFoundError as exc:
            msg = "pyarrow dependency is required for ParquetStore"
            raise ConfigError(msg) from exc

    def _partition_dir(self, *, symbol: str, exchange: Exchange, timeframe: str) -> Path:
        return self._root_dir / exchange.value / symbol / timeframe

    def write_bars(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        bars: list[OHLCVBar],
    ) -> Path:
        if not bars:
            msg = "bars cannot be empty"
            raise ConfigError(msg)
        validate_ohlcv_series(bars)
        partition = self._partition_dir(symbol=symbol, exchange=exchange, timeframe=timeframe)
        partition.mkdir(parents=True, exist_ok=True)
        filename = self._build_filename(bars[0].timestamp, bars[-1].timestamp)
        file_path = partition / filename
        pyarrow, parquet = self._import_pyarrow()
        table = pyarrow.table(self._bars_to_columns(bars))
        parquet.write_table(table, file_path)
        return file_path

    def read_bars(self, file_path: Path) -> list[OHLCVBar]:
        if not file_path.exists():
            msg = f"Parquet file does not exist: {file_path}"
            raise ConfigError(msg)
        _, parquet = self._import_pyarrow()
        table = parquet.read_table(file_path)
        return self._columns_to_bars(table.to_pydict())

    def list_parquet_files(self, *, symbol: str, exchange: Exchange, timeframe: str) -> list[Path]:
        partition = self._partition_dir(symbol=symbol, exchange=exchange, timeframe=timeframe)
        if not partition.exists():
            return []
        return sorted(partition.glob("*.parquet"))

    @staticmethod
    def _build_filename(start: Timestamp, end: Timestamp) -> str:
        start_part = start.strftime("%Y%m%dT%H%M%S")
        end_part = end.strftime("%Y%m%dT%H%M%S")
        return f"{start_part}_{end_part}.parquet"

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
            msg = "Parquet columns missing required OHLCV fields"
            raise ConfigError(msg)
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
