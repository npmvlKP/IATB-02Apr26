"""
OpenAlgo HTTP provider for market OHLCV and ticker data.

Includes Zerodha authentication flow and per-exchange feed status tracking.
Reference: marketcalls/openalgo (AGPL-3.0)
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import Timestamp, create_price, create_quantity
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.normalizer import normalize_ohlcv_batch
from iatb.data.validator import validate_ticker_snapshot

_LOGGER = logging.getLogger(__name__)
_DEFAULT_TIMEOUT_SECONDS = 20
NumericInput = str | int | Decimal
_SUPPORTED_ZERODHA_EXCHANGES = (Exchange.NSE, Exchange.CDS, Exchange.MCX)


class FeedStatus(StrEnum):
    """Status of a data feed for a specific exchange."""

    LIVE = "LIVE"
    FALLBACK = "FALLBACK"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ExchangeFeedState:
    """Feed state for a single exchange."""

    exchange: Exchange
    status: FeedStatus
    source: str
    checked_at_utc: datetime
    error: str | None = None


@dataclass
class DataFeedStatus:
    """Aggregate feed status across all configured exchanges."""

    exchanges: dict[Exchange, ExchangeFeedState] = field(default_factory=dict)

    def summary_line(self) -> str:
        parts: list[str] = []
        for exchange in _SUPPORTED_ZERODHA_EXCHANGES:
            state = self.exchanges.get(exchange)
            if state is None:
                parts.append(f"{exchange.value}: UNAVAILABLE")
            else:
                parts.append(f"{exchange.value}: {state.status.value}")
        return "Data feed initialized – " + ", ".join(parts)


class ZerodhaAuth:
    """Zerodha/OpenAlgo authentication flow for paper trading mode.

    Reads credentials from .env (ZERODHA_ACCESS_TOKEN or
    ZERODHA_REQUEST_TOKEN) and validates them against the OpenAlgo
    server.  No live trading orders are placed – paper/analyze mode only.
    """

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str | None = None,
        access_token_env: str = "ZERODHA_ACCESS_TOKEN",  # noqa: S107
        request_token_env: str = "ZERODHA_REQUEST_TOKEN",  # noqa: S107
        api_key_env: str = "ZERODHA_API_KEY",
        api_secret_env: str = "ZERODHA_API_SECRET",  # noqa: S107
        http_post: Callable[[str, Mapping[str, str], bytes], Mapping[str, object]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        _validate_http_url(self._base_url)
        self._access_token = access_token or os.getenv(access_token_env)
        self._request_token = os.getenv(request_token_env)
        self._api_key = os.getenv(api_key_env)
        self._api_secret = os.getenv(api_secret_env)
        self._http_post = http_post or self._default_http_post
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    def authenticate(self) -> str:
        """Perform authentication and return the access token."""
        if self._access_token:
            self._authenticated = True
            _LOGGER.info("Zerodha auth: using existing access token")
            return self._access_token
        if not self._request_token:
            msg = "Zerodha auth: no access_token or request_token in environment"
            raise ConfigError(msg)
        if not self._api_key or not self._api_secret:
            msg = "Zerodha auth: API_KEY and API_SECRET required for request_token exchange"
            raise ConfigError(msg)
        token = self._exchange_request_token()
        self._access_token = token
        self._authenticated = True
        return token

    def _exchange_request_token(self) -> str:
        """Exchange request_token for access_token via OpenAlgo."""
        url = f"{self._base_url}/api/v1/auth/token"
        body = json.dumps(
            {
                "request_token": self._request_token,
                "api_key": self._api_key,
                "api_secret": self._api_secret,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        payload = self._http_post(url, headers, body)
        data = payload.get("data")
        if isinstance(data, Mapping):
            token = data.get("access_token")
            if isinstance(token, str) and token:
                _LOGGER.info("Zerodha auth: request_token exchanged successfully")
                return token
        msg = "Zerodha auth: failed to exchange request_token"
        raise ConfigError(msg)

    @staticmethod
    def _default_http_post(
        url: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, object]:
        request = Request(url=url, headers=dict(headers), data=body, method="POST")  # noqa: S310  # nosec B310
        with urlopen(request, timeout=_DEFAULT_TIMEOUT_SECONDS) as response:  # noqa: S310  # nosec B310
            payload = response.read().decode("utf-8")
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            msg = "Zerodha auth response is not valid JSON"
            raise ConfigError(msg) from exc
        if not isinstance(decoded, Mapping):
            msg = "Zerodha auth response must decode into JSON object"
            raise ConfigError(msg)
        return decoded


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


def check_exchange_feed(
    provider: OpenAlgoProvider,
    exchange: Exchange,
) -> ExchangeFeedState:
    """Check if a data feed is available for a specific exchange via OpenAlgo."""
    now = datetime.now(UTC)
    try:
        import asyncio as _aio

        coro = provider.get_ticker(symbol="NIFTY 50", exchange=exchange)
        try:
            loop = _aio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                loop.run_in_executor(pool, lambda: _aio.run(coro))
        except RuntimeError:
            _aio.run(coro)
        return ExchangeFeedState(
            exchange=exchange,
            status=FeedStatus.LIVE,
            source="Zerodha/OpenAlgo",
            checked_at_utc=now,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Exchange %s feed check failed: %s", exchange.value, exc)
        return ExchangeFeedState(
            exchange=exchange,
            status=FeedStatus.FALLBACK,
            source="jugaad-data (EOD)",
            checked_at_utc=now,
            error=str(exc),
        )


def initialize_feed_status(
    auth: ZerodhaAuth,
    provider: OpenAlgoProvider,
    exchanges: tuple[Exchange, ...] = _SUPPORTED_ZERODHA_EXCHANGES,
) -> DataFeedStatus:
    """Initialize and return feed status for all configured exchanges."""
    status = DataFeedStatus()
    for exchange in exchanges:
        if auth.is_authenticated:
            state = check_exchange_feed(provider, exchange)
        else:
            state = ExchangeFeedState(
                exchange=exchange,
                status=FeedStatus.FALLBACK,
                source="jugaad-data (EOD)",
                checked_at_utc=datetime.now(UTC),
                error="Not authenticated",
            )
        status.exchanges[exchange] = state
    _LOGGER.info(status.summary_line())
    return status
