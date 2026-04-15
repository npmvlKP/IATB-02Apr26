"""
WebSocket-based real-time market data provider using KiteTicker.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
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

        self._api_key = api_key
        self._access_token = access_token
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._kite_ticker_factory = kite_ticker_factory or self._default_ticker_factory

        self._tickers: dict[str, CandleBuilder] = {}
        self._latest_tickers: dict[str, TickerSnapshot] = {}
        self._is_connected = False
        self._ticker_instance: Any = None
        self._tick_queue: asyncio.Queue[Tick] = asyncio.Queue()
        self._tick_processor_task: asyncio.Task[None] | None = None

    @staticmethod
    def _default_ticker_factory(api_key: str, access_token: str) -> Any:
        try:
            from kiteconnect import KiteTicker  # type: ignore

            return KiteTicker(api_key, access_token)
        except ModuleNotFoundError as exc:
            msg = "kiteconnect dependency is required for KiteWebSocketProvider"
            raise ConfigError(msg) from exc

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._is_connected:
            return

        self._ticker_instance = await asyncio.to_thread(
            self._kite_ticker_factory,
            self._api_key,
            self._access_token,
        )

        self._setup_tick_handlers()
        await self._start_connection()
        self._start_tick_processor()
        self._is_connected = True

    async def disconnect(self) -> None:
        """Disconnect WebSocket and cleanup resources."""
        if not self._is_connected:
            return

        if self._tick_processor_task:
            self._tick_processor_task.cancel()
            try:
                await self._tick_processor_task
            except asyncio.CancelledError:
                pass
            except RuntimeError:
                # Event loop is closed during shutdown, ignore
                pass

        if self._ticker_instance:
            await asyncio.to_thread(self._ticker_instance.close)

        self._is_connected = False
        self._tickers.clear()
        self._latest_tickers.clear()

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
        """Start the WebSocket connection with retries."""
        for attempt in range(1, self._max_retries + 1):
            try:
                await asyncio.to_thread(self._ticker_instance.connect)
                return
            except Exception as exc:
                if attempt >= self._max_retries:
                    msg = f"Failed to connect after {self._max_retries} attempts: {exc}"
                    raise ConfigError(msg) from exc
                await asyncio.sleep(self._retry_delay_seconds * attempt)

    def _setup_tick_handlers(self) -> None:
        """Setup tick event handlers."""
        self._ticker_instance.on_ticks = self._on_ticks
        self._ticker_instance.on_connect = self._on_connect
        self._ticker_instance.on_close = self._on_close
        self._ticker_instance.on_error = self._on_error

    def _on_ticks(self, ws: Any, ticks: list[dict[str, object]]) -> None:
        """Handle incoming ticks."""
        for tick_data in ticks:
            tick = self._parse_tick(tick_data)
            if tick:
                asyncio.create_task(self._tick_queue.put(tick))

    def _on_connect(self, ws: Any, response: dict[str, object]) -> None:
        """Handle connection event."""
        pass

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection close event."""
        self._is_connected = False

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        """Handle connection error event."""
        pass

    def _start_tick_processor(self) -> None:
        """Start the background tick processor task."""
        self._tick_processor_task = asyncio.create_task(self._process_ticks())

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
        )
