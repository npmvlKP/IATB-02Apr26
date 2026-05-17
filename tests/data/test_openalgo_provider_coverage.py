"""
Comprehensive coverage tests for OpenAlgo provider.

Covers: get_ohlcv, get_ticker, connection pooling, HTTP GET,
API key from env, JSON decode error, invalid URL, numeric coercion,
_extract_data_list, _extract_data_mapping, _extract_numeric,
_coerce_numeric_input, _validate_http_url, _PooledHTTPSession,
_build_path, _default_http_get, _request, since parameter.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity
from iatb.data.base import TickerSnapshot
from iatb.data.openalgo_provider import (
    OpenAlgoProvider,
    _coerce_numeric_input,
    _extract_data_list,
    _extract_data_mapping,
    _extract_numeric,
    _PooledHTTPSession,
    _validate_http_url,
)


def _http_get_factory(
    responses: dict[str, dict[str, object]],
) -> Any:
    def _http_get(url: str, headers: Mapping[str, str]) -> dict[str, object]:
        _ = headers
        for key, payload in responses.items():
            if key in url:
                return payload
        return {"data": []}

    return _http_get


_VALID_OHLCV_PAYLOAD: dict[str, object] = {
    "data": [
        {
            "timestamp": "2026-01-01T09:15:00+00:00",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 1000,
        },
        {
            "timestamp": "2026-01-01T09:16:00+00:00",
            "open": 101,
            "high": 103,
            "low": 100,
            "close": 102,
            "volume": 1100,
        },
    ]
}

_VALID_TICKER_PAYLOAD: dict[str, object] = {
    "data": {
        "bid": 100.5,
        "ask": 101.5,
        "last": 101,
        "volume_24h": 900,
    }
}


class TestExtractDataList:
    def test_valid_list_of_mappings(self) -> None:
        payload: dict[str, object] = {"data": [{"a": 1}, {"b": 2}]}
        result = _extract_data_list(payload)
        assert len(result) == 2

    def test_missing_data_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data list"):
            _extract_data_list({"other": []})

    def test_data_is_not_list_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data list"):
            _extract_data_list({"data": "not-a-list"})

    def test_data_list_contains_non_mapping_raises(self) -> None:
        with pytest.raises(ConfigError, match="must contain mapping objects"):
            _extract_data_list({"data": [{"a": 1}, "non-mapping", 42]})

    def test_empty_data_list_returns_empty(self) -> None:
        result = _extract_data_list({"data": []})
        assert result == []

    def test_data_is_none_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data list"):
            _extract_data_list({"data": None})


class TestExtractDataMapping:
    def test_valid_mapping(self) -> None:
        payload: dict[str, object] = {"data": {"bid": 100, "ask": 101}}
        result = _extract_data_mapping(payload)
        assert result == {"bid": 100, "ask": 101}

    def test_missing_data_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data mapping"):
            _extract_data_mapping({"other": {"a": 1}})

    def test_data_is_list_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data mapping"):
            _extract_data_mapping({"data": [1, 2, 3]})

    def test_data_is_none_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data mapping"):
            _extract_data_mapping({"data": None})

    def test_data_is_string_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing data mapping"):
            _extract_data_mapping({"data": "string-value"})


class TestExtractNumeric:
    def test_first_key_present(self) -> None:
        payload: dict[str, object] = {"ltp": 105.5, "last": 100}
        result = _extract_numeric(payload, ("ltp", "last"), 0)
        assert result == 105.5

    def test_second_key_fallback(self) -> None:
        payload: dict[str, object] = {"last": 100}
        result = _extract_numeric(payload, ("ltp", "last"), 0)
        assert result == 100

    def test_no_keys_present_returns_default(self) -> None:
        payload: dict[str, object] = {"other": 999}
        result = _extract_numeric(payload, ("ltp", "last"), 42)
        assert result == 42

    def test_key_present_but_none_returns_default(self) -> None:
        payload: dict[str, object] = {"ltp": None, "last": None}
        result = _extract_numeric(payload, ("ltp", "last"), 0)
        assert result == 0

    def test_empty_keys_tuple_returns_default(self) -> None:
        payload: dict[str, object] = {"ltp": 100}
        result = _extract_numeric(payload, (), 99)
        assert result == 99

    def test_empty_payload_returns_default(self) -> None:
        result = _extract_numeric({}, ("last", "close"), 7)
        assert result == 7


class TestCoerceNumericInput:
    def test_decimal_value(self) -> None:
        result = _coerce_numeric_input(Decimal("100.5"), field_name="price")
        assert result == Decimal("100.5")

    def test_int_value(self) -> None:
        result = _coerce_numeric_input(42, field_name="qty")
        assert result == 42

    def test_str_value(self) -> None:
        result = _coerce_numeric_input("150.75", field_name="price")
        assert result == "150.75"

    def test_float_value_converts_to_str(self) -> None:
        result = _coerce_numeric_input(99.9, field_name="price")
        assert result == str(99.9)

    def test_bool_value_raises(self) -> None:
        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(True, field_name="price")

    def test_bool_false_raises(self) -> None:
        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(False, field_name="price")

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ConfigError, match="numeric-compatible"):
            _coerce_numeric_input([1, 2, 3], field_name="price")

    def test_none_value_raises(self) -> None:
        with pytest.raises(ConfigError, match="numeric-compatible"):
            _coerce_numeric_input(None, field_name="price")

    def test_dict_value_raises(self) -> None:
        with pytest.raises(ConfigError, match="numeric-compatible"):
            _coerce_numeric_input({"a": 1}, field_name="price")


class TestValidateHttpUrl:
    def test_valid_https(self) -> None:
        _validate_http_url("https://api.example.com")

    def test_valid_http(self) -> None:
        _validate_http_url("http://localhost:8080")

    def test_ftp_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            _validate_http_url("ftp://files.example.com")

    def test_empty_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            _validate_http_url("api.example.com")

    def test_no_host_raises(self) -> None:
        with pytest.raises(ConfigError, match="must include host"):
            _validate_http_url("https://")

    def test_file_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            _validate_http_url("file:///local/path")


class TestPooledHTTPSession:
    def test_init_http_scheme(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        assert session._conn_cls is HTTPConnection
        assert session._host == "localhost:8080"
        session.close()

    def test_init_https_scheme(self) -> None:
        session = _PooledHTTPSession("https://api.example.com", pool_size=2)
        assert session._conn_cls is HTTPSConnection
        assert session._host == "api.example.com"
        session.close()

    def test_acquire_creates_new_connection(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=4)
        conn = session._acquire()
        assert conn is not None
        assert len(session._pool) == 1
        session.close()

    def test_acquire_reuses_idle_connection(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=4)
        conn1 = session._acquire()
        session._release(conn1)
        conn2 = session._acquire()
        assert conn2 is conn1
        session.close()

    def test_acquire_pool_exhausted_reuses_first(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=1)
        conn1 = session._acquire()
        conn2 = session._acquire()
        assert conn2 is conn1
        session.close()

    def test_release_removes_from_in_use(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=4)
        conn = session._acquire()
        assert id(conn) in session._in_use
        session._release(conn)
        assert id(conn) not in session._in_use
        session.close()

    def test_get_successful_request(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"key": "value"}}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        session._pool = [mock_conn]
        session._in_use = set()
        result = session.get("/api/test", {"Auth": "Bearer key"})
        assert isinstance(result, Mapping)
        assert result.get("data") == {"key": "value"}
        session.close()

    def test_get_http_error_closes_conn_and_raises(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        mock_conn = MagicMock()
        mock_conn.request.side_effect = ConnectionError("refused")
        mock_conn.close = MagicMock()
        session._pool = [mock_conn]
        session._in_use = set()
        with pytest.raises(ConnectionError, match="refused"):
            session.get("/api/test", {"Auth": "Bearer key"})
        mock_conn.close.assert_called_once()
        assert mock_conn not in session._pool
        session.close()

    def test_get_json_decode_error_raises_config_error(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"not-valid-json"
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        session._pool = [mock_conn]
        session._in_use = set()
        with pytest.raises(ConfigError, match="not valid JSON"):
            session.get("/api/test", {"Auth": "Bearer key"})
        session.close()

    def test_get_non_mapping_json_raises_config_error(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"[1, 2, 3]"
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        session._pool = [mock_conn]
        session._in_use = set()
        with pytest.raises(ConfigError, match="must decode into JSON object"):
            session.get("/api/test", {"Auth": "Bearer key"})
        session.close()

    def test_close_clears_pool_and_in_use(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        session._acquire()
        session.close()
        assert len(session._pool) == 0
        assert len(session._in_use) == 0

    def test_close_handles_conn_close_error(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        mock_conn = MagicMock()
        mock_conn.close.side_effect = OSError("close error")
        session._pool = [mock_conn]
        session._in_use = set()
        session.close()
        assert len(session._pool) == 0

    def test_pool_size_limit_creates_up_to_pool_size(self) -> None:
        session = _PooledHTTPSession("http://localhost:8080", pool_size=2)
        conn1 = session._acquire()
        conn2 = session._acquire()
        assert len(session._pool) == 2
        assert id(conn1) in session._in_use
        assert id(conn2) in session._in_use
        session.close()


class TestOpenAlgoProviderConstructor:
    def test_explicit_api_key(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="explicit-key",
            http_get=_http_get_factory({}),
        )
        assert provider._api_key == "explicit-key"

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENALGO_API_KEY", "from-env")
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key=None,
            http_get=_http_get_factory({}),
        )
        assert provider._api_key == "from-env"

    def test_custom_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CUSTOM_KEY", "custom-value")
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key=None,
            api_key_env_var="CUSTOM_KEY",
            http_get=_http_get_factory({}),
        )
        assert provider._api_key == "custom-value"

    def test_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENALGO_API_KEY", raising=False)
        with pytest.raises(ConfigError, match="API key is required"):
            OpenAlgoProvider(  # type: ignore[abstract]
                base_url="https://api.openalgo.local"
            )

    def test_explicit_key_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENALGO_API_KEY", "env-value")
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="explicit",
            http_get=_http_get_factory({}),
        )
        assert provider._api_key == "explicit"

    def test_invalid_url_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must use http or https"):
            OpenAlgoProvider(  # type: ignore[abstract]
                base_url="ftp://api.openalgo.local",
                api_key="secret",
            )

    def test_url_without_host_raises(self) -> None:
        with pytest.raises(ConfigError, match="must include host"):
            OpenAlgoProvider(  # type: ignore[abstract]
                base_url="https://", api_key="secret"
            )

    def test_base_url_trailing_slash_stripped(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local/",
            api_key="secret",
            http_get=_http_get_factory({}),
        )
        assert provider._base_url == "https://api.openalgo.local"

    def test_custom_pool_size(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({}),
            pool_size=8,
        )
        assert provider._pool_size == 8

    def test_http_get_default_when_none(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
        )
        assert provider._http_get is OpenAlgoProvider._default_http_get

    def test_http_get_custom_callable(self) -> None:
        custom_get = _http_get_factory({})
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=custom_get,
        )
        assert provider._http_get is custom_get


class TestGetSession:
    def test_creates_session_on_first_call(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({}),
        )
        assert provider._session is None
        session = provider._get_session()
        assert session is not None
        assert isinstance(session, _PooledHTTPSession)

    def test_reuses_existing_session(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({}),
        )
        session1 = provider._get_session()
        session2 = provider._get_session()
        assert session1 is session2


class TestBuildPath:
    def test_builds_path_with_params(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({}),
        )
        result = provider._build_path(
            "/api/v1/market/ohlcv",
            {"symbol": "RELIANCE", "exchange": "NSE"},
        )
        assert "/api/v1/market/ohlcv?" in result
        assert "symbol=RELIANCE" in result
        assert "exchange=NSE" in result

    def test_builds_path_empty_params(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({}),
        )
        result = provider._build_path("/api/v1/test", {})
        assert result.startswith("/api/v1/test?")


class TestGetOHLCV:
    @pytest.mark.asyncio()
    async def test_valid_single_bar(self) -> None:
        single_bar_payload: dict[str, object] = {
            "data": [
                {
                    "timestamp": "2026-01-01T09:15:00+00:00",
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 1000,
                }
            ]
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": single_bar_payload}),
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            limit=1,
        )
        assert len(bars) == 1
        assert bars[0].close == create_price("101")
        assert bars[0].symbol == "RELIANCE"
        assert bars[0].exchange == Exchange.NSE

    @pytest.mark.asyncio()
    async def test_multiple_bars(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": _VALID_OHLCV_PAYLOAD}),
        )
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            limit=2,
        )
        assert len(bars) == 2

    @pytest.mark.asyncio()
    async def test_with_since_parameter(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": _VALID_OHLCV_PAYLOAD}),
        )
        from iatb.core.types import create_timestamp

        since = create_timestamp(datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1m",
            since=since,
            limit=2,
        )
        assert len(bars) == 2

    @pytest.mark.asyncio()
    async def test_limit_zero_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": []}}),
        )
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=0,
            )

    @pytest.mark.asyncio()
    async def test_limit_negative_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": []}}),
        )
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=-5,
            )

    @pytest.mark.asyncio()
    async def test_missing_data_list_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": {"not": "a-list"}}}),
        )
        with pytest.raises(ConfigError, match="missing data list"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio()
    async def test_data_list_with_non_mapping_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": {"data": [42, "string"]}}),
        )
        with pytest.raises(ConfigError, match="must contain mapping objects"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio()
    async def test_non_mapping_payload_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: [1, 2, 3],
        )
        with pytest.raises(ConfigError, match="must be mapping-like JSON"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1m",
                limit=1,
            )

    @pytest.mark.asyncio()
    async def test_bse_exchange(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ohlcv": _VALID_OHLCV_PAYLOAD}),
        )
        bars = await provider.get_ohlcv(
            symbol="SBIN",
            exchange=Exchange.BSE,
            timeframe="5m",
            limit=2,
        )
        assert all(b.exchange == Exchange.BSE for b in bars)


class TestGetTicker:
    @pytest.mark.asyncio()
    async def test_valid_ticker(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": _VALID_TICKER_PAYLOAD}),
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert isinstance(ticker, TickerSnapshot)
        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")
        assert ticker.last == create_price("101")
        assert ticker.symbol == "RELIANCE"

    @pytest.mark.asyncio()
    async def test_ltp_fallback(self) -> None:
        payload: dict[str, object] = {
            "data": {"ltp": 105, "bid": 104.5, "ask": 105.5, "volume_24h": 500}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="TCS", exchange=Exchange.NSE)
        assert ticker.last == create_price("105")

    @pytest.mark.asyncio()
    async def test_close_fallback_for_last(self) -> None:
        payload: dict[str, object] = {
            "data": {"close": 200, "bid": 199.5, "ask": 200.5, "volume_24h": 300}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="INFY", exchange=Exchange.NSE)
        assert ticker.last == create_price("200")

    @pytest.mark.asyncio()
    async def test_bid_defaults_to_last(self) -> None:
        payload: dict[str, object] = {
            "data": {"last": 150, "ask": 151, "volume_24h": 100}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="HDFC", exchange=Exchange.NSE)
        assert ticker.bid == create_price("150")

    @pytest.mark.asyncio()
    async def test_ask_defaults_to_last(self) -> None:
        payload: dict[str, object] = {
            "data": {"last": 150, "bid": 149.5, "volume_24h": 100}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="ICICI", exchange=Exchange.NSE)
        assert ticker.ask == create_price("150")

    @pytest.mark.asyncio()
    async def test_volume_fallback_key(self) -> None:
        payload: dict[str, object] = {
            "data": {"last": 100, "bid": 99.5, "ask": 100.5, "volume": 2000}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="WIPRO", exchange=Exchange.NSE)
        assert ticker.volume_24h is not None

    @pytest.mark.asyncio()
    async def test_volume_defaults_to_zero(self) -> None:
        payload: dict[str, object] = {"data": {"last": 100, "bid": 99.5, "ask": 100.5}}
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="ITC", exchange=Exchange.NSE)
        assert ticker.volume_24h == create_quantity("0")

    @pytest.mark.asyncio()
    async def test_missing_data_mapping_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": {"data": []}}),
        )
        with pytest.raises(ConfigError, match="missing data mapping"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio()
    async def test_invalid_numeric_bid_raises(self) -> None:
        payload: dict[str, object] = {
            "data": {"bid": object(), "ask": 101.5, "last": 101, "volume_24h": 100}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        with pytest.raises(ConfigError, match="numeric-compatible"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio()
    async def test_bool_bid_raises(self) -> None:
        payload: dict[str, object] = {
            "data": {"bid": True, "ask": 101.5, "last": 101, "volume_24h": 100}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        with pytest.raises(ConfigError, match="must not be boolean"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio()
    async def test_non_mapping_http_response_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: [1, 2],
        )
        with pytest.raises(ConfigError, match="must be mapping-like JSON"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio()
    async def test_decimal_values_in_payload(self) -> None:
        payload: dict[str, object] = {
            "data": {
                "bid": Decimal("100.50"),
                "ask": Decimal("101.50"),
                "last": Decimal("101.00"),
                "volume_24h": Decimal("900"),
            }
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.bid == create_price("100.50")
        assert ticker.ask == create_price("101.50")

    @pytest.mark.asyncio()
    async def test_int_values_in_payload(self) -> None:
        payload: dict[str, object] = {
            "data": {"bid": 100, "ask": 102, "last": 101, "volume_24h": 500}
        }
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=_http_get_factory({"market/ticker": payload}),
        )
        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert ticker.bid == create_price("100")
        assert ticker.ask == create_price("102")


class TestRequest:
    @pytest.mark.asyncio()
    async def test_custom_http_get_receives_full_url(self) -> None:
        received_urls: list[str] = []

        def capture_get(url: str, headers: Mapping[str, str]) -> dict[str, object]:
            received_urls.append(url)
            return _VALID_TICKER_PAYLOAD

        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=capture_get,
        )
        await provider._request("/api/v1/market/ticker", {"symbol": "RELIANCE"})
        assert len(received_urls) == 1
        assert received_urls[0].startswith("https://api.openalgo.local")

    @pytest.mark.asyncio()
    async def test_default_http_get_uses_session(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
        )
        mock_session = MagicMock()
        mock_session.get.return_value = {
            "data": {"bid": 100, "ask": 101, "last": 100, "volume_24h": 0}
        }
        provider._session = mock_session
        result = await provider._request("/api/v1/test", {"k": "v"})
        mock_session.get.assert_called_once()
        assert isinstance(result, Mapping)

    @pytest.mark.asyncio()
    async def test_non_mapping_response_raises(self) -> None:
        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=lambda *_: "not-a-mapping",
        )
        with pytest.raises(ConfigError, match="must be mapping-like JSON"):
            await provider._request("/api/v1/test", {"k": "v"})

    @pytest.mark.asyncio()
    async def test_bearer_token_in_headers(self) -> None:
        received_headers: list[Mapping[str, str]] = []

        def capture_headers(url: str, headers: Mapping[str, str]) -> dict[str, object]:
            received_headers.append(headers)
            return _VALID_TICKER_PAYLOAD

        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="my-secret-key",
            http_get=capture_headers,
        )
        await provider._request("/api/v1/test", {"k": "v"})
        assert len(received_headers) == 1
        assert received_headers[0].get("Authorization") == "Bearer my-secret-key"


class TestDefaultHttpGet:
    def test_valid_json_response(self) -> None:
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": {"key": "value"}}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPSConnection", return_value=mock_conn
        ):
            result = OpenAlgoProvider._default_http_get(
                "https://api.example.com/api/v1/test?symbol=RELIANCE",
                {"Authorization": "Bearer key"},
            )
        assert isinstance(result, Mapping)
        assert result.get("data") == {"key": "value"}

    def test_http_scheme(self) -> None:
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": []}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPConnection", return_value=mock_conn
        ):
            result = OpenAlgoProvider._default_http_get(
                "http://localhost:8080/api/v1/test",
                {"Authorization": "Bearer key"},
            )
        assert isinstance(result, Mapping)

    def test_json_decode_error_raises_config_error(self) -> None:
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"invalid-json{{"
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPSConnection", return_value=mock_conn
        ):
            with pytest.raises(ConfigError, match="not valid JSON"):
                OpenAlgoProvider._default_http_get(
                    "https://api.example.com/api/v1/test",
                    {"Authorization": "Bearer key"},
                )

    def test_non_mapping_json_raises_config_error(self) -> None:
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"[1, 2, 3]"
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPSConnection", return_value=mock_conn
        ):
            with pytest.raises(ConfigError, match="must decode into JSON object"):
                OpenAlgoProvider._default_http_get(
                    "https://api.example.com/api/v1/test",
                    {"Authorization": "Bearer key"},
                )

    def test_connection_error_closes_and_raises(self) -> None:
        mock_conn = MagicMock()
        mock_conn.request.side_effect = ConnectionError("refused")
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPSConnection", return_value=mock_conn
        ):
            with pytest.raises(ConnectionError, match="refused"):
                OpenAlgoProvider._default_http_get(
                    "https://api.example.com/api/v1/test",
                    {"Authorization": "Bearer key"},
                )
        mock_conn.close.assert_called_once()

    def test_url_with_query_string(self) -> None:
        mock_conn = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": []}'
        mock_conn.getresponse.return_value = mock_response
        mock_conn.request = MagicMock()
        mock_conn.close = MagicMock()
        with patch(
            "iatb.data.openalgo_provider.HTTPSConnection", return_value=mock_conn
        ):
            OpenAlgoProvider._default_http_get(
                "https://api.example.com/api/v1/test?symbol=AAPL&exchange=NSE",
                {"Authorization": "Bearer key"},
            )
        call_args = mock_conn.request.call_args
        request_path = call_args[0][1]
        assert "symbol=AAPL" in request_path
        assert "exchange=NSE" in request_path


class TestAsyncIoToThread:
    @pytest.mark.asyncio()
    async def test_custom_http_get_runs_in_thread(self) -> None:
        call_count = 0

        def counting_get(url: str, headers: Mapping[str, str]) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return _VALID_TICKER_PAYLOAD

        provider = OpenAlgoProvider(  # type: ignore[abstract]
            base_url="https://api.openalgo.local",
            api_key="secret",
            http_get=counting_get,
        )
        await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert call_count == 1
