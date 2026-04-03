"""
CCXT-backed provider for crypto exchange market data.
"""

import asyncio
import importlib
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Protocol, cast

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_EXCHANGE_ID_MAP = {
    Exchange.BINANCE: "binance",
    Exchange.COINDCX: "coindcx",
}
NumericInput = str | int | Decimal


class _CCXTExchangeClient(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> object:
        ...

    def fetch_ticker(self, symbol: str) -> object:
        ...


def _exchange_id(exchange: Exchange) -> str:
    exchange_id = _EXCHANGE_ID_MAP.get(exchange)
    if exchange_id is None:
        msg = f"Unsupported exchange for CCXT provider: {exchange.value}"
        raise ConfigError(msg)
    return exchange_id


def _normalize_symbol(symbol: str) -> str:
    if "/" in symbol:
        return symbol
    quote_candidates = ("USDT", "USD", "INR", "BTC", "ETH")
    for quote in quote_candidates:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"
    return symbol


def _extract_numeric(payload: Mapping[str, object], key: str) -> object | None:
    value = payload.get(key)
    return value if value is not None else None


def _coerce_numeric_input(value: object, *, field_name: str) -> NumericInput:
    if isinstance(value, bool):
        msg = f"{field_name} must not be boolean"
        raise ConfigError(msg)
    if isinstance(value, Decimal | int | str):
        return value
    if isinstance(value, float):
        return str(value)
    msg = f"{field_name} must be numeric-compatible, got {type(value).__name__}"
    raise ConfigError(msg)


class CCXTProvider(DataProvider):
    """Crypto market data provider backed by CCXT unified APIs."""

    def __init__(
        self,
        exchange_factory: Callable[[str], _CCXTExchangeClient] | None = None,
    ) -> None:
        self._exchange_factory = exchange_factory or self._default_exchange_factory

    @staticmethod
    def _default_exchange_factory(exchange_id: str) -> _CCXTExchangeClient:
        try:
            module = importlib.import_module("ccxt")
        except ModuleNotFoundError as exc:
            msg = "ccxt dependency is required for CCXTProvider"
            raise ConfigError(msg) from exc
        if not hasattr(module, exchange_id):
            msg = f"ccxt exchange class not found: {exchange_id}"
            raise ConfigError(msg)
        exchange_class = getattr(module, exchange_id)
        return cast(_CCXTExchangeClient, exchange_class({"enableRateLimit": True}))

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
        exchange_id = _exchange_id(exchange)
        normalized_symbol = _normalize_symbol(symbol)
        client = self._exchange_factory(exchange_id)
        since_ms = int(since.timestamp() * 1000) if since is not None else None
        raw_rows = await asyncio.to_thread(
            client.fetch_ohlcv,
            normalized_symbol,
            timeframe,
            since_ms,
            limit,
        )
        records = self._normalize_ohlcv_rows(raw_rows)
        return normalize_ohlcv_batch(
            records,
            symbol=symbol,
            exchange=exchange,
            source=f"ccxt:{exchange_id}",
        )

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        exchange_id = _exchange_id(exchange)
        normalized_symbol = _normalize_symbol(symbol)
        client = self._exchange_factory(exchange_id)
        ticker = await asyncio.to_thread(client.fetch_ticker, normalized_symbol)
        if not isinstance(ticker, Mapping):
            msg = "CCXT ticker response must be mapping-like"
            raise ConfigError(msg)
        payload = self._normalize_ticker_payload(ticker)
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
            source=f"ccxt:{exchange_id}",
        )
        validate_ticker_snapshot(snapshot)
        return snapshot

    @staticmethod
    def _normalize_ohlcv_rows(rows: object) -> list[dict[str, object]]:
        if not isinstance(rows, list):
            msg = "CCXT fetch_ohlcv response must be a list"
            raise ConfigError(msg)
        records: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, list | tuple) or len(row) < 6:
                msg = "CCXT OHLCV row must include timestamp/open/high/low/close/volume"
                raise ConfigError(msg)
            records.append(
                {
                    "timestamp": row[0],
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                }
            )
        return records

    @staticmethod
    def _normalize_ticker_payload(ticker: Mapping[str, object]) -> dict[str, object]:
        last = _extract_numeric(ticker, "last") or _extract_numeric(ticker, "close")
        bid = _extract_numeric(ticker, "bid") or last
        ask = _extract_numeric(ticker, "ask") or last
        volume = (
            _extract_numeric(ticker, "baseVolume") or _extract_numeric(ticker, "quoteVolume") or 0
        )
        if last is None:
            msg = "CCXT ticker response missing last/close value"
            raise ConfigError(msg)
        return {"bid": bid, "ask": ask, "last": last, "volume_24h": volume}
