"""
Instrument master service with SQLite-cached instrument lookups.

Parses Kite-format instrument CSV dumps and provides typed queries
for lot size, option chains, available instrument types, and expiry dates.

Memory optimization: Enforces 50MB max cache size with auto-vacuum.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError, ValidationError
from iatb.data.instrument import (
    Instrument,
    InstrumentProvider,
    InstrumentType,
    map_kite_instrument_type,
)

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(hours=24)
_MAX_CACHE_SIZE_MB = 50
_BYTES_PER_MB = 1024 * 1024

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS instruments (
    instrument_token INTEGER NOT NULL,
    exchange_token INTEGER NOT NULL,
    trading_symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    exchange TEXT NOT NULL,
    segment TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    lot_size TEXT NOT NULL,
    tick_size TEXT NOT NULL,
    strike TEXT,
    expiry TEXT,
    fetched_at_utc TEXT NOT NULL,
    PRIMARY KEY (instrument_token, exchange)
)
"""

_INSERT_SQL = """
INSERT OR REPLACE INTO instruments (
    instrument_token, exchange_token, trading_symbol, name,
    exchange, segment, instrument_type, lot_size, tick_size,
    strike, expiry, fetched_at_utc
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class InstrumentMaster:
    """Cached instrument lookup service backed by SQLite.

    Enforces 50MB max cache size with auto-vacuum to minimize memory footprint.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._db_path = cache_dir / "instruments.sqlite"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        with self._connect() as conn:
            # Enable auto-vacuum to reclaim space after deletions
            conn.execute("PRAGMA auto_vacuum = FULL;")
            conn.execute("PRAGMA page_size = 4096;")
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inst_exchange "
                "ON instruments (exchange, instrument_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inst_name " "ON instruments (name, exchange)"
            )
            conn.commit()

    def _get_db_size_mb(self) -> Decimal:
        """Get current database size in megabytes."""
        try:
            size_bytes = self._db_path.stat().st_size
            return Decimal(str(size_bytes)) / Decimal(str(_BYTES_PER_MB))
        except FileNotFoundError:
            return Decimal("0")

    def _enforce_cache_size_limit(self) -> None:
        """Enforce 50MB cache size limit by pruning oldest entries."""
        current_size_mb = self._get_db_size_mb()
        if current_size_mb <= Decimal(str(_MAX_CACHE_SIZE_MB)):
            return

        logger.warning(
            "Cache size %.2fMB exceeds limit %dMB, pruning oldest entries",
            current_size_mb,
            _MAX_CACHE_SIZE_MB,
        )

        with self._connect() as conn:
            # Delete oldest 20% of entries to reduce size
            conn.execute(
                """
                DELETE FROM instruments
                WHERE instrument_token IN (
                    SELECT instrument_token
                    FROM instruments
                    ORDER BY fetched_at_utc ASC
                    LIMIT (SELECT CAST(COUNT(*) * 0.2 AS INTEGER) FROM instruments)
                )
            """
            )
            conn.commit()
            logger.info("Pruned oldest instrument entries to enforce cache size limit")

        # Run VACUUM to reclaim space (auto-vacuum will handle this automatically)
        self._vacuum_if_needed()

    def _vacuum_if_needed(self) -> None:
        """Run VACUUM if database size is significantly above limit."""
        current_size_mb = self._get_db_size_mb()
        if current_size_mb > Decimal(str(_MAX_CACHE_SIZE_MB * 0.8)):
            logger.info("Running VACUUM to reclaim database space")
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("VACUUM;")
                conn.close()
                logger.info("VACUUM completed successfully")
            except Exception as exc:
                logger.error("VACUUM failed: %s", exc)

    def load_from_csv(self, csv_path: Path, exchange: Exchange) -> int:
        """Parse Kite-format instrument CSV and cache. Returns count loaded."""
        if not csv_path.is_file():
            msg = f"Instrument CSV not found: {csv_path}"
            raise ConfigError(msg)
        self._purge_stale()
        now_utc = datetime.now(UTC).isoformat()
        loaded = 0
        with csv_path.open(encoding="utf-8") as fh, self._connect() as conn:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    conn.execute(_INSERT_SQL, _csv_row_to_db_tuple(row, exchange, now_utc))
                    loaded += 1
                except (ValidationError, KeyError, InvalidOperation, ValueError, TypeError) as exc:
                    logger.warning("Skipping invalid CSV row: %s", exc)
        conn.commit()
        logger.info("Loaded %d instruments for %s from %s", loaded, exchange.value, csv_path)

        # Enforce cache size limit after loading
        self._enforce_cache_size_limit()
        return loaded

    async def load_from_provider(self, provider: InstrumentProvider, exchange: Exchange) -> int:
        """Fetch instruments from a broker provider and cache."""
        instruments = await provider.fetch_instruments(exchange)
        self._purge_stale()
        now_utc = datetime.now(UTC).isoformat()
        loaded = 0
        with self._connect() as conn:
            for inst in instruments:
                conn.execute(_INSERT_SQL, _instrument_to_db_tuple(inst, now_utc))
                loaded += 1
        conn.commit()
        logger.info("Loaded %d instruments for %s from provider", loaded, exchange.value)

        # Enforce cache size limit after loading
        self._enforce_cache_size_limit()
        return loaded

    def get_instrument(
        self, symbol: str, exchange: Exchange, instrument_type: InstrumentType | None = None
    ) -> Instrument:
        """Lookup a single instrument by trading symbol or name and exchange."""
        query = (
            "SELECT * FROM instruments " "WHERE (trading_symbol = ? OR name = ?) AND exchange = ?"
        )
        params: list[str] = [symbol.strip(), symbol.strip(), exchange.value]
        if instrument_type is not None:
            query += " AND instrument_type = ?"
            params.append(instrument_type.value)
        query += " LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            msg = f"Instrument not found: {symbol} on {exchange.value}"
            raise ConfigError(msg)
        return _row_to_instrument(row)

    def get_option_chain(
        self, underlying: str, exchange: Exchange, expiry: date | None = None
    ) -> list[Instrument]:
        """Get all option contracts for an underlying, optionally filtered by expiry."""
        query = (
            "SELECT * FROM instruments WHERE name = ? AND exchange = ? "
            "AND instrument_type IN ('OPTION_CE', 'OPTION_PE')"
        )
        params: list[str] = [underlying.strip(), exchange.value]
        if expiry is not None:
            query += " AND expiry = ?"
            params.append(expiry.isoformat())
        query += " ORDER BY strike ASC, instrument_type ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_instrument(r) for r in rows]

    def get_lot_size(self, symbol: str, exchange: Exchange) -> Decimal:
        """Get lot size for a specific instrument."""
        return self.get_instrument(symbol, exchange).lot_size

    def get_available_types(self, underlying: str, exchange: Exchange) -> set[InstrumentType]:
        """Get all instrument types available for an underlying on an exchange."""
        query = (
            "SELECT DISTINCT instrument_type FROM instruments "
            "WHERE (name = ? OR trading_symbol = ?) AND exchange = ?"
        )
        with self._connect() as conn:
            rows = conn.execute(query, (underlying.strip(), underlying.strip(), exchange.value))
        return {InstrumentType(str(r["instrument_type"])) for r in rows}

    def get_nearest_expiry(
        self, underlying: str, exchange: Exchange, instrument_type: InstrumentType
    ) -> date:
        """Get the nearest future expiry for an underlying and instrument type."""
        today_str = datetime.now(UTC).date().isoformat()
        query = (
            "SELECT DISTINCT expiry FROM instruments "
            "WHERE name = ? AND exchange = ? AND instrument_type = ? "
            "AND expiry >= ? ORDER BY expiry ASC LIMIT 1"
        )
        with self._connect() as conn:
            row = conn.execute(
                query,
                (underlying.strip(), exchange.value, instrument_type.value, today_str),
            ).fetchone()
        if row is None:
            msg = f"No expiry found for {underlying} {instrument_type.value} on {exchange.value}"
            raise ConfigError(msg)
        return date.fromisoformat(str(row["expiry"]))

    def _purge_stale(self) -> None:
        cutoff = (datetime.now(UTC) - _CACHE_TTL).isoformat()
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM instruments WHERE fetched_at_utc < ?", (cutoff,)
            ).rowcount
            conn.commit()
        if deleted:
            logger.info("Purged %d stale instrument records", deleted)

    def get_cache_stats(self) -> dict[str, Decimal]:
        """Get cache statistics including current size in MB."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM instruments").fetchone()
            count = int(row["count"])
        return {
            "count": Decimal(str(count)),
            "size_mb": self._get_db_size_mb(),
            "max_size_mb": Decimal(str(_MAX_CACHE_SIZE_MB)),
        }

    def get_instrument_by_token(self, instrument_token: int) -> Instrument | None:
        """Lookup an instrument by its instrument token.

        Args:
            instrument_token: The instrument token to look up.

        Returns:
            Instrument object or None if not found.
        """
        query = "SELECT * FROM instruments WHERE instrument_token = ? LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(query, (instrument_token,)).fetchone()
        if row is None:
            return None
        return _row_to_instrument(row)


def _csv_row_to_db_tuple(
    row: dict[str, str], exchange: Exchange, now_utc: str
) -> tuple[int, int, str, str, str, str, str, str, str, str | None, str | None, str]:
    inst_type = map_kite_instrument_type(row["instrument_type"])
    strike_raw = row.get("strike", "").strip()
    expiry_raw = row.get("expiry", "").strip()
    return (
        int(row["instrument_token"]),
        int(row["exchange_token"]),
        row["tradingsymbol"].strip(),
        row.get("name", "").strip(),
        exchange.value,
        row.get("segment", "").strip(),
        inst_type.value,
        row["lot_size"].strip(),
        row["tick_size"].strip(),
        strike_raw if strike_raw and strike_raw != "0" else None,
        expiry_raw if expiry_raw else None,
        now_utc,
    )


def _instrument_to_db_tuple(
    inst: Instrument, now_utc: str
) -> tuple[int, int, str, str, str, str, str, str, str, str | None, str | None, str]:
    return (
        inst.instrument_token,
        inst.exchange_token,
        inst.trading_symbol,
        inst.name,
        inst.exchange.value,
        inst.segment,
        inst.instrument_type.value,
        str(inst.lot_size),
        str(inst.tick_size),
        str(inst.strike) if inst.strike is not None else None,
        inst.expiry.isoformat() if inst.expiry is not None else None,
        now_utc,
    )


def _row_to_instrument(row: sqlite3.Row) -> Instrument:
    strike_raw = row["strike"]
    expiry_raw = row["expiry"]
    return Instrument(
        instrument_token=int(row["instrument_token"]),
        exchange_token=int(row["exchange_token"]),
        trading_symbol=str(row["trading_symbol"]),
        name=str(row["name"]),
        exchange=Exchange(str(row["exchange"])),
        segment=str(row["segment"]),
        instrument_type=InstrumentType(str(row["instrument_type"])),
        lot_size=Decimal(str(row["lot_size"])),
        tick_size=Decimal(str(row["tick_size"])),
        strike=Decimal(str(strike_raw)) if strike_raw is not None else None,
        expiry=date.fromisoformat(str(expiry_raw)) if expiry_raw is not None else None,
    )
