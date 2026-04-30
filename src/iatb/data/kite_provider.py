"""
Kite Connect REST API provider for historical market data.

This provider wraps the Kite Connect REST API endpoints for fetching
OHLCV historical data and ticker snapshots. It implements rate limiting
and exponential backoff for resilience.

Key endpoints wrapped:
- kite.historical_data() → OHLCV bars
- kite.quote() → Ticker snapshot with bid/ask/last/volume
- kite.ltp() → Last traded price
- kite.instruments() → Instrument master dump (not in DataProvider protocol)
"""

import asyncio
import importlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    Timestamp,
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.rate_limiter import (
    CircuitBreaker,
    RateLimiter,
    RetryConfig,
    retry_with_backoff,
)
from iatb.data.validator import validate_ticker_snapshot

# Kite API rate limit: 3 requests per second
_RATE_LIMIT_REQUESTS = 3
_RATE_LIMIT_WINDOW = 1.0  # seconds

# Retry configuration
_MAX_RETRIES = 3
_INITIAL_RETRY_DELAY = 1.0  # seconds
_RETRY_BACKOFF_MULTIPLIER = 2.0

# Supported exchanges
_SUPPORTED_EXCHANGES = frozenset({Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS})

# Interval mapping from IATB timeframe to Kite Connect interval
_INTERVAL_MAP = {
    "1m": "minute",
    "5m": "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h": "hour",
    "1d": "day",
}

# Exchange prefix for Kite trading symbols
_EXCHANGE_PREFIX_MAP = {
    Exchange.NSE: "NSE",
    Exchange.BSE: "BSE",
    Exchange.MCX: "MCX",
    Exchange.CDS: "CDS",
}


def _ensure_supported_exchange(exchange: Exchange) -> None:
    """Validate that the exchange is supported by Kite Connect."""
    if exchange in _SUPPORTED_EXCHANGES:
        return
    msg = f"Unsupported exchange for Kite provider: {exchange.value}"
    raise ConfigError(msg)


def _map_timeframe(timeframe: str) -> str:
    """Map IATB timeframe to Kite Connect interval format."""
    interval = _INTERVAL_MAP.get(timeframe)
    if interval is None:
        msg = f"Unsupported Kite timeframe: {timeframe}"
        raise ConfigError(msg)
    return interval


def _format_trading_symbol(symbol: str, exchange: Exchange) -> str:
    """Format symbol as Kite trading symbol with exchange prefix."""
    prefix = _EXCHANGE_PREFIX_MAP.get(exchange)
    if prefix is None:
        msg = f"Cannot format trading symbol for exchange: {exchange.value}"
        raise ConfigError(msg)
    return f"{prefix}:{symbol}"


def _extract_numeric(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
    default: object = 0,
) -> object:
    """Extract numeric value from payload with fallback keys."""
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _coerce_numeric_input(value: object, *, field_name: str) -> str | int | Decimal:
    """Coerce value to numeric type without using float."""
    if isinstance(value, bool):
        msg = f"{field_name} must not be boolean"
        raise ConfigError(msg)
    if isinstance(value, Decimal | int | str):
        return value if isinstance(value, Decimal | int) else str(value)
    if isinstance(value, float):
        # API boundary conversion: explicitly convert float to str
        # This is the only place where float is accepted from external API
        return str(value)
    msg = f"{field_name} must be numeric-compatible, got {type(value).__name__}"
    raise ConfigError(msg)


def _parse_kite_timestamp(value: object) -> datetime:
    """Parse Kite timestamp to UTC datetime."""
    if isinstance(value, datetime):
        # Ensure timezone awareness
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        # Kite returns ISO format strings
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            msg = f"Kite timestamp string must include timezone: {value!r}"
            raise ConfigError(msg)
        return parsed.astimezone(UTC)
    msg = f"Unsupported timestamp from Kite: {type(value).__name__}"
    raise ConfigError(msg)


