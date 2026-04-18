"""
Jugaad-data provider for NSE daily historical market data.
"""

import asyncio
import importlib
import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_LOGGER = logging.getLogger(__name__)

_OHLCV_KEYS = {
    "timestamp": ("timestamp", "TIMESTAMP", "date", "DATE"),
    "open": ("open", "OPEN"),
    "high": ("high", "HIGH"),
    "low": ("low", "LOW"),
    "close": ("close", "CLOSE"),
    "volume": ("volume", "VOLUME", "TOTTRDQTY", "TTL_TRD_QNT"),
}


def _extract_value(payload: Mapping[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    msg = f"Missing required OHLCV key from jugaad payload: {keys}"
    raise ConfigError(msg)


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.strip()
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from jugaad payload: {type(value).__name__}"
    raise ConfigError(msg)


def _iter_rows(frame: Any) -> Iterable[Mapping[str, object]]:
    """Extract rows from jugaad data using vectorized operations.

    This implementation uses to_dict('records') for 10-100x performance improvement
    over iterrows() for large DataFrames. Target: 30-day data for 10 symbols in <500ms.

    Falls back to iterrows() if to_dict() fails or is not available.
    """
    # Try vectorized approach first
    if hasattr(frame, "to_dict"):
        try:
            records = frame.to_dict("records")
            for payload in records:
                if not isinstance(payload, Mapping):
                    msg = "jugaad dataframe rows must be mapping-like"
                    raise ConfigError(msg)
                yield payload
            return
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("to_dict() failed, falling back to iterrows(): %s", exc)

    # Fallback to iterrows() for backward compatibility
    if hasattr(frame, "iterrows"):
        for _, payload in frame.iterrows():
            if not isinstance(payload, Mapping):
                msg = "jugaad dataframe rows must be mapping-like"
                raise ConfigError(msg)
            yield payload
        return

    # Support list input for testing
    if isinstance(frame, list):
        for payload in frame:
            if not isinstance(payload, Mapping):
                msg = "jugaad list rows must be mapping-like"
                raise ConfigError(msg)
            yield payload
        return

    msg = "Unsupported jugaad history response type: must be DataFrame or list"
    raise ConfigError(msg)


class JugaadProvider(DataProvider):
    """NSE-focused provider backed by jugaad-data stock_df API."""

    def __init__(self, stock_df_loader: Callable[[], Callable[..., object]] | None = None) -> None:
        self._stock_df_loader = stock_df_loader or self._default_stock_df_loader

    @staticmethod
    def _default_stock_df_loader() -> Callable[..., object]:
        try:
            module = importlib.import_module("jugaad_data.nse")
        except ModuleNotFoundError as exc:
            msg = "jugaad_data dependency is required for JugaadProvider"
            raise ConfigError(msg) from exc
        if not hasattr(module, "stock_df"):
            msg = "jugaad_data.nse.stock_df is not available"
            raise ConfigError(msg)
        return cast(Callable[..., object], module.stock_df)

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        if exchange != Exchange.NSE:
            msg = f"JugaadProvider only supports NSE exchange, got {exchange.value}"
            raise ConfigError(msg)
        if timeframe != "1d":
            msg = f"JugaadProvider supports only 1d timeframe, got {timeframe}"
            raise ConfigError(msg)
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        stock_df = self._stock_df_loader()
        from_date, to_date = self._history_window(since, limit)
        frame = await asyncio.to_thread(
            stock_df,
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
        )
        records = self._records_from_history(frame, since=since)
        clipped = records[-limit:]
        return normalize_ohlcv_batch(clipped, symbol=symbol, exchange=exchange, source="jugaad")

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        bars = await self.get_ohlcv(symbol=symbol, exchange=exchange, timeframe="1d", limit=1)
        if not bars:
            msg = f"No market data found for symbol {symbol}"
            raise ConfigError(msg)
        latest = bars[-1]
        snapshot = TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price(latest.close),
            ask=create_price(latest.close),
            last=create_price(latest.close),
            volume_24h=create_quantity(latest.volume),
            source="jugaad",
        )
        validate_ticker_snapshot(snapshot)
        return snapshot

    @staticmethod
    def _history_window(since: Timestamp | None, limit: int) -> tuple[date, date]:
        now = datetime.now(UTC)
        end_date = now.date()
        if since is not None:
            return since.date(), end_date
        lookback_days = max(30, limit * 2)
        return (now - timedelta(days=lookback_days)).date(), end_date

    @staticmethod
    def _records_from_history(frame: object, since: Timestamp | None) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for payload in _iter_rows(frame):
            timestamp = _coerce_datetime(
                _extract_value(payload, _OHLCV_KEYS["timestamp"])
            ).astimezone(UTC)
            if since is not None and timestamp < since:
                continue
            records.append(
                {
                    "timestamp": create_timestamp(timestamp),
                    "open": _extract_value(payload, _OHLCV_KEYS["open"]),
                    "high": _extract_value(payload, _OHLCV_KEYS["high"]),
                    "low": _extract_value(payload, _OHLCV_KEYS["low"]),
                    "close": _extract_value(payload, _OHLCV_KEYS["close"]),
                    "volume": _extract_value(payload, _OHLCV_KEYS["volume"]),
                }
            )
        return records
