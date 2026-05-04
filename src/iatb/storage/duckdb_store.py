"""
DuckDB-backed OHLCV time-series storage.
"""

import importlib
from datetime import UTC, datetime
from decimal import Decimal
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
    """Store and query OHLCV bars in DuckDB with connection pooling and analytical queries."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection: Any | None = None
        self._connection_errors: int = 0
        self._max_reconnect_attempts: int = 3

    def _import_duckdb(self) -> Any:
        try:
            return importlib.import_module("duckdb")
        except ModuleNotFoundError as exc:
            msg = "duckdb dependency is required for DuckDBStore"
            raise ConfigError(msg) from exc

    def _connect(self) -> Any:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        return self._import_duckdb().connect(str(self._db_path))

    def _get_connection(self) -> Any:
        if self._connection is not None:
            try:
                self._connection.execute("SELECT 1")
                return self._connection
            except Exception:
                self._connection = None
        if self._connection_errors >= self._max_reconnect_attempts:
            self._connection_errors = 0
            self._connection = None
        self._connection = self._connect()
        self._connection_errors += 1
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:  # nosec: B110 - Intentional: cleanup failures should not raise
                pass
            finally:
                self._connection = None

    def initialize(self) -> None:
        connection = self._get_connection()
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
            if self._connection is None:
                connection.close()

    def store_bars(self, bars: list[OHLCVBar]) -> None:
        if not bars:
            return
        validate_ohlcv_series(bars)
        self.initialize()
        connection = self._get_connection()
        try:
            if bars:
                delete_params = [
                    (bar.exchange.value, bar.symbol, bar.timestamp.isoformat(), bar.source)
                    for bar in bars
                ]
                connection.executemany(
                    """
                    DELETE FROM ohlcv_bars
                    WHERE exchange = ? AND symbol = ? AND timestamp_utc = ? AND source = ?
                    """,
                    delete_params,
                )
                insert_params = [
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
                    )
                    for bar in bars
                ]
                connection.executemany(
                    """
                    INSERT INTO ohlcv_bars (
                    exchange, symbol, timestamp_utc, open_price, high_price,
                    low_price, close_price, volume, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    insert_params,
                )
        finally:
            if self._connection is None:
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
        connection = self._get_connection()
        try:
            rows = connection.execute(query, params).fetchall()
        finally:
            if self._connection is None:
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

    def query_vwap(
        self,
        symbol: str,
        exchange: Exchange,
        start: Timestamp,
        end: Timestamp,
    ) -> Decimal:
        connection = self._get_connection()
        try:
            result = connection.execute(
                """
                SELECT SUM(
                    (CAST(close_price AS DOUBLE) + CAST(high_price AS DOUBLE)
                     + CAST(low_price AS DOUBLE)) / 3 * CAST(volume AS DOUBLE)
                ) / SUM(CAST(volume AS DOUBLE)) AS vwap
                FROM ohlcv_bars
                WHERE symbol = ? AND exchange = ?
                AND timestamp_utc >= ? AND timestamp_utc <= ?
                """,
                (symbol, exchange.value, start.isoformat(), end.isoformat()),
            ).fetchone()
        finally:
            if self._connection is None:
                connection.close()
        if result is None or result[0] is None:
            msg = f"No data for VWAP calculation: {symbol} on {exchange.value}"
            raise ConfigError(msg)
        return create_price(str(result[0]))

    def query_daily_summary(
        self,
        symbol: str,
        exchange: Exchange,
        start: Timestamp,
        end: Timestamp,
    ) -> list[dict[str, Any]]:
        connection = self._get_connection()
        try:
            rows = connection.execute(
                """
                SELECT
                    DATE(timestamp_utc) AS trade_date,
                    MAX(CAST(high_price AS DOUBLE)) AS high,
                    MIN(CAST(low_price AS DOUBLE)) AS low,
                    (SELECT close_price FROM ohlcv_bars o2
                     WHERE o2.symbol = o1.symbol AND o2.exchange = o1.exchange
                     AND DATE(o2.timestamp_utc) = DATE(o1.timestamp_utc)
                     ORDER BY timestamp_utc DESC LIMIT 1) AS close,
                    (SELECT open_price FROM ohlcv_bars o3
                     WHERE o3.symbol = o1.symbol AND o3.exchange = o1.exchange
                     AND DATE(o3.timestamp_utc) = DATE(o1.timestamp_utc)
                     ORDER BY timestamp_utc ASC LIMIT 1) AS open,
                    SUM(CAST(volume AS DOUBLE)) AS volume
                FROM ohlcv_bars o1
                WHERE symbol = ? AND exchange = ?
                AND timestamp_utc >= ? AND timestamp_utc <= ?
                GROUP BY DATE(timestamp_utc)
                ORDER BY trade_date
                """,
                (symbol, exchange.value, start.isoformat(), end.isoformat()),
            ).fetchall()
        finally:
            if self._connection is None:
                connection.close()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "date": row[0],
                    "open": create_price(str(row[4])),
                    "high": create_price(str(row[1])),
                    "low": create_price(str(row[2])),
                    "close": create_price(str(row[3])),
                    "volume": create_quantity(str(row[5])),
                }
            )
        return result

    def _process_moving_average_rows(self, rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
        """Process rows from moving average query."""
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "timestamp": _normalize_timestamp(row[0]),
                    "close": create_price(str(row[1])),
                    "sma": create_price(str(row[2])) if row[2] is not None else None,
                    "ema": create_price(str(row[3])) if row[3] is not None else None,
                }
            )
        return result

    def _process_performance_rows(
        self, rows: list[tuple[Any, ...]], limit: int
    ) -> list[dict[str, Any]]:
        """Process rows from performance ranking query."""
        rankings: list[dict[str, Any]] = []
        for row in rows:
            symbol = row[0]
            end_price = row[1]
            start_price = row[2]
            if start_price is not None and end_price is not None and start_price != 0:
                return_pct = ((end_price - start_price) / start_price) * 100
                rankings.append(
                    {
                        "symbol": symbol,
                        "start_price": create_price(str(start_price)),
                        "end_price": create_price(str(end_price)),
                        "return_pct": create_price(str(return_pct)),
                    }
                )
        rankings.sort(key=lambda x: float(x["return_pct"]), reverse=True)
        return rankings[:limit]

    def query_performance_ranking(  # noqa: G10
        self,
        exchange: Exchange,
        start: Timestamp,
        end: Timestamp,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Rank symbols by performance (return %) over a period."""
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        connection = self._get_connection()
        try:
            rows = connection.execute(
                """
                SELECT
                    symbol,
                    (SELECT CAST(close_price AS DOUBLE) FROM ohlcv_bars o2
                     WHERE o2.symbol = o1.symbol AND o2.exchange = o1.exchange
                     AND o2.timestamp_utc <= ?
                     ORDER BY o2.timestamp_utc DESC LIMIT 1) AS end_price,
                    (SELECT CAST(open_price AS DOUBLE) FROM ohlcv_bars o3
                     WHERE o3.symbol = o1.symbol AND o3.exchange = o1.exchange
                     AND o3.timestamp_utc >= ?
                     ORDER BY o3.timestamp_utc ASC LIMIT 1) AS start_price
                FROM ohlcv_bars o1
                WHERE exchange = ?
                AND timestamp_utc >= ? AND timestamp_utc <= ?
                GROUP BY symbol
                """,
                (
                    end.isoformat(),
                    start.isoformat(),
                    exchange.value,
                    start.isoformat(),
                    end.isoformat(),
                ),
            ).fetchall()
        finally:
            if self._connection is None:
                connection.close()
        return self._process_performance_rows(rows, limit)

    def query_volatility(
        self,
        symbol: str,
        exchange: Exchange,
        window: int,
        start: Timestamp,
        end: Timestamp,
    ) -> list[dict[str, Any]]:
        if window <= 0:
            msg = "window must be positive"
            raise ConfigError(msg)
        connection = self._get_connection()
        try:
            rows = connection.execute(
                """
                SELECT
                    timestamp_utc,
                    CAST(close_price AS DOUBLE) AS close,
                    STDDEV(CAST(close_price AS DOUBLE)) OVER (
                        ORDER BY timestamp_utc
                        ROWS BETWEEN ? PRECEDING AND CURRENT ROW
                    ) AS rolling_stddev
                FROM ohlcv_bars
                WHERE symbol = ? AND exchange = ?
                AND timestamp_utc >= ? AND timestamp_utc <= ?
                ORDER BY timestamp_utc
                """,
                (window - 1, symbol, exchange.value, start.isoformat(), end.isoformat()),
            ).fetchall()
        finally:
            if self._connection is None:
                connection.close()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "timestamp": _normalize_timestamp(row[0]),
                    "close": create_price(str(row[1])),
                    "volatility": create_price(str(row[2])) if row[2] is not None else None,
                }
            )
        return result

    def query_correlation_matrix(  # noqa: G10
        self,
        symbols: list[str],
        exchange: Exchange,
        start: Timestamp,
        end: Timestamp,
    ) -> dict[str, dict[str, float]]:
        """Compute correlation matrix between symbols based on daily returns."""
        if len(symbols) < 2:
            msg = "At least 2 symbols required for correlation"
            raise ConfigError(msg)
        connection = self._get_connection()
        try:
            symbol_list = ", ".join("?" * len(symbols))
            rows = connection.execute(
                f"""
                SELECT
                    symbol,
                    timestamp_utc,
                    CAST(close_price AS DOUBLE) AS close
                FROM ohlcv_bars
                WHERE exchange = ?
                AND symbol IN ({symbol_list})
                AND timestamp_utc >= ? AND timestamp_utc <= ?
                ORDER BY symbol, timestamp_utc
                """,  # nosec B608: parameterized query with ? placeholders
                (*symbols, exchange.value, start.isoformat(), end.isoformat()),
            ).fetchall()
        finally:
            if self._connection is None:
                connection.close()
        pivot = self._build_price_pivot(rows)
        returns = self._compute_returns(pivot, symbols)
        return self._compute_correlation_matrix(returns)

    def _build_price_pivot(self, rows: list[tuple[Any, ...]]) -> dict[str, dict[str, float]]:
        """Build pivot table: symbol -> {timestamp: close}."""
        pivot: dict[str, dict[str, float]] = {}
        for row in rows:
            sym = row[0]
            close = float(row[2])
            if sym not in pivot:
                pivot[sym] = {}
            pivot[sym][_normalize_timestamp(row[1]).isoformat()] = close
        return pivot

    def _compute_returns(
        self, pivot: dict[str, dict[str, float]], symbols: list[str]
    ) -> dict[str, list[float]]:
        """Compute daily returns for each symbol."""
        all_timestamps: set[str] = set()
        for sym_data in pivot.values():
            all_timestamps.update(sym_data.keys())
        sorted_timestamps = sorted(all_timestamps)
        returns: dict[str, list[float]] = {}
        for sym in symbols:
            if sym not in pivot or len(pivot[sym]) < 2:
                continue
            sym_prices = [pivot[sym].get(ts) for ts in sorted_timestamps]
            sym_returns: list[float] = []
            for i in range(1, len(sym_prices)):
                prev_price = sym_prices[i - 1]
                curr_price = sym_prices[i]
                if prev_price is not None and curr_price is not None:
                    ret = (curr_price - prev_price) / prev_price
                    sym_returns.append(ret)
            if sym_returns:
                returns[sym] = sym_returns
        return returns

    def _compute_correlation_matrix(
        self, returns: dict[str, list[float]]
    ) -> dict[str, dict[str, float]]:
        """Compute covariance-based correlation matrix."""
        common_symbols = list(returns.keys())
        correlation_matrix: dict[str, dict[str, float]] = {}
        for sym1 in common_symbols:
            correlation_matrix[sym1] = {}
            for sym2 in common_symbols:
                if sym1 == sym2:
                    correlation_matrix[sym1][sym2] = 1.0
                else:
                    ret1 = returns[sym1]
                    ret2 = returns[sym2]
                    min_len = min(len(ret1), len(ret2))
                    if min_len < 2:
                        correlation_matrix[sym1][sym2] = 0.0
                    else:
                        r1 = ret1[:min_len]
                        r2 = ret2[:min_len]
                        mean1 = sum(r1) / min_len
                        mean2 = sum(r2) / min_len
                        cov = (
                            sum((r1[i] - mean1) * (r2[i] - mean2) for i in range(min_len)) / min_len
                        )
                        std1 = (sum((r - mean1) ** 2 for r in r1) / min_len) ** 0.5
                        std2 = (sum((r - mean2) ** 2 for r in r2) / min_len) ** 0.5
                        if std1 > 0 and std2 > 0:
                            correlation_matrix[sym1][sym2] = cov / (std1 * std2)
                        else:
                            correlation_matrix[sym1][sym2] = 0.0
        return correlation_matrix

    def query_parquet(self, file_pattern: str) -> list[OHLCVBar]:
        connection = self._get_connection()
        try:
            rows = connection.execute("SELECT * FROM read_parquet(?)", [file_pattern]).fetchall()
        finally:
            if self._connection is None:
                connection.close()
        return [self._row_to_ohlcv(row) for row in rows]

    def migrate_parquet_to_duckdb(self, parquet_dir: Path) -> int:
        self.initialize()
        pattern = str(parquet_dir / "*.parquet")
        connection = self._get_connection()
        try:
            count_row = connection.execute(
                "SELECT COUNT(*) FROM read_parquet(?)", [pattern]
            ).fetchone()
            row_count = int(str(count_row[0])) if count_row and count_row[0] is not None else 0
            if row_count == 0:
                return 0
            connection.execute(
                "DELETE FROM ohlcv_bars WHERE (exchange, symbol, timestamp_utc, source) IN ("
                "SELECT exchange, symbol, timestamp_utc, source FROM read_parquet(?))",
                [pattern],
            )
            connection.execute(
                "INSERT INTO ohlcv_bars SELECT * FROM read_parquet(?)",
                [pattern],
            )
        finally:
            if self._connection is None:
                connection.close()
        return row_count

    def archive_to_parquet(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        start: Timestamp,
        end: Timestamp,
        target_dir: Path,
    ) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        start_str = start.strftime("%Y%m%dT%H%M%S")
        end_str = end.strftime("%Y%m%dT%H%M%S")
        filename = f"{start_str}_{end_str}.parquet"
        file_path = target_dir / filename
        safe_path = str(file_path)
        connection = self._get_connection()
        try:
            query_str = (  # noqa: S608
                "COPY (SELECT * FROM ohlcv_bars "  # nosec B608  # noqa: S608
                "WHERE symbol = ? AND exchange = ? "
                "AND timestamp_utc >= ? AND timestamp_utc <= ? "
                "ORDER BY timestamp_utc) TO "
                f"'{safe_path}' (FORMAT 'parquet')"
            )
            connection.execute(
                query_str,
                [symbol, exchange.value, start.isoformat(), end.isoformat()],
            )
        finally:
            if self._connection is None:
                connection.close()
        return file_path
