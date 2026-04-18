"""
YFinance-backed market data provider for NSE and BSE instruments.
"""

import asyncio
import importlib
import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_LOGGER = logging.getLogger(__name__)

_SUPPORTED_EXCHANGES = frozenset({Exchange.NSE, Exchange.BSE})

_INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m",
    "1d": "1d",
}


def _ensure_supported_exchange(exchange: Exchange) -> None:
    if exchange in _SUPPORTED_EXCHANGES:
        return
    msg = f"Unsupported exchange for yfinance provider: {exchange.value}"
    raise ConfigError(msg)


def _map_symbol(symbol: str, exchange: Exchange) -> str:
    if exchange == Exchange.NSE:
        return f"{symbol}.NS"
    if exchange == Exchange.BSE:
        return f"{symbol}.BO"
    msg = f"Unsupported exchange for yfinance provider: {exchange.value}"
    raise ConfigError(msg)


def _map_timeframe(timeframe: str) -> str:
    interval = _INTERVAL_MAP.get(timeframe)
    if interval is None:
        msg = f"Unsupported yfinance timeframe: {timeframe}"
        raise ConfigError(msg)
    return interval


NumericInput = str | int | Decimal


def _extract_numeric(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
    default: object = 0,
) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _coerce_numeric_input(value: object, *, field_name: str) -> NumericInput:
    if isinstance(value, bool):
        msg = f"{field_name} must not be boolean"
        raise ConfigError(msg)
    if isinstance(value, Decimal | int | str):
        return value
    # API boundary conversion: yfinance returns float, convert to str for Decimal
    if isinstance(value, float):
        return str(value)
    msg = f"{field_name} must be numeric-compatible, got {type(value).__name__}"
    raise ConfigError(msg)


def _ensure_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if hasattr(value, "to_pydatetime"):
        converted = value.to_pydatetime()
        if isinstance(converted, datetime):
            return converted if converted.tzinfo is not None else converted.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp from yfinance history: {type(value).__name__}"
    raise ConfigError(msg)


def _history_rows(history: Any) -> Iterable[tuple[object, Mapping[str, object]]]:
    """Extract rows from yfinance history using vectorized operations.

    This implementation uses to_dict('records') for 10-100x performance improvement
    over iterrows() for large DataFrames. Target: 30-day data for 10 symbols in <500ms.

    Falls back to iterrows() if to_dict() fails or is not available.
    """
    # Try vectorized approach first
    if hasattr(history, "to_dict"):
        try:
            records = history.to_dict("records")
            for idx, payload in enumerate(records):
                if not isinstance(payload, Mapping):
                    msg = "yfinance row payload must be mapping-like"
                    raise ConfigError(msg)
                # Use index as timestamp if not in payload (yfinance behavior)
                timestamp = history.index[idx] if hasattr(history, "index") else idx
                yield timestamp, payload
            return
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("to_dict() failed, falling back to iterrows(): %s", exc)

    # Fallback to iterrows() for backward compatibility
    if not hasattr(history, "iterrows"):
        msg = "yfinance history response must support to_dict() or iterrows()"
        raise ConfigError(msg)
    rows = history.iterrows()
    for timestamp, payload in rows:
        if not isinstance(payload, Mapping):
            msg = "yfinance row payload must be mapping-like"
            raise ConfigError(msg)
        yield timestamp, payload


class YFinanceProvider(DataProvider):
    """Market data provider powered by yfinance historical endpoints."""

    def __init__(self, client_factory: Callable[[str], object] | None = None) -> None:
        self._client_factory = client_factory or self._default_client_factory

    @staticmethod
    def _default_client_factory(symbol: str) -> object:
        try:
            module = importlib.import_module("yfinance")
        except ModuleNotFoundError as exc:
            msg = "yfinance dependency is required for YFinanceProvider"
            raise ConfigError(msg) from exc
        return module.Ticker(symbol)

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Timestamp | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        if limit <= 0:
            msg = "limit must be positive"
            raise ConfigError(msg)
        _ensure_supported_exchange(exchange)
        yf_symbol = _map_symbol(symbol, exchange)
        interval = _map_timeframe(timeframe)
        ticker = self._client_factory(yf_symbol)
        history = await asyncio.to_thread(self._fetch_history, ticker, interval)
        records = self._build_ohlcv_records(history, since=since)
        clipped = records[-limit:]
        return normalize_ohlcv_batch(clipped, symbol=symbol, exchange=exchange, source="yfinance")

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        _ensure_supported_exchange(exchange)
        yf_symbol = _map_symbol(symbol, exchange)
        ticker = self._client_factory(yf_symbol)
        payload = await asyncio.to_thread(self._extract_ticker_payload, ticker)
        bid = _coerce_numeric_input(payload["bid"], field_name="bid")
        ask = _coerce_numeric_input(payload["ask"], field_name="ask")
        last = _coerce_numeric_input(payload["last"], field_name="last")
        volume_24h = _coerce_numeric_input(payload["volume_24h"], field_name="volume_24h")
        snapshot = TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price(bid),
            ask=create_price(ask),
            last=create_price(last),
            volume_24h=create_quantity(volume_24h),
            source="yfinance",
        )
        validate_ticker_snapshot(snapshot)
        return snapshot

    @staticmethod
    def _fetch_history(ticker: object, interval: str) -> object:
        if not hasattr(ticker, "history"):
            msg = "yfinance ticker client must expose history()"
            raise ConfigError(msg)
        history = ticker.history(interval=interval, period="max")
        if history is None:
            msg = "yfinance history response is empty"
            raise ConfigError(msg)
        return history

    @staticmethod
    def _build_ohlcv_records(history: object, since: Timestamp | None) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for timestamp, payload in _history_rows(history):
            normalized_timestamp = _ensure_datetime(timestamp).astimezone(UTC)
            if since is not None and normalized_timestamp < since:
                continue
            records.append(
                {
                    "timestamp": create_timestamp(normalized_timestamp),
                    "open": _extract_numeric(payload, ("Open", "open")),
                    "high": _extract_numeric(payload, ("High", "high")),
                    "low": _extract_numeric(payload, ("Low", "low")),
                    "close": _extract_numeric(payload, ("Close", "close")),
                    "volume": _extract_numeric(payload, ("Volume", "volume")),
                }
            )
        return records

    @staticmethod
    def _extract_ticker_payload(ticker: object) -> dict[str, object]:
        fast_info = getattr(ticker, "fast_info", {})
        info_payload = fast_info if isinstance(fast_info, Mapping) else {}
        fallback_info = getattr(ticker, "info", {})
        info = fallback_info if isinstance(fallback_info, Mapping) else {}
        last = _extract_numeric(
            info_payload,
            ("lastPrice", "last_price"),
            _extract_numeric(info, ("currentPrice", "regularMarketPrice")),
        )
        bid = _extract_numeric(info_payload, ("bid",), last)
        ask = _extract_numeric(info_payload, ("ask",), last)
        volume = _extract_numeric(
            info_payload,
            ("lastVolume", "volume"),
            _extract_numeric(info, ("volume",), 0),
        )
        return {"bid": bid, "ask": ask, "last": last, "volume_24h": volume}
