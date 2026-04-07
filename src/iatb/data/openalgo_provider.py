"""
OpenAlgo HTTP provider for market OHLCV and ticker data.
"""

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from decimal import Decimal
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_DEFAULT_TIMEOUT_SECONDS = 20
NumericInput = str | int | Decimal


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


def _validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        msg = "OpenAlgo base_url must use http or https"
        raise ConfigError(msg)
    if not parsed.netloc:
        msg = "OpenAlgo base_url must include host"
        raise ConfigError(msg)


class OpenAlgoProvider(DataProvider):
    """HTTP provider using OpenAlgo REST endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        api_key_env_var: str = "OPENALGO_API_KEY",
        http_get: Callable[[str, Mapping[str, str]], object] | None = None,
    ) -> None:
        resolved_key = api_key or os.getenv(api_key_env_var)
        if not resolved_key:
            msg = "OpenAlgo API key is required"
            raise ConfigError(msg)
        self._base_url = base_url.rstrip("/")
        _validate_http_url(self._base_url)
        self._api_key = resolved_key
        self._http_get = http_get or self._default_http_get

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
        url = self._build_url(path, params)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = await asyncio.to_thread(self._http_get, url, headers)
        if not isinstance(payload, Mapping):
            msg = "OpenAlgo response must be mapping-like JSON"
            raise ConfigError(msg)
        return payload

    def _build_url(self, path: str, params: Mapping[str, str]) -> str:
        encoded = urlencode(params)
        return f"{self._base_url}{path}?{encoded}"

    @staticmethod
    def _default_http_get(url: str, headers: Mapping[str, str]) -> Mapping[str, object]:
        request = Request(url=url, headers=dict(headers), method="GET")  # noqa: S310  # nosec B310
        with urlopen(request, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:  # noqa: S310  # nosec B310
            payload = response.read().decode("utf-8")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            msg = "OpenAlgo response is not valid JSON"
            raise ConfigError(msg) from exc
        if not isinstance(decoded, Mapping):
            msg = "OpenAlgo response must decode into JSON object"
            raise ConfigError(msg)
        return decoded