class KiteProvider(DataProvider):
    """Kite Connect REST API provider for historical market data.

    This provider implements the DataProvider protocol using Kite Connect's
    REST API endpoints. It includes built-in rate limiting (3 req/sec) and
    exponential backoff retry logic for 429/5xx errors.

    Example:
        provider = KiteProvider(api_key="xxx", access_token="yyy")
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=100
        )
    """

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        kite_connect_factory: Callable[[str, str], Any] | None = None,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize Kite Connect provider.

        Args:
            api_key: Kite Connect API key.
            access_token: Kite Connect access token.
            kite_connect_factory: Optional factory for creating KiteConnect instance.
                Useful for testing/mocking.
            rate_limiter: Optional rate limiter instance. If not provided,
                creates default RateLimiter(3, burst_capacity=10).
            circuit_breaker: Optional circuit breaker instance. If not provided,
                creates default CircuitBreaker(5, 60.0).
            retry_config: Optional retry configuration. If not provided,
                creates default RetryConfig().

        Raises:
            ConfigError: If api_key or access_token is empty, or if parameters invalid.
        """
        self._validate_init_params(api_key, access_token)
        self._api_key = api_key
        self._access_token = access_token
        self._kite_connect_factory = kite_connect_factory or self._default_kite_factory

        self._rate_limiter = rate_limiter or RateLimiter(
            requests_per_second=3.0,
            burst_capacity=10,
        )
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=5,
            reset_timeout=60.0,
        )
        self._retry_config = retry_config or RetryConfig()

        self._kite_client: Any = None

    @staticmethod
    def _validate_init_params(api_key: str, access_token: str) -> None:
        """Validate initialization parameters."""
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not access_token.strip():
            msg = "access_token cannot be empty"
            raise ConfigError(msg)

    @staticmethod
    def _default_kite_factory(api_key: str, access_token: str) -> Any:
        """Default factory to create KiteConnect instance."""
        try:
            module = importlib.import_module("kiteconnect")
        except ModuleNotFoundError as exc:
            msg = "kiteconnect dependency is required for KiteProvider"
            raise ConfigError(msg) from exc
        if not hasattr(module, "KiteConnect"):
            msg = "kiteconnect.KiteConnect is not available"
            raise ConfigError(msg)
        return module.KiteConnect(api_key=api_key, access_token=access_token)

    def _get_client(self) -> Any:
        """Get or create KiteConnect client instance."""
        if self._kite_client is None:
            self._kite_client = self._kite_connect_factory(self._api_key, self._access_token)
        return self._kite_client

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV bars from Kite Connect historical data endpoint.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, MCX, or CDS).
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 1d).
            since: Optional timestamp to filter from.
            limit: Maximum number of bars to return.

        Returns:
            List of normalized OHLCVBar objects.

        Raises:
            ConfigError: If exchange/timeframe unsupported or API errors occur.
        """
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)

        _ensure_supported_exchange(exchange)
        kite_interval = _map_timeframe(timeframe)
        trading_symbol = _format_trading_symbol(symbol, exchange)

        start_date, end_date = self._calculate_date_range(since, limit)
        client = self._get_client()

        data = await self._retry_with_backoff(
            self._fetch_historical_data,
            client,
            trading_symbol,
            kite_interval,
            start_date,
            end_date,
        )

        return self._process_ohlcv_data(data, symbol, exchange, timeframe, since, limit)

    def _calculate_date_range(
        self, since: Timestamp | None, limit: int
    ) -> tuple[datetime, datetime]:
        """Calculate start and end dates for historical data fetch."""
        end_date = datetime.now(UTC)
        if since is not None:
            start_date = datetime(since.year, since.month, since.day, tzinfo=UTC)
        else:
            start_date = end_date - timedelta(days=limit)
        return start_date, end_date

    def _process_ohlcv_data(
        self,
        data: list[dict[str, object]],
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None,
        limit: int,
    ) -> list[OHLCVBar]:
        """Process and normalize OHLCV data from Kite API."""
        records = self._build_ohlcv_records(data, since=since)
        clipped = records[-limit:] if len(records) > limit else records
        return normalize_ohlcv_batch(
            clipped,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            source="kiteconnect",
        )

    async def get_ticker(
        self,
        *,
        symbol: str,
        exchange: Exchange,
    ) -> TickerSnapshot:
        """Fetch ticker snapshot from Kite Connect quote endpoint.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, MCX, or CDS).

        Returns:
            Normalized TickerSnapshot with bid/ask/last/volume.

        Raises:
            ConfigError: If exchange unsupported or API errors occur.
        """
        _ensure_supported_exchange(exchange)
        trading_symbol = _format_trading_symbol(symbol, exchange)

        client = self._get_client()
        quote_data = await self._retry_with_backoff(
            self._fetch_quote,
            client,
            trading_symbol,
        )

        return self._build_ticker_snapshot(symbol, exchange, quote_data, trading_symbol)

    def _build_ticker_snapshot(
        self,
        symbol: str,
        exchange: Exchange,
        quote_data: dict[str, Any],
        trading_symbol: str,
    ) -> TickerSnapshot:
        """Build ticker snapshot from quote data."""
        quote = quote_data.get(trading_symbol, {})

        bid = _coerce_numeric_input(
            _extract_numeric(quote, ("bid", "buy", "best_bid")),
            field_name="bid",
        )
        ask = _coerce_numeric_input(
            _extract_numeric(quote, ("ask", "sell", "best_offer")),
            field_name="ask",
        )
        last = _coerce_numeric_input(
            _extract_numeric(quote, ("last_price", "last")),
            field_name="last_price",
        )
        volume = _coerce_numeric_input(
            _extract_numeric(quote, ("volume", "total_buy_qty")),
            field_name="volume",
        )

        snapshot = TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price(bid),
            ask=create_price(ask),
            last=create_price(last),
            volume_24h=create_quantity(volume),
            source="kiteconnect",
        )

        validate_ticker_snapshot(snapshot)
        return snapshot

    async def _retry_with_backoff(
        self,
        func: Callable[..., Any],
        *args: object,
    ) -> Any:
        """Execute func with exponential backoff retry and circuit breaker.

        Delegates to rate_limiter.retry_with_backoff() with rate limiting.
        """

        # Wrap the function to include rate limiting
        async def rate_limited_func(**kwargs: Any) -> Any:
            await self._rate_limiter.acquire()
            try:
                return await func(*args)
            finally:
                self._rate_limiter.release()

        return await retry_with_backoff(
            rate_limited_func,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def _fetch_historical_data(
        self,
        client: Any,
        trading_symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, object]]:
        """Fetch historical data from Kite Connect API.

        Args:
            client: KiteConnect instance.
            trading_symbol: Kite trading symbol (e.g., "NSE:RELIANCE").
            interval: Kite interval (minute, 5minute, day, etc.).
            start_date: Start datetime.
            end_date: End datetime.

        Returns:
            List of OHLCV dictionaries from Kite API.

        Raises:
            ConfigError: If API call fails or returns invalid data.
        """
        if not hasattr(client, "historical_data"):
            msg = "KiteConnect client must have historical_data() method"
            raise ConfigError(msg)

        # Convert to date objects for Kite API
        start = start_date.date()
        end = end_date.date()

        # Run blocking API call in thread pool
        data = await asyncio.to_thread(
            client.historical_data,
            trading_symbol,
            start,
            end,
            interval,
        )

        if not isinstance(data, list):
            msg = f"Kite historical_data must return list, got {type(data).__name__}"
            raise ConfigError(msg)

        return data

    async def _fetch_quote(
        self,
        client: Any,
        trading_symbol: str,
    ) -> dict[str, Any]:
        """Fetch quote data from Kite Connect API.

        Args:
            client: KiteConnect instance.
            trading_symbol: Kite trading symbol (e.g., "NSE:RELIANCE").

        Returns:
            Dictionary mapping symbols to quote data.

        Raises:
            ConfigError: If API call fails or returns invalid data.
        """
        if not hasattr(client, "quote"):
            msg = "KiteConnect client must have quote() method"
            raise ConfigError(msg)

        # Run blocking API call in thread pool
        data = await asyncio.to_thread(client.quote, [trading_symbol])

        if not isinstance(data, dict):
            msg = f"Kite quote must return dict, got {type(data).__name__}"
            raise ConfigError(msg)

        return data

    def _build_ohlcv_records(
        self,
        data: list[dict[str, object]],
        since: Timestamp | None = None,
    ) -> list[dict[str, object]]:
        """Build OHLCV records from Kite historical data response.

        Args:
            data: Raw list from Kite historical_data endpoint.
            since: Optional timestamp to filter from.

        Returns:
            List of normalized OHLCV dictionaries.
        """
        records: list[dict[str, object]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            # Parse timestamp
            raw_timestamp = item.get("date")
            if raw_timestamp is None:
                continue

            try:
                timestamp = _parse_kite_timestamp(raw_timestamp).astimezone(UTC)
            except (ConfigError, ValueError):
                continue

            # Filter by since timestamp if provided
            if since is not None and timestamp < since:
                continue

            # Extract OHLCV values
            records.append(
                {
                    "timestamp": create_timestamp(timestamp),
                    "open": _extract_numeric(item, ("open", "Open")),
                    "high": _extract_numeric(item, ("high", "High")),
                    "low": _extract_numeric(item, ("low", "Low")),
                    "close": _extract_numeric(item, ("close", "Close")),
                    "volume": _extract_numeric(item, ("volume", "Volume")),
                }
            )

        return records

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env_var: str = "ZERODHA_API_KEY",
        access_token_env_var: str = "ZERODHA_ACCESS_TOKEN",  # noqa: S107
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        retry_config: RetryConfig | None = None,
    ) -> "KiteProvider":
        """Create provider from environment variables.

        Args:
            api_key_env_var: Environment variable name for API key.
            access_token_env_var: Environment variable name for access token.
            rate_limiter: Optional rate limiter instance.
            circuit_breaker: Optional circuit breaker instance.
            retry_config: Optional retry configuration.

        Returns:
            Configured KiteProvider instance.

        Raises:
            ConfigError: If required environment variables not set.
        """
        import os

        api_key = os.getenv(api_key_env_var, "").strip()
        access_token = os.getenv(access_token_env_var, "").strip()

        if not api_key:
            msg = f"{api_key_env_var} environment variable is required"
            raise ConfigError(msg)
        if not access_token:
            msg = f"{access_token_env_var} environment variable is required"
            raise ConfigError(msg)

        return cls(
            api_key=api_key,
            access_token=access_token,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
            retry_config=retry_config,
        )
