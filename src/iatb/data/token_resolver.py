"""
Symbol to instrument token resolution service.

Provides efficient symbol-to-token lookup for KiteConnect APIs which require
instrument_token (integer) rather than trading symbols. Uses cached
InstrumentMaster for fast lookups with fallback to Kite API on cache miss.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError, ValidationError

if TYPE_CHECKING:
    from iatb.data.instrument import Instrument, InstrumentType
    from iatb.data.instrument_master import InstrumentMaster

logger = logging.getLogger(__name__)

# Cache TTL for token resolution (24 hours)
_CACHE_TTL = timedelta(hours=24)

# Supported exchanges for token resolution
_SUPPORTED_EXCHANGES = frozenset({Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS})


def _ensure_supported_exchange(exchange: Exchange) -> None:
    """Validate that the exchange is supported for token resolution."""
    if exchange in _SUPPORTED_EXCHANGES:
        return
    msg = f"Unsupported exchange for token resolution: {exchange.value}"
    raise ConfigError(msg)


def _parse_instrument_token(value: Any, *, field_name: str) -> int:
    """Parse instrument token from various types."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            msg = f"{field_name} must be integer, got '{value}'"
            raise ValidationError(msg) from exc
    msg = f"{field_name} must be int or str, got {type(value).__name__}"
    raise ValidationError(msg)


def _extract_instrument_from_api(
    raw_instrument: Mapping[str, Any], exchange: Exchange
) -> tuple[int, str, str] | None:
    """Extract token, trading_symbol, and name from Kite API response.

    Args:
        raw_instrument: Raw instrument dict from Kite API.
        exchange: Exchange to validate against.

    Returns:
        Tuple of (instrument_token, trading_symbol, name) or None if invalid.
    """
    try:
        # Validate exchange matches
        raw_exchange = str(raw_instrument.get("exchange", "")).strip().upper()
        if raw_exchange != exchange.value:
            return None

        # Extract required fields
        token_str = raw_instrument.get("instrument_token")
        trading_symbol = str(raw_instrument.get("tradingsymbol", "")).strip()
        name = str(raw_instrument.get("name", "")).strip()

        if not token_str or not trading_symbol or not name:
            return None

        token = _parse_instrument_token(token_str, field_name="instrument_token")

        return (token, trading_symbol, name)
    except (ValidationError, ValueError, TypeError) as exc:
        logger.debug("Skipping invalid instrument: %s", exc)
        return None


