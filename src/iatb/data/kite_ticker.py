"""
KiteTicker WebSocket feed for real-time market data with advanced features.

This module provides a specialized WebSocket feed using KiteTicker with:
- Auto-reconnect with exponential backoff
- Heartbeat monitoring for connection health
- Thread-safe tick buffer for scanner consumption
- QUOTE (full) and LTP (lightweight) modes
- Callback and async queue emission patterns
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity
from iatb.data.base import TickerSnapshot

_LOGGER = logging.getLogger(__name__)

# Configuration constants
_MAX_RECONNECT_ATTEMPTS = 10
_INITIAL_RECONNECT_DELAY = 1.0  # seconds
_MAX_RECONNECT_DELAY = 60.0  # seconds
_RECONNECT_BACKOFF_MULTIPLIER = 2.0
_HEARTBEAT_INTERVAL = 30.0  # seconds
_TICK_BUFFER_SIZE = 1000
_MODE_QUOTE = "quote"
_MODE_LTP = "ltp"


_TICK_QUEUE_MAXSIZE = 10000


@dataclass
class ConnectionStats:
    """Statistics about the WebSocket connection."""

    connected_at: datetime | None = None
    last_tick_at: datetime | None = None
    ticks_received: int = 0
    reconnect_attempts: int = 0
    last_reconnect_at: datetime | None = None


class TickBuffer:
    """Thread-safe buffer for storing recent ticks."""

    def __init__(self, max_size: int = _TICK_BUFFER_SIZE) -> None:
        self._buffer: dict[str, TickerSnapshot] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._insertion_order: list[str] = []

    def put(self, snapshot: TickerSnapshot) -> None:
        """Add a ticker snapshot to the buffer."""
        symbol_key = f"{snapshot.exchange.value}:{snapshot.symbol}"
        with self._lock:
            # Update or add snapshot
            self._buffer[symbol_key] = snapshot
            # Track insertion order for LRU eviction
            if symbol_key in self._insertion_order:
                self._insertion_order.remove(symbol_key)
            self._insertion_order.append(symbol_key)
            # Evict oldest if buffer is full
            while len(self._insertion_order) > self._max_size:
                oldest = self._insertion_order.pop(0)
                del self._buffer[oldest]

    def get(self, symbol: str, exchange: Exchange) -> TickerSnapshot | None:
        """Get the latest snapshot for a symbol."""
        symbol_key = f"{exchange.value}:{symbol}"
        with self._lock:
            return self._buffer.get(symbol_key)

    def get_all(self) -> list[TickerSnapshot]:
        """Get all snapshots in the buffer."""
        with self._lock:
            return list(self._buffer.values())

    def clear(self) -> None:
        """Clear all snapshots from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._insertion_order.clear()

    def size(self) -> int:
        """Get the current buffer size."""
        with self._lock:
            return len(self._buffer)


