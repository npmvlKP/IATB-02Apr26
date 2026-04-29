"""
WebSocket-based real-time market data provider using KiteTicker.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import (
    Price,
    Quantity,
    Timestamp,
    create_price,
    create_quantity,
    create_timestamp,
)
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot

_TICK_QUEUE_MAXSIZE = 10000
_LOGGER = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass(frozen=True)
class Tick:
    """Normalized tick data from Kite WebSocket."""

    event_id: str
    timestamp: Timestamp
    exchange: Exchange
    symbol: str
    last_price: Price
    volume: Quantity
    mode: str = "quote"


@dataclass
class CandleBuilder:
    """Aggregates ticks into OHLCV candles."""

    symbol: str
    exchange: Exchange
    timeframe: str
    current_candle: dict[str, object] = field(default_factory=dict)
    candle_queue: list[OHLCVBar] = field(default_factory=list)

    def add_tick(self, tick: Tick) -> None:
        """Add a tick to the current candle or start a new one."""
        timestamp_utc = tick.timestamp.astimezone(UTC)
        candle_timestamp = self._candle_timestamp(timestamp_utc)

        if not self.current_candle or self._new_candle_needed(candle_timestamp):
            if self.current_candle:
                self._finalize_candle()
            self._start_candle(tick, candle_timestamp)

        self._update_candle(tick)

    def get_candles(self) -> list[OHLCVBar]:
        """Get completed candles."""
        candles = self.candle_queue.copy()
        self.candle_queue.clear()
        return candles

    def finalize_current_candle(self) -> OHLCVBar | None:
        """Finalize the current candle if it has data."""
        if not self.current_candle:
            return None
        self._finalize_candle()
        if self.candle_queue:
            return self.candle_queue.pop()
        return None

    def _candle_timestamp(self, timestamp: datetime) -> datetime:
        """Calculate the candle timestamp based on timeframe."""
        if self.timeframe == "1m":
            return timestamp.replace(second=0, microsecond=0)
        if self.timeframe == "5m":
            minute = (timestamp.minute // 5) * 5
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        if self.timeframe == "15m":
            minute = (timestamp.minute // 15) * 15
            return timestamp.replace(minute=minute, second=0, microsecond=0)
        if self.timeframe == "1h":
            return timestamp.replace(minute=0, second=0, microsecond=0)
        if self.timeframe == "1d":
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        msg = f"Unsupported timeframe: {self.timeframe}"
        raise ConfigError(msg)

    def _new_candle_needed(self, candle_timestamp: datetime) -> bool:
        """Check if a new candle is needed."""
        current_ts = cast(datetime, self.current_candle.get("timestamp"))
        return candle_timestamp != current_ts

    def _start_candle(self, tick: Tick, candle_timestamp: datetime) -> None:
        """Start a new candle from the tick."""
        self.current_candle = {
            "timestamp": candle_timestamp,
            "open": tick.last_price,
            "high": tick.last_price,
            "low": tick.last_price,
            "close": tick.last_price,
            "volume": create_quantity("0"),
        }

    def _update_candle(self, tick: Tick) -> None:
        """Update the current candle with tick data."""
        current_high = cast(Price, self.current_candle.get("high"))
        current_low = cast(Price, self.current_candle.get("low"))
        current_volume = cast(Quantity, self.current_candle.get("volume"))

        self.current_candle["high"] = max(current_high, tick.last_price)
        self.current_candle["low"] = min(current_low, tick.last_price)
        self.current_candle["close"] = tick.last_price
        self.current_candle["volume"] = create_quantity(
            str(Decimal(current_volume) + Decimal(tick.volume))
        )

    def _finalize_candle(self) -> None:
        """Finalize and queue the current candle."""
        if not self.current_candle:
            return

        candle = OHLCVBar(
            timestamp=create_timestamp(cast(datetime, self.current_candle["timestamp"])),
            exchange=self.exchange,
            symbol=self.symbol,
            open=cast(Price, self.current_candle["open"]),
            high=cast(Price, self.current_candle["high"]),
            low=cast(Price, self.current_candle["low"]),
            close=cast(Price, self.current_candle["close"]),
            volume=cast(Quantity, self.current_candle["volume"]),
            source="kite-ws",
        )
        self.candle_queue.append(candle)


class KiteWebSocketProvider(DataProvider):
    """Real-time market data provider using Kite WebSocket."""

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        kite_ticker_factory: Callable[[str, str], Any] | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 30.0,
        heartbeat_timeout_seconds: float = 90.0,
        max_reconnect_attempts: int = 10,
        reconnect_backoff_base: float = 2.0,
        reconnect_backoff_max: float = 60.0,
    ) -> None:
        self._validate_init_params(
            api_key=api_key,
            access_token=access_token,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            max_reconnect_attempts=max_reconnect_attempts,
            reconnect_backoff_base=reconnect_backoff_base,
            reconnect_backoff_max=reconnect_backoff_max,
        )

        self._api_key = api_key
        self._access_token = access_token
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_backoff_base = reconnect_backoff_base
        self._reconnect_backoff_max = reconnect_backoff_max
        self._kite_ticker_factory = kite_ticker_factory or self._default_ticker_factory

        self._tickers: dict[str, CandleBuilder] = {}
        self._latest_tickers: dict[str, TickerSnapshot] = {}
        self._is_connected = False
        self._connection_state = ConnectionState.DISCONNECTED
        self._ticker_instance: Any = None
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=_TICK_QUEUE_MAXSIZE)
        self._tick_processor_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._last_heartbeat_utc: datetime | None = None
        self._reconnect_attempt = 0
        self._should_stop = False

    @staticmethod
    def _validate_init_params(
        *,
        api_key: str,
        access_token: str,
        max_retries: int,
        retry_delay_seconds: float,
        heartbeat_interval_seconds: float,
        heartbeat_timeout_seconds: float,
        max_reconnect_attempts: int,
        reconnect_backoff_base: float,
        reconnect_backoff_max: float,
    ) -> None:
        if not api_key.strip():
            msg = "api_key cannot be empty"
            raise ConfigError(msg)
        if not access_token.strip():
            msg = "access_token cannot be empty"
            raise ConfigError(msg)
        if max_retries <= 0:
            msg = "max_retries must be positive"
            raise ConfigError(msg)
        if retry_delay_seconds < 0:
            msg = "retry_delay_seconds must be non-negative"
            raise ConfigError(msg)
        if heartbeat_interval_seconds <= 0:
            msg = "heartbeat_interval_seconds must be positive"
            raise ConfigError(msg)
        if heartbeat_timeout_seconds <= 0:
            msg = "heartbeat_timeout_seconds must be positive"
            raise ConfigError(msg)
        if max_reconnect_attempts <= 0:
            msg = "max_reconnect_attempts must be positive"
            raise ConfigError(msg)
        if reconnect_backoff_base <= 1.0:
            msg = "reconnect_backoff_base must be greater than 1.0"
            raise ConfigError(msg)
        if reconnect_backoff_max <= 0:
            msg = "reconnect_backoff_max must be positive"
            raise ConfigError(msg)

    @staticmethod
    def _default_ticker_factory(api_key: str, access_token: str) -> Any:
        try:
            from kiteconnect import KiteTicker  # type: ignore

            return KiteTicker(api_key, access_token)
        except ModuleNotFoundError as exc:
            msg = "kiteconnect dependency is required for KiteWebSocketProvider"
            raise ConfigError(msg) from exc

    async def connect(self) -> None:
        """Establish WebSocket connection with reconnection support."""
        if self._is_connected and self._connection_state == ConnectionState.CONNECTED:
            return

        self._should_stop = False
        self._connection_state = ConnectionState.CONNECTING
        self._reconnect_attempt = 0

        self._ticker_instance = await asyncio.to_thread(
            self._kite_ticker_factory,
            self._api_key,
            self._access_token,
        )

        self._setup_tick_handlers()
        await self._start_connection()
        self._start_tick_processor()
        self._start_heartbeat_monitor()
        self._is_connected = True
        self._connection_state = ConnectionState.CONNECTED
        _LOGGER.info(
            "WebSocket connected",
            extra={"api_key": self._api_key[:8] + "..."},
        )

    async def disconnect(self) -> None:
        """Disconnect WebSocket and cleanup resources."""
        self._should_stop = True

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            except RuntimeError:
                pass
            self._heartbeat_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            except RuntimeError:
                pass
            self._reconnect_task = None

        if not self._is_connected:
            return

        if self._tick_processor_task:
            self._tick_processor_task.cancel()
            try:
                await self._tick_processor_task
            except asyncio.CancelledError:
                pass
            except RuntimeError:
                pass

        if self._ticker_instance:
            await asyncio.to_thread(self._ticker_instance.close)

        self._is_connected = False
        self._connection_state = ConnectionState.DISCONNECTED
        self._tickers.clear()
        self._latest_tickers.clear()
        _LOGGER.info("WebSocket disconnected")

    async def subscribe(self, symbol: str, exchange: Exchange, timeframe: str) -> None:
        """Subscribe to real-time updates for a symbol."""
        if not self._is_connected:
            msg = "Provider not connected. Call connect() first."
            raise ConfigError(msg)

        if symbol not in self._tickers:
            self._tickers[symbol] = CandleBuilder(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
            )

        await self._subscribe_instrument(symbol)

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Fetch aggregated OHLCV bars from WebSocket ticks.

        Note: This returns bars built from real-time ticks since connection.
        For historical data, use JugaadProvider.
        """
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)

        if not self._is_connected:
            msg = "Provider not connected. Call connect() first."
            raise ConfigError(msg)

        if symbol not in self._tickers:
            msg = f"Symbol {symbol} not subscribed. Call subscribe() first."
            raise ConfigError(msg)

        builder = self._tickers[symbol]
        candles = builder.get_candles()

        if since:
            candles = [c for c in candles if c.timestamp >= since]

        return candles[-limit:]

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        """Fetch the latest ticker snapshot from WebSocket."""
        if not self._is_connected:
            msg = "Provider not connected. Call connect() first."
            raise ConfigError(msg)

        if symbol not in self._latest_tickers:
            msg = f"No ticker data available for {symbol}. Subscribe first."
            raise ConfigError(msg)

        return self._latest_tickers[symbol]

    async def get_ohlcv_batch(
        self,
        *,
        symbols: list[str],
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> dict[str, list[OHLCVBar]]:
        """Fetch aggregated OHLCV bars for multiple symbols."""
        results: dict[str, list[OHLCVBar]] = {}
        for symbol in symbols:
            results[symbol] = await self.get_ohlcv(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                since=since,
                limit=limit,
            )
        return results

    async def _start_connection(self) -> None:
        """Start the WebSocket connection with retries and exponential backoff."""
        for attempt in range(1, self._max_retries + 1):
            try:
                await asyncio.to_thread(self._ticker_instance.connect)
                return
            except Exception as exc:
                if attempt >= self._max_retries:
                    msg = f"Failed to connect after {self._max_retries} attempts: {exc}"
                    self._connection_state = ConnectionState.FAILED
                    _LOGGER.error(
                        "WebSocket connection failed",
                        extra={"attempts": attempt, "error": str(exc)},
                    )
                    raise ConfigError(msg) from exc
                delay = self._retry_delay_seconds * attempt
                _LOGGER.warning(
                    "WebSocket connection retry",
                    extra={"attempt": attempt, "delay": delay, "error": str(exc)},
                )
                await asyncio.sleep(delay)

    def _setup_tick_handlers(self) -> None:
        """Setup tick event handlers."""
        self._ticker_instance.on_ticks = self._on_ticks
        self._ticker_instance.on_connect = self._on_connect
        self._ticker_instance.on_close = self._on_close
        self._ticker_instance.on_error = self._on_error

    def _on_ticks(self, ws: Any, ticks: list[dict[str, object]]) -> None:
        """Handle incoming ticks."""
        self._last_heartbeat_utc = datetime.now(UTC)
        for tick_data in ticks:
            tick = self._parse_tick(tick_data)
            if tick:
                asyncio.create_task(self._tick_queue.put(tick))

    def _on_connect(self, ws: Any, response: dict[str, object]) -> None:
        """Handle connection event."""
        self._last_heartbeat_utc = datetime.now(UTC)
        _LOGGER.info("WebSocket connection established")

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection close event and trigger reconnection."""
        self._is_connected = False
        self._connection_state = ConnectionState.DISCONNECTED
        _LOGGER.warning(
            "WebSocket connection closed",
            extra={"code": code, "reason": reason},
        )
        if not self._should_stop:
            self._schedule_reconnect()

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection error event and trigger reconnection."""
        _LOGGER.error(
            "WebSocket connection error",
            extra={"code": code, "reason": reason},
        )
        if not self._should_stop:
            self._schedule_reconnect()

    def _start_tick_processor(self) -> None:
        """Start the background tick processor task."""
        self._tick_processor_task = asyncio.create_task(self._process_ticks())

    def _start_heartbeat_monitor(self) -> None:
        """Start the heartbeat monitoring task."""
        self._heartbeat_task = asyncio.create_task(self._monitor_heartbeat())

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_with_backoff())

    async def _reconnect_with_backoff(self) -> None:
        """Reconnect with exponential backoff."""
        if self._should_stop:
            return

        self._connection_state = ConnectionState.RECONNECTING
        self._reconnect_attempt += 1

        if self._reconnect_attempt > self._max_reconnect_attempts:
            _LOGGER.error(
                "Max reconnection attempts reached",
                extra={"attempts": self._reconnect_attempt},
            )
            self._connection_state = ConnectionState.FAILED
            return

        backoff_delay = min(
            self._reconnect_backoff_base**self._reconnect_attempt,
            self._reconnect_backoff_max,
        )

        _LOGGER.info(
            "Scheduling reconnection",
            extra={
                "attempt": self._reconnect_attempt,
                "delay": backoff_delay,
            },
        )

        await asyncio.sleep(backoff_delay)

        if not self._should_stop:
            try:
                await self._perform_reconnect()
            except Exception as exc:
                _LOGGER.error(
                    "Reconnection failed",
                    extra={"attempt": self._reconnect_attempt, "error": str(exc)},
                )
                self._schedule_reconnect()

    async def _perform_reconnect(self) -> None:
        """Perform the actual reconnection."""
        if self._ticker_instance:
            try:
                await asyncio.to_thread(self._ticker_instance.close)
            except Exception:
                _LOGGER.debug("Error closing ticker instance during disconnect")

        self._ticker_instance = await asyncio.to_thread(
            self._kite_ticker_factory,
            self._api_key,
            self._access_token,
        )

        self._setup_tick_handlers()
        await self._start_connection()

        self._is_connected = True
        self._connection_state = ConnectionState.CONNECTED
        self._reconnect_attempt = 0
        self._last_heartbeat_utc = datetime.now(UTC)

        _LOGGER.info(
            "WebSocket reconnected successfully",
            extra={"attempt": self._reconnect_attempt},
        )

    async def _monitor_heartbeat(self) -> None:
        """Monitor heartbeat and detect stale connections."""
        while not self._should_stop:
            try:
                await asyncio.sleep(self._heartbeat_interval_seconds)

                if self._should_stop:
                    break

                now_utc = datetime.now(UTC)

                if self._last_heartbeat_utc is None:
                    self._last_heartbeat_utc = now_utc
                    continue

                time_since_last_heartbeat = now_utc - self._last_heartbeat_utc

                if time_since_last_heartbeat.total_seconds() > self._heartbeat_timeout_seconds:
                    _LOGGER.warning(
                        "Heartbeat timeout detected",
                        extra={
                            "last_heartbeat": self._last_heartbeat_utc.isoformat(),
                            "timeout": self._heartbeat_timeout_seconds,
                        },
                    )
                    if self._is_connected:
                        self._is_connected = False
                        self._connection_state = ConnectionState.DISCONNECTED
                        self._schedule_reconnect()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                _LOGGER.error(
                    "Heartbeat monitor error",
                    extra={"error": str(exc)},
                )

    async def _process_ticks(self) -> None:
        """Process ticks from the queue and update candle builders."""
        while True:
            try:
                tick = await self._tick_queue.get()
                self._process_tick(tick)
                self._tick_queue.task_done()
            except asyncio.CancelledError:
                break
            except RuntimeError:
                # Event loop is closed during shutdown, exit gracefully
                break

    def _process_tick(self, tick: Tick) -> None:
        """Process a single tick."""
        builder = self._tickers.get(tick.symbol)
        if builder:
            builder.add_tick(tick)

        self._update_latest_ticker(tick)

    def _update_latest_ticker(self, tick: Tick) -> None:
        """Update the latest ticker snapshot for the symbol."""
        self._latest_tickers[tick.symbol] = TickerSnapshot(
            exchange=tick.exchange,
            symbol=tick.symbol,
            bid=tick.last_price,
            ask=tick.last_price,
            last=tick.last_price,
            volume_24h=tick.volume,
            source="kite-ws",
        )

    def _parse_tick(self, tick_data: dict[str, object]) -> Tick | None:
        """Parse raw Kite tick data into normalized Tick."""
        try:
            symbol = str(tick_data.get("instrument_token", ""))
            if not symbol:
                return None

            last_price = tick_data.get("last_price")
            if last_price is None:
                return None

            volume = tick_data.get("volume_traded", 0)

            timestamp = datetime.now(UTC)
            exchange_ts = tick_data.get("exchange_timestamp")
            if exchange_ts and isinstance(exchange_ts, datetime):
                timestamp = exchange_ts if exchange_ts.tzinfo else exchange_ts.replace(tzinfo=UTC)

            return Tick(
                event_id=str(tick_data.get("instrument_token", "")),
                timestamp=create_timestamp(timestamp),
                exchange=Exchange.NSE,
                symbol=symbol,
                last_price=create_price(str(last_price)),
                volume=create_quantity(str(volume)),
                mode=str(tick_data.get("mode", "quote")),
            )
        except (ValueError, TypeError, KeyError):
            return None

    async def _subscribe_instrument(self, symbol: str) -> None:
        """Subscribe to instrument updates via WebSocket."""
        if self._ticker_instance and hasattr(self._ticker_instance, "subscribe"):
            await asyncio.to_thread(self._ticker_instance.subscribe, [symbol])

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env_var: str = "ZERODHA_API_KEY",
        access_token_env_var: str = "ZERODHA_ACCESS_TOKEN",  # noqa: S107
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 30.0,
        heartbeat_timeout_seconds: float = 90.0,
        max_reconnect_attempts: int = 10,
        reconnect_backoff_base: float = 2.0,
        reconnect_backoff_max: float = 60.0,
    ) -> KiteWebSocketProvider:
        """Create provider from environment variables."""
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
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            max_reconnect_attempts=max_reconnect_attempts,
            reconnect_backoff_base=reconnect_backoff_base,
            reconnect_backoff_max=reconnect_backoff_max,
        )