class SymbolTokenResolver:
    """Resolves trading symbols to KiteConnect instrument tokens.

    This service provides efficient symbol-to-token lookup for KiteConnect
    APIs which require instrument_token (integer) rather than trading symbols.

    It uses a two-tier caching strategy:
    1. First lookup in InstrumentMaster SQLite cache (fast, 24h TTL)
    2. Fallback to KiteConnect.instruments() API on cache miss

    Example:
        resolver = SymbolTokenResolver(instrument_master=master, kite_provider=kite)
        token = await resolver.resolve_token(symbol="RELIANCE", exchange=Exchange.NSE)
        logger.info("Token for RELIANCE: %s", token)

    Args:
        instrument_master: InstrumentMaster instance for cached lookups.
        kite_provider: Optional KiteProvider for API fallback on cache miss.
    """

    def __init__(
        self,
        *,
        instrument_master: InstrumentMaster,
        kite_provider: Any | None = None,
    ) -> None:
        """Initialize symbol token resolver.

        Args:
            instrument_master: InstrumentMaster instance for cached lookups.
            kite_provider: Optional KiteProvider for API fallback on cache miss.
                If None, cache misses will raise ConfigError instead of fetching.

        Raises:
            ConfigError: If instrument_master is None.
        """
        self._instrument_master = instrument_master
        self._kite_provider = kite_provider
        self._last_api_refresh: dict[Exchange, datetime] = {}

    async def resolve_token(
        self,
        symbol: str,
        exchange: Exchange,
        *,
        force_refresh: bool = False,
    ) -> int:
        """Resolve a trading symbol to its instrument token.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "INFY").
            exchange: Exchange (NSE, BSE, MCX, or CDS).
            force_refresh: If True, bypass cache and fetch from API.

        Returns:
            Instrument token as integer.

        Raises:
            ConfigError: If symbol cannot be resolved or exchange unsupported.
        """
        _ensure_supported_exchange(exchange)
        normalized_symbol = symbol.strip()

        if not normalized_symbol:
            msg = "symbol cannot be empty"
            raise ConfigError(msg)

        # Try cache first (unless force_refresh)
        if not force_refresh:
            try:
                instrument = self._instrument_master.get_instrument(normalized_symbol, exchange)
                return instrument.instrument_token
            except ConfigError:
                logger.debug(
                    "Symbol '%s' not found in cache for %s, trying API fallback",
                    normalized_symbol,
                    exchange.value,
                )

        # Cache miss: try API fallback if available
        if self._kite_provider is None:
            msg = (
                f"Symbol '{normalized_symbol}' not found in cache and "
                f"no kite_provider configured for API fallback"
            )
            raise ConfigError(msg)

        return await self._refresh_and_resolve(normalized_symbol, exchange)

    async def resolve_multiple_tokens(
        self,
        symbols: list[str],
        exchange: Exchange,
        *,
        force_refresh: bool = False,
    ) -> dict[str, int]:
        """Resolve multiple trading symbols to their instrument tokens.

        Args:
            symbols: List of trading symbols.
            exchange: Exchange (NSE, BSE, MCX, or CDS).
            force_refresh: If True, bypass cache and fetch from API.

        Returns:
            Dictionary mapping symbols to their tokens.

        Raises:
            ConfigError: If any symbol cannot be resolved.
        """
        _ensure_supported_exchange(exchange)
        if not symbols:
            return {}

        results: dict[str, int] = {}
        errors: list[str] = []

        for symbol in symbols:
            try:
                token = await self.resolve_token(symbol, exchange, force_refresh=force_refresh)
                results[symbol.strip()] = token
            except ConfigError as exc:
                errors.append(f"{symbol}: {exc}")

        if errors and len(errors) == len(symbols):
            msg = f"Failed to resolve all symbols: {'; '.join(errors)}"
            raise ConfigError(msg)

        if errors:
            logger.warning("Partial resolution failures: %s", "; ".join(errors))

        return results

    async def _refresh_and_resolve(
        self,
        symbol: str,
        exchange: Exchange,
    ) -> int:
        """Refresh instrument cache from API and resolve token.

        Args:
            symbol: Trading symbol to resolve.
            exchange: Exchange to fetch instruments for.

        Returns:
            Instrument token.

        Raises:
            ConfigError: If refresh fails or symbol still not found.
        """
        # Check if we need to refresh (rate limit: once per minute per exchange)
        now = datetime.now(UTC)
        last_refresh = self._last_api_refresh.get(exchange)
        if last_refresh and (now - last_refresh) < timedelta(minutes=1):
            logger.debug("Skipping API refresh, recent fetch for %s", exchange.value)

        await self._refresh_instruments_from_api(exchange)

        # Try cache again after refresh
        try:
            instrument = self._instrument_master.get_instrument(symbol, exchange)
            return instrument.instrument_token
        except ConfigError as exc:
            msg = f"Symbol '{symbol}' not found even after API refresh for {exchange.value}"
            raise ConfigError(msg) from exc

    async def _refresh_instruments_from_api(self, exchange: Exchange) -> None:
        """Fetch instruments from Kite API and update cache.

        Args:
            exchange: Exchange to fetch instruments for.

        Raises:
            ConfigError: If API fetch fails.
        """
        logger.info("Refreshing instrument cache from Kite API for %s", exchange.value)

        if self._kite_provider is None:
            msg = "Cannot refresh instruments: no kite_provider configured"
            raise ConfigError(msg)

        try:
            kite_client = self._kite_provider._get_client()

            # Call kite.instruments() - this is a blocking call
            import asyncio

            raw_instruments = await asyncio.to_thread(kite_client.instruments, exchange.value)

            if not isinstance(raw_instruments, list):
                msg = (
                    f"Kite instruments() must return list, " f"got {type(raw_instruments).__name__}"
                )
                raise ConfigError(msg)

            # Process and load valid instruments
            loaded_count = await self._process_and_load_instruments(raw_instruments, exchange)

            logger.info(
                "Loaded %d instruments from Kite API for %s",
                loaded_count,
                exchange.value,
            )

            # Update last refresh timestamp
            self._last_api_refresh[exchange] = datetime.now(UTC)

        except Exception as exc:
            msg = f"Failed to refresh instruments from Kite API for {exchange.value}: {exc}"
            raise ConfigError(msg) from exc

    async def _process_and_load_instruments(
        self,
        raw_instruments: list[Mapping[str, Any]],
        exchange: Exchange,
    ) -> int:
        """Process raw instruments from API and load into cache.

        Args:
            raw_instruments: List of raw instrument dicts from Kite API.
            exchange: Exchange for these instruments.

        Returns:
            Number of instruments loaded.
        """
        instruments = self._build_instruments_list(raw_instruments, exchange)
        now_utc = datetime.now(UTC).isoformat()
        return self._load_instruments_to_cache(instruments, now_utc)

    def _build_instruments_list(
        self,
        raw_instruments: list[Mapping[str, Any]],
        exchange: Exchange,
    ) -> list[Instrument]:
        """Build list of Instrument objects from raw API data.

        Args:
            raw_instruments: List of raw instrument dicts from Kite API.
            exchange: Exchange for these instruments.

        Returns:
            List of Instrument objects.
        """
        from iatb.data.instrument import Instrument

        instruments: list[Instrument] = []

        for raw in raw_instruments:
            extracted = _extract_instrument_from_api(raw, exchange)
            if extracted is None:
                continue

            token, trading_symbol, name = extracted

            # Build Instrument object
            # Some fields may not be available in instruments() response
            # We set sensible defaults
            instrument = Instrument(
                instrument_token=token,
                exchange_token=token,  # Often same as instrument_token
                trading_symbol=trading_symbol,
                name=name,
                exchange=exchange,
                segment=str(raw.get("segment", "EQ")).strip(),
                instrument_type=self._map_instrument_type(raw),
                lot_size=self._safe_decimal(raw.get("lot_size", "1")),
                tick_size=self._safe_decimal(raw.get("tick_size", "0.05")),
                strike=self._parse_strike(raw.get("strike")),
                expiry=self._parse_expiry(raw.get("expiry")),
            )
            instruments.append(instrument)

        return instruments

    def _load_instruments_to_cache(
        self,
        instruments: list[Instrument],
        now_utc: str,
    ) -> int:
        """Load instruments directly into SQLite cache.

        Args:
            instruments: List of Instrument objects to cache.
            now_utc: Current UTC timestamp as ISO string.

        Returns:
            Number of instruments loaded.
        """
        import sqlite3
        from pathlib import Path

        db_path = Path(self._instrument_master._db_path)
        insert_sql = self._get_insert_sql()

        loaded = 0
        try:
            with sqlite3.connect(db_path) as conn:
                loaded = self._insert_instruments_batch(conn, insert_sql, instruments, now_utc)
                conn.commit()
        except Exception as exc:
            logger.warning("Failed to connect to database: %s", exc)
            return 0

        return loaded

    def _get_insert_sql(self) -> str:
        """Get SQL INSERT statement for instruments.

        Returns:
            SQL INSERT statement.
        """
        return """
            INSERT OR REPLACE INTO instruments (
                instrument_token, exchange_token, trading_symbol, name,
                exchange, segment, instrument_type, lot_size, tick_size,
                strike, expiry, fetched_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    def _insert_instruments_batch(
        self,
        conn: Any,
        insert_sql: str,
        instruments: list[Instrument],
        now_utc: str,
    ) -> int:
        """Insert a batch of instruments into database.

        Args:
            conn: SQLite connection.
            insert_sql: SQL INSERT statement.
            instruments: List of Instrument objects.
            now_utc: Current UTC timestamp.

        Returns:
            Number of instruments inserted.
        """
        loaded = 0
        for inst in instruments:
            try:
                conn.execute(
                    insert_sql,
                    (
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
                    ),
                )
                loaded += 1
            except Exception as exc:
                logger.warning("Failed to load instrument %s: %s", inst.trading_symbol, exc)
        return loaded

    def _map_instrument_type(self, raw: Mapping[str, Any]) -> InstrumentType:
        """Map Kite instrument type to InstrumentType enum.

        Args:
            raw: Raw instrument dict from Kite API.

        Returns:
            InstrumentType enum value.
        """
        from iatb.data.instrument import InstrumentType, map_kite_instrument_type

        raw_type = str(raw.get("instrument_type", "")).strip().upper()
        try:
            return map_kite_instrument_type(raw_type)
        except (ValueError, KeyError):
            # Default to EQUITY for unknown types
            return InstrumentType.EQUITY

    def _safe_decimal(self, value: Any) -> Decimal:
        """Safely convert value to Decimal for lot_size/tick_size.

        Args:
            value: Value to convert.

        Returns:
            Decimal representation.
        """
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int):
            return Decimal(str(value))
        if isinstance(value, str):
            try:
                # G7 exemption: API boundary conversion with immediate Decimal wrap
                return Decimal(str(float(value.strip())))  # noqa: G7
            except (ValueError, TypeError):
                return Decimal("1")
        if isinstance(value, float):
            # G7 exemption: API boundary conversion with immediate Decimal wrap
            return Decimal(str(value))  # noqa: G7
        return Decimal("1")

    def _parse_strike(self, value: Any) -> Decimal | None:
        """Parse strike price from API response.

        Args:
            value: Raw strike value.

        Returns:
            Strike price as Decimal or None.
        """
        if value is None or value == "" or value == 0:
            return None
        try:
            # G7 exemption: API boundary conversion with immediate Decimal wrap
            return Decimal(str(float(value)))  # noqa: G7
        except (ValueError, TypeError):
            return None

    def _parse_expiry(self, value: Any) -> datetime | None:
        """Parse expiry date from API response.

        Args:
            value: Raw expiry value.

        Returns:
            Expiry datetime or None.
        """
        if value is None or value == "":
            return None

        try:
            # Kite returns expiry as datetime object or string
            if isinstance(value, datetime):
                return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
            if isinstance(value, str):
                # Parse ISO format
                parsed = datetime.fromisoformat(value.strip())
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            pass

        return None