class KiteTickerFeed:
    """Real-time WebSocket feed using KiteTicker with advanced features.

    This class provides a robust WebSocket connection for receiving real-time
    market data from Kite Connect. It includes automatic reconnection with
    exponential backoff, heartbeat monitoring, and thread-safe tick buffering.

    Example:
        .. code-block:: python

            async def on_tick(snapshot: TickerSnapshot) -> None:
                # Handle tick data
                pass

            feed = KiteTickerFeed(api_key="xxx", access_token="yyy")
            await feed.connect()
            await feed.subscribe("RELIANCE", Exchange.NSE, mode="quote")
            feed.set_callback(on_tick)
            await feed.start()
    """

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        kite_ticker_factory: Callable[[str, str], Any] | None = None,
        max_reconnect_attempts: int = _MAX_RECONNECT_ATTEMPTS,
        initial_reconnect_delay: float = _INITIAL_RECONNECT_DELAY,
        max_reconnect_delay: float = _MAX_RECONNECT_DELAY,
        reconnect_backoff_multiplier: float = _RECONNECT_BACKOFF_MULTIPLIER,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
        tick_buffer_size: int = _TICK_BUFFER_SIZE,
    ) -> None:
        """Initialize the KiteTicker feed.

        Args:
            api_key: Kite Connect API key.
            access_token: Kite Connect access token.
            kite_ticker_factory: Optional factory for creating KiteTicker instance.
            max_reconnect_attempts: Maximum number of reconnection attempts.
            initial_reconnect_delay: Initial delay in seconds before first reconnect.
            max_reconnect_delay: Maximum delay in seconds between reconnects.
            reconnect_backoff_multiplier: Multiplier for exponential backoff.
            heartbeat_interval: Interval in seconds for heartbeat checks.
            tick_buffer_size: Maximum number of ticks to buffer per symbol.

        Raises:
            ConfigError: If parameters are invalid.
        """
        self._validate_and_initialize(
            api_key,
            access_token,
            kite_ticker_factory,
            max_reconnect_attempts,
            initial_reconnect_delay,
            max_reconnect_delay,
            reconnect_backoff_multiplier,
            heartbeat_interval,
            tick_buffer_size,
        )

    def _validate_and_initialize(
        self,
        api_key: str,
        access_token: str,
        kite_ticker_factory: Callable[[str, str], Any] | None,
        max_reconnect_attempts: int,
        initial_reconnect_delay: float,
        max_reconnect_delay: float,
        reconnect_backoff_multiplier: float,
        heartbeat_interval: float,
        tick_buffer_size: int,
    ) -> None:
        """Validate parameters and initialize state."""
        self._validate_init_params(
            api_key,
            access_token,
            max_reconnect_attempts,
            initial_reconnect_delay,
            max_reconnect_delay,
            reconnect_backoff_multiplier,
            heartbeat_interval,
            tick_buffer_size,
        )
        self._initialize_state(
            api_key,
            access_token,
            kite_ticker_factory,
            max_reconnect_attempts,
            initial_reconnect_delay,
            max_reconnect_delay,
            reconnect_backoff_multiplier,
            heartbeat_interval,
            tick_buffer_size,
        )

    @staticmethod
    def _validate_init_params(
        api_key: str,
        access_token: str,
        max_reconnect_attempts: int,
        initial_reconnect_delay: float,
        max_reconnect_delay: float,
        reconnect_backoff_multiplier: float,
        heartbeat_interval: float,
        tick_buffer_size: int,
    ) -> None:
        """Validate initialization parameters.

        Raises:
            ConfigError: If parameters are invalid.
        """
        KiteTickerFeed._validate_credentials(api_key, access_token)
        KiteTickerFeed._validate_reconnect_params(
            max_reconnect_attempts,
            initial_reconnect_delay,
            max_reconnect_delay,
            reconnect_backoff_multiplier,
        )
        KiteTickerFeed._validate_runtime_params(heartbeat_interval, tick_buffer_size)

    @staticmethod
    def _validate_credentials(api_key: str, access_token: str) -> None:
        """Validate API credentials.

        Raises:
            ConfigError: If credentials are invalid.
        """
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not access_token.strip():
            msg = "access_token cannot be empty"
            raise ConfigError(msg)

    @staticmethod
    def _validate_reconnect_params(
        max_reconnect_attempts: int,
        initial_reconnect_delay: float,
        max_reconnect_delay: float,
        reconnect_backoff_multiplier: float,
    ) -> None:
        """Validate reconnection parameters.

        Raises:
            ConfigError: If parameters are invalid.
        """
        if max_reconnect_attempts <= 0:
            msg = "max_reconnect_attempts must be positive"
            raise ConfigError(msg)
        if initial_reconnect_delay < 0:
            msg = "initial_reconnect_delay must be non-negative"
            raise ConfigError(msg)
        if max_reconnect_delay <= 0:
            msg = "max_reconnect_delay must be positive"
            raise ConfigError(msg)
        if reconnect_backoff_multiplier <= 1.0:
            msg = "reconnect_backoff_multiplier must be greater than 1.0"
            raise ConfigError(msg)

    @staticmethod
    def _validate_runtime_params(heartbeat_interval: float, tick_buffer_size: int) -> None:
        """Validate runtime parameters.

        Raises:
            ConfigError: If parameters are invalid.
        """
        if heartbeat_interval <= 0:
            msg = "heartbeat_interval must be positive"
            raise ConfigError(msg)
        if tick_buffer_size <= 0:
            msg = "tick_buffer_size must be positive"
            raise ConfigError(msg)

    def _initialize_state(
        self,
        api_key: str,
        access_token: str,
        kite_ticker_factory: Callable[[str, str], Any] | None,
        max_reconnect_attempts: int,
        initial_reconnect_delay: float,
        max_reconnect_delay: float,
        reconnect_backoff_multiplier: float,
        heartbeat_interval: float,
        tick_buffer_size: int,
    ) -> None:
        """Initialize instance state."""
        self._init_config(
            api_key,
            access_token,
            kite_ticker_factory,
            max_reconnect_attempts,
            initial_reconnect_delay,
            max_reconnect_delay,
            reconnect_backoff_multiplier,
            heartbeat_interval,
        )
        self._init_buffers(tick_buffer_size)
        self._init_connection_state()

    def _init_config(
        self,
        api_key: str,
        access_token: str,
        kite_ticker_factory: Callable[[str, str], Any] | None,
        max_reconnect_attempts: int,
        initial_reconnect_delay: float,
        max_reconnect_delay: float,
        reconnect_backoff_multiplier: float,
        heartbeat_interval: float,
    ) -> None:
        """Initialize configuration parameters."""
        self._api_key = api_key
        self._access_token = access_token
        self._max_reconnect_attempts = max_reconnect_attempts
        self._initial_reconnect_delay = initial_reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay
        self._reconnect_backoff_multiplier = reconnect_backoff_multiplier
        self._heartbeat_interval = heartbeat_interval
        self._kite_ticker_factory = kite_ticker_factory or self._default_ticker_factory

    def _init_buffers(self, tick_buffer_size: int) -> None:
        """Initialize buffers and queues."""
        self._subscriptions: set[tuple[str, Exchange]] = set()
        self._tick_buffer = TickBuffer(max_size=tick_buffer_size)
        self._tick_queue: asyncio.Queue[TickerSnapshot] = asyncio.Queue(maxsize=_TICK_QUEUE_MAXSIZE)

    def _init_connection_state(self) -> None:
        """Initialize connection state variables."""
        self._ticker_instance: Any = None
        self._is_connected = False
        self._is_running = False
        self._callback: Callable[[TickerSnapshot], None] | None = None
        self._stats = ConnectionStats()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reconnect_delay = self._initial_reconnect_delay
        self._should_stop = asyncio.Event()

    @staticmethod
    def _default_ticker_factory(api_key: str, access_token: str) -> Any:
        """Default factory to create KiteTicker instance."""
        try:
            module = importlib.import_module("kiteconnect")
        except ModuleNotFoundError as exc:
            msg = "kiteconnect dependency is required for KiteTickerFeed"
            raise ConfigError(msg) from exc
        if not hasattr(module, "KiteTicker"):
            msg = "kiteconnect.KiteTicker is not available"
            raise ConfigError(msg)
        return module.KiteTicker(api_key=api_key, access_token=access_token)

    async def connect(self) -> None:
        """Establish WebSocket connection with reconnection logic."""
        if self._is_connected:
            return

        self._should_stop.clear()
        attempt = 0

        while attempt < self._max_reconnect_attempts:
            if self._should_stop.is_set():
                msg = "Connection stopped by user"
                raise ConfigError(msg)

            attempt += 1
            self._stats.reconnect_attempts = attempt

            try:
                self._ticker_instance = await asyncio.to_thread(
                    self._kite_ticker_factory,
                    self._api_key,
                    self._access_token,
                )

                self._setup_handlers()

                await asyncio.to_thread(self._ticker_instance.connect)

                self._is_connected = True
                self._stats.connected_at = datetime.now(UTC)
                self._stats.last_reconnect_at = datetime.now(UTC)
                self._reconnect_delay = self._initial_reconnect_delay

                return

            except Exception as exc:
                if attempt >= self._max_reconnect_attempts:
                    msg = f"Failed to connect after {self._max_reconnect_attempts} attempts: {exc}"
                    raise ConfigError(msg) from exc

                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * self._reconnect_backoff_multiplier,
                    self._max_reconnect_delay,
                )

    async def disconnect(self) -> None:
        """Disconnect WebSocket and cleanup resources."""
        self._should_stop.set()
        self._is_running = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._ticker_instance:
            try:
                await asyncio.to_thread(self._ticker_instance.close)
            except RuntimeError:
                pass

        self._is_connected = False
        self._tick_buffer.clear()
        self._subscriptions.clear()

    async def subscribe(
        self,
        symbol: str,
        exchange: Exchange,
        mode: str = _MODE_QUOTE,
    ) -> None:
        """Subscribe to real-time updates for a symbol.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            exchange: Exchange (NSE, BSE, MCX, or CDS).
            mode: Subscription mode: "quote" (full) or "ltp" (lightweight).

        Raises:
            ConfigError: If not connected or parameters invalid.
        """
        if not self._is_connected:
            msg = "Not connected. Call connect() first."
            raise ConfigError(msg)

        if mode not in (_MODE_QUOTE, _MODE_LTP):
            msg = f"Invalid mode: {mode}. Must be 'quote' or 'ltp'"
            raise ConfigError(msg)

        self._subscriptions.add((symbol, exchange))

        if self._ticker_instance and hasattr(self._ticker_instance, "subscribe"):
            instrument_tokens = self._get_instrument_tokens({(symbol, exchange)})
            if instrument_tokens:
                await asyncio.to_thread(
                    self._ticker_instance.subscribe,
                    instrument_tokens,
                    mode if mode == _MODE_QUOTE else "ltp",
                )

    async def unsubscribe(
        self,
        symbol: str,
        exchange: Exchange,
    ) -> None:
        """Unsubscribe from updates for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange.
        """
        if (symbol, exchange) in self._subscriptions:
            self._subscriptions.remove((symbol, exchange))

        if self._ticker_instance and hasattr(self._ticker_instance, "unsubscribe"):
            instrument_tokens = self._get_instrument_tokens({(symbol, exchange)})
            if instrument_tokens:
                await asyncio.to_thread(
                    self._ticker_instance.unsubscribe,
                    instrument_tokens,
                )

    def set_callback(self, callback: Callable[[TickerSnapshot], None]) -> None:
        """Set callback function for incoming ticks.

        Args:
            callback: Function to call with each TickerSnapshot.
        """
        self._callback = callback

    async def start(self) -> None:
        """Start the feed processing (heartbeat and auto-reconnect)."""
        if self._is_running:
            return

        self._is_running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self._reconnect_task = asyncio.create_task(self._auto_reconnect())

    async def get_tick(
        self,
        symbol: str,
        exchange: Exchange,
        timeout: float = 5.0,
    ) -> TickerSnapshot:
        """Get the latest tick for a symbol from the queue.

        Args:
            symbol: Trading symbol.
            exchange: Exchange.
            timeout: Maximum time to wait for a tick.

        Returns:
            Latest TickerSnapshot for the symbol.

        Raises:
            asyncio.TimeoutError: If no tick received within timeout.
            ConfigError: If not connected.
        """
        if not self._is_connected:
            msg = "Not connected. Call connect() first."
            raise ConfigError(msg)

        # Try to get from buffer first
        snapshot = self._tick_buffer.get(symbol, exchange)
        if snapshot:
            return snapshot

        # Fall back to queue
        try:
            snapshot = await asyncio.wait_for(self._tick_queue.get(), timeout=timeout)
            if snapshot.symbol == symbol and snapshot.exchange == exchange:
                return snapshot
            # Put back if not our symbol
            self._tick_queue.put_nowait(snapshot)
        except asyncio.TimeoutError:
            msg = f"Timeout waiting for tick for {symbol}"
            raise asyncio.TimeoutError(msg) from None

        msg = f"No tick available for {symbol}"
        raise ConfigError(msg)

    def get_latest_tick(self, symbol: str, exchange: Exchange) -> TickerSnapshot | None:
        """Get the latest tick from the buffer (non-blocking).

        Args:
            symbol: Trading symbol.
            exchange: Exchange.

        Returns:
            Latest TickerSnapshot or None if not available.
        """
        return self._tick_buffer.get(symbol, exchange)

    def get_all_ticks(self) -> list[TickerSnapshot]:
        """Get all ticks from the buffer (non-blocking).

        Returns:
            List of all TickerSnapshot objects in the buffer.
        """
        return self._tick_buffer.get_all()

    def get_stats(self) -> ConnectionStats:
        """Get connection statistics.

        Returns:
            ConnectionStats object with current statistics.
        """
        return self._stats

    def is_connected(self) -> bool:
        """Check if the feed is connected."""
        return self._is_connected

    def is_running(self) -> bool:
        """Check if the feed is running."""
        return self._is_running

    def _setup_handlers(self) -> None:
        """Setup KiteTicker event handlers."""
        self._ticker_instance.on_ticks = self._on_ticks
        self._ticker_instance.on_connect = self._on_connect
        self._ticker_instance.on_close = self._on_close
        self._ticker_instance.on_error = self._on_error
        self._ticker_instance.on_reconnect = self._on_reconnect
        self._ticker_instance.on_noreconnect = self._on_noreconnect

    def _on_ticks(self, ws: Any, ticks: list[dict[str, object]]) -> None:
        """Handle incoming ticks from WebSocket."""
        for tick_data in ticks:
            try:
                snapshot = self._parse_tick(tick_data)
                if snapshot:
                    self._tick_buffer.put(snapshot)
                    asyncio.create_task(self._tick_queue.put(snapshot))

                    if self._callback:
                        try:
                            self._callback(snapshot)
                        except Exception:  # nosec  # Intentional: callback errors shouldn't crash ticker
                            _LOGGER.exception("Error in callback")

                    self._stats.ticks_received += 1
                    self._stats.last_tick_at = datetime.now(UTC)
            except (ValueError, TypeError, KeyError):
                continue

    def _on_connect(self, ws: Any, response: dict[str, object]) -> None:
        """Handle connection event."""
        self._is_connected = True
        self._stats.connected_at = datetime.now(UTC)

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection close event."""
        self._is_connected = False

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection error event."""
        self._is_connected = False

    def _on_reconnect(self, ws: Any, response: dict[str, object]) -> None:
        """Handle reconnection event."""
        self._is_connected = True
        self._stats.last_reconnect_at = datetime.now(UTC)
        self._reconnect_delay = self._initial_reconnect_delay

    def _on_noreconnect(self, ws: Any) -> None:
        """Handle no more reconnection attempts event."""
        self._is_connected = False

    async def _auto_reconnect(self) -> None:
        """Monitor connection and attempt reconnection if needed."""
        while not self._should_stop.is_set():
            if not self._is_connected and self._is_running:
                try:
                    await self.connect()
                    # Resubscribe to all symbols
                    for symbol, exchange in self._subscriptions:
                        await self.subscribe(symbol, exchange)
                except ConfigError:
                    pass

            await asyncio.sleep(5.0)

    async def _heartbeat_monitor(self) -> None:
        """Monitor heartbeat and log connection health."""
        while not self._should_stop.is_set():
            await asyncio.sleep(self._heartbeat_interval)

            if not self._is_connected:
                continue

            last_tick_age = None
            if self._stats.last_tick_at:
                last_tick_age = (datetime.now(UTC) - self._stats.last_tick_at).total_seconds()

            if last_tick_age and last_tick_age > self._heartbeat_interval * 2:
                self._is_connected = False

    def _parse_tick(self, tick_data: dict[str, object]) -> TickerSnapshot | None:
        """Parse raw Kite tick data into TickerSnapshot.

        Args:
            tick_data: Raw tick data from KiteTicker.

        Returns:
            TickerSnapshot or None if parsing fails.
        """
        try:
            instrument_token = tick_data.get("instrument_token")
            if not instrument_token:
                return None

            last_price = tick_data.get("last_price")
            if last_price is None:
                return None

            # Extract bid/ask if available (QUOTE mode)
            bid = tick_data.get("buy_quantity", 0)
            ask = tick_data.get("sell_quantity", 0)

            if bid == 0:
                bid = last_price
            if ask == 0:
                ask = last_price

            volume = tick_data.get("volume_traded", 0)

            # Determine symbol from instrument token
            symbol = str(instrument_token)

            return TickerSnapshot(
                exchange=Exchange.NSE,
                symbol=symbol,
                bid=create_price(str(bid)),
                ask=create_price(str(ask)),
                last=create_price(str(last_price)),
                volume_24h=create_quantity(str(volume)),
                source="kite-ticker",
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _get_instrument_tokens(self, symbols: set[tuple[str, Exchange]]) -> list[int]:
        """Get instrument tokens for symbols.

        In production, this would query the instrument master.
        For now, we use the symbol string as a token placeholder.

        Args:
            symbols: Set of (symbol, exchange) tuples.

        Returns:
            List of instrument tokens.
        """
        tokens = []
        for symbol, _ in symbols:
            try:
                token = int(symbol)
                tokens.append(token)
            except ValueError:
                pass
        return tokens

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env_var: str = "ZERODHA_API_KEY",
        access_token_env_var: str = "ZERODHA_ACCESS_TOKEN",  # noqa: S107
        max_reconnect_attempts: int = _MAX_RECONNECT_ATTEMPTS,
        initial_reconnect_delay: float = _INITIAL_RECONNECT_DELAY,
        max_reconnect_delay: float = _MAX_RECONNECT_DELAY,
        reconnect_backoff_multiplier: float = _RECONNECT_BACKOFF_MULTIPLIER,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
        tick_buffer_size: int = _TICK_BUFFER_SIZE,
    ) -> KiteTickerFeed:
        """Create feed from environment variables.

        Args:
            api_key_env_var: Environment variable name for API key.
            access_token_env_var: Environment variable name for access token.
            max_reconnect_attempts: Maximum reconnection attempts.
            initial_reconnect_delay: Initial reconnect delay in seconds.
            max_reconnect_delay: Maximum reconnect delay in seconds.
            reconnect_backoff_multiplier: Backoff multiplier.
            heartbeat_interval: Heartbeat interval in seconds.
            tick_buffer_size: Tick buffer size.

        Returns:
            Configured KiteTickerFeed instance.

        Raises:
            ConfigError: If required environment variables not set.
        """
        api_key, access_token = cls._load_env_vars(api_key_env_var, access_token_env_var)

        return cls(
            api_key=api_key,
            access_token=access_token,
            max_reconnect_attempts=max_reconnect_attempts,
            initial_reconnect_delay=initial_reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            reconnect_backoff_multiplier=reconnect_backoff_multiplier,
            heartbeat_interval=heartbeat_interval,
            tick_buffer_size=tick_buffer_size,
        )

    @staticmethod
    def _load_env_vars(api_key_env_var: str, access_token_env_var: str) -> tuple[str, str]:
        """Load and validate environment variables.

        Args:
            api_key_env_var: Environment variable name for API key.
            access_token_env_var: Environment variable name for access token.

        Returns:
            Tuple of (api_key, access_token).

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

        return api_key, access_token
