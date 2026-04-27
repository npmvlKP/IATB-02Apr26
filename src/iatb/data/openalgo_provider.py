"""
OpenAlgo HTTP provider for market OHLCV and ticker data.

Uses connection pooling via http.client for efficient TCP connection reuse.
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable, Mapping
from decimal import Decimal
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlencode, urlparse

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_DEFAULT_TIMEOUT_SECONDS = 20
_NUMERIC_INPUT = str | int | Decimal

_LOGGER_P = logging.getLogger(__name__)


class _PooledHTTPSession:
    """Lightweight connection pool using http.client with keep-alive."""

    def __init__(
        self, base_url: str, pool_size: int = 4, timeout: int = _DEFAULT_TIMEOUT_SECONDS
    ) -> None:
        parsed = urlparse(base_url)
        self._scheme = parsed.scheme
        self._host = parsed.netloc
        self._timeout = timeout
        self._pool_size = pool_size
        self._pool: list[HTTPConnection] = []
        self._in_use: set[int] = set()
        if self._scheme == "https":
            self._conn_cls: type[HTTPConnection] | type[HTTPSConnection] = HTTPSConnection
        else:
            self._conn_cls = HTTPConnection

    def _acquire(self) -> HTTPConnection:
        for conn in self._pool:
            if id(conn) not in self._in_use:
                self._in_use.add(id(conn))
                return conn
        if len(self._pool) < self._pool_size:
            conn = self._conn_cls(self._host, timeout=self._timeout)
            self._pool.append(conn)
            self._in_use.add(id(conn))
            return conn
        reused = self._pool[0]
        self._in_use.add(id(reused))
        return reused

    def _release(self, conn: HTTPConnection) -> None:
        self._in_use.discard(id(conn))

    def get(self, path: str, headers: dict[str, str]) -> Mapping[str, object]:
        conn = self._acquire()
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            body = response.read().decode("utf-8")
        except Exception:
            conn.close()
            self._pool = [c for c in self._pool if c is not conn]
            raise
        finally:
            self._release(conn)
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            msg = "OpenAlgo response is not valid JSON"
            raise ConfigError(msg) from exc
        if not isinstance(decoded, Mapping):
            msg = "OpenAlgo response must decode into JSON object"
            raise ConfigError(msg)
        return decoded

    def close(self) -> None:
        for conn in self._pool:
            try:
                conn.close()
            except Exception:
                _LOGGER_P.debug("Connection close error")
        self._pool.clear()
        self._in_use.clear()


def _extract_data_list(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    data = payload.get("data")
    if isinstance(data, list):
        mappings = [item for item in data if isinstance(item, Mapping)]
        if len(mappings) != len(data):
            msg = "OpenAlgo data list must contain mapping objects"
            raise ConfigError(msg)
        return mappings
    msg = "OpenAlgo response missing data list"
    raise ConfigError(msg)


def _extract_data_mapping(payload: Mapping[str, object]) -> Mapping[str, object]:
    data = payload.get("data")
    if isinstance(data, Mapping):
        return data
    msg = "OpenAlgo response missing data mapping"
    raise ConfigError(msg)


def _extract_numeric(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
    default: object = 0,
) -> object:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _coerce_numeric_input(value: object, *, field_name: str) -> _NUMERIC_INPUT:
    if isinstance(value, bool):
        msg = f"{field_name} must not be boolean"
        raise ConfigError(msg)
    if isinstance(value, Decimal | int | str):
        return value
    if isinstance(value, float):
        return str(value)
    msg = f"{field_name} must be numeric-compatible, got {type(value).__name__}"
    raise ConfigError(msg)


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = "OpenAlgo base_url must use http or https"
        raise ConfigError(msg)
    if not parsed.netloc:
        msg = "OpenAlgo base_url must include host"
        raise ConfigError(msg)


class OpenAlgoProvider(DataProvider):
    """HTTP provider using OpenAlgo REST endpoints with connection pooling."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        api_key_env_var: str = "OPENALGO_API_KEY",
        http_get: Callable[[str, Mapping[str, str]], object] | None = None,
        pool_size: int = 4,
    ) -> None:
        resolved_key = api_key or os.getenv(api_key_env_var)
        if not resolved_key:
            msg = "OpenAlgo API key is required"
            raise ConfigError(msg)
        self._base_url = base_url.rstrip("/")
        _validate_http_url(self._base_url)
        self._api_key = resolved_key
        self._http_get = http_get or self._default_http_get
        self._session: _PooledHTTPSession | None = None
        self._pool_size = pool_size

    def _get_session(self) -> _PooledHTTPSession:
        if self._session is None:
            self._session = _PooledHTTPSession(self._base_url, pool_size=self._pool_size)
        return self._session

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
        params = {
            "symbol": symbol,
            "exchange": exchange.value,
            "timeframe": timeframe,
            "limit": str(limit),
        }
        if since is not None:
            params["since"] = since.isoformat()
        payload = await self._request("/api/v1/market/ohlcv", params)
        records = [dict(item) for item in _extract_data_list(payload)]
        return normalize_ohlcv_batch(records, symbol=symbol, exchange=exchange, source="openalgo")

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        payload = await self._request(
            "/api/v1/market/ticker",
            {"symbol": symbol, "exchange": exchange.value},
        )
        data = _extract_data_mapping(payload)
        last = _extract_numeric(data, ("last", "ltp", "close"))
        bid = _extract_numeric(data, ("bid",), last)
        ask = _extract_numeric(data, ("ask",), last)
        volume = _extract_numeric(data, ("volume_24h", "volume"), 0)
        bid_value = _coerce_numeric_input(bid, field_name="bid")
        ask_value = _coerce_numeric_input(ask, field_name="ask")
        last_value = _coerce_numeric_input(last, field_name="last")
        volume_value = _coerce_numeric_input(volume, field_name="volume_24h")
        snapshot = TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price(bid_value),
            ask=create_price(ask_value),
            last=create_price(last_value),
            volume_24h=create_quantity(volume_value),
            source="openalgo",
        )
        validate_ticker_snapshot(snapshot)
        return snapshot

    async def _request(self, path: str, params: Mapping[str, str]) -> Mapping[str, object]:
        url_path = self._build_path(path, params)
        full_url = f"{self._base_url}{url_path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._http_get is not self._default_http_get:
            payload = await asyncio.to_thread(self._http_get, full_url, headers)
        else:
            session = self._get_session()
            payload = await asyncio.to_thread(session.get, url_path, headers)
        if not isinstance(payload, Mapping):
            msg = "OpenAlgo response must be mapping-like JSON"
            raise ConfigError(msg)
        return payload

    def _build_path(self, path: str, params: Mapping[str, str]) -> str:
        encoded = urlencode(params)
        return f"{path}?{encoded}"

    @staticmethod
    def _default_http_get(url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
        parsed = urlparse(url)
        if parsed.scheme == "https":
            conn: HTTPConnection | HTTPSConnection = HTTPSConnection(
                parsed.netloc, timeout=_DEFAULT_TIMEOUT_SECONDS
            )
        else:
            conn = HTTPConnection(parsed.netloc, timeout=_DEFAULT_TIMEOUT_SECONDS)
        try:
            request_path = parsed.path
            if parsed.query:
                request_path += "?" + parsed.query
            conn.request("GET", request_path, headers=dict(headers))
            response = conn.getresponse()
            payload = response.read().decode("utf-8")
        finally:
            conn.close()
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            msg = "OpenAlgo response is not valid JSON"
            raise ConfigError(msg) from exc
        if not isinstance(decoded, Mapping):
            msg = "OpenAlgo response must decode into JSON object"
            raise ConfigError(msg)
        return decoded
