"""
DuckDB-backed OHLCV time-series storage.
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


def _normalize_timestamp(value: object) -> Timestamp:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return create_timestamp(parsed.astimezone(UTC))
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            msg = f"Invalid timestamp from DuckDB: {value!r}"
            raise ConfigError(msg) from exc
        parsed = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        return create_timestamp(parsed.astimezone(UTC))
    msg = f"Unsupported timestamp type from DuckDB: {type(value).__name__}"
    raise ConfigError(msg)


class DuckDBStore:
    """Store and query OHLCV bars in DuckDB."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _import_duckdb(self) -> Any:
        try:
            return importlib.import_module("duckdb")
        except ModuleNotFoundError as exc:
            msg = "duckdb dependency is required for DuckDBStore"
            raise ConfigError(msg) from exc

    def _connect(self) -> Any:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return self._import_duckdb().connect(str(self._db_path))

    def initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv_bars (
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    open_price TEXT NOT NULL,
                    high_price TEXT NOT NULL,
                    low_price TEXT NOT NULL,
                    close_price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    source TEXT NOT NULL
                )
                """
            )
        finally:
            connection.close()

    def store_bars(self, bars: list[OHLCVBar]) -> None:
        if not bars:
            return
        validate_ohlcv_series(bars)
        self.initialize()
        connection = self._connect()
        try:
            for bar in bars:
                connection.execute(
                    """
                    DELETE FROM ohlcv_bars
                    WHERE exchange = ? AND symbol = ? AND timestamp_utc = ? AND source = ?
                    """,
                    (bar.exchange.value, bar.symbol, bar.timestamp.isoformat(), bar.source),
                )
                connection.execute(
                    """
                    INSERT INTO ohlcv_bars (
                        exchange, symbol, timestamp_utc, open_price, high_price,
                        low_price, close_price, volume, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bar.exchange.value,
                        bar.symbol,
                        bar.timestamp.isoformat(),
                        str(bar.open),
                        str(bar.high),
                        str(bar.low),
                        str(bar.close),
                        str(bar.volume),
                        bar.source,
                    ),
                )
        finally:
            connection.close()

    def load_bars(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        start: Timestamp | None = None,
        end: Timestamp | None = None,
        limit: int = 1000,
    ) -> list[OHLCVBar]:
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        query, params = self._build_select_query(
            symbol=symbol,
            exchange=exchange,
            start=start,
            end=end,
        )
        params.append(limit)
        connection = self._connect()
        try:
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()
        return [self._row_to_ohlcv(row) for row in rows]

    @staticmethod
    def _build_select_query(
        *,
        symbol: str,
        exchange: Exchange,
        start: Timestamp | None,
        end: Timestamp | None,
    ) -> tuple[str, list[object]]:
        query = (
            "SELECT exchange, symbol, timestamp_utc, open_price, high_price, low_price, "
            "close_price, volume, source FROM ohlcv_bars WHERE symbol = ? AND exchange = ?"
        )
        params: list[object] = [symbol, exchange.value]
        if start is not None:
            params.append(start.isoformat())
            query += " AND timestamp_utc >= ?"
        if end is not None:
            params.append(end.isoformat())
            query += " AND timestamp_utc <= ?"
        query += " ORDER BY timestamp_utc ASC LIMIT ?"
        return query, params

    @staticmethod
    def _row_to_ohlcv(row: tuple[object, ...]) -> OHLCVBar:
        (
            exchange,
            symbol,
            timestamp_raw,
            open_raw,
            high_raw,
            low_raw,
            close_raw,
            volume_raw,
            source,
        ) = row
        return OHLCVBar(
            exchange=Exchange(str(exchange)),
            symbol=str(symbol),
            timestamp=_normalize_timestamp(timestamp_raw),
            open=create_price(str(open_raw)),
            high=create_price(str(high_raw)),
            low=create_price(str(low_raw)),
            close=create_price(str(close_raw)),
            volume=create_quantity(str(volume_raw)),
            source=str(source),
        )
