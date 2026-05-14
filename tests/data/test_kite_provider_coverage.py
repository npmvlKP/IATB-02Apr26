"""
Comprehensive coverage tests for kite_provider.py targeting >=90% coverage.

Covers: get_ohlcv, get_ohlcv_batch, get_ticker, from_env, rate limiter
integration, retry with backoff, circuit breaker interaction, unsupported
timeframe/exchange, batch partial failures, _parse_kite_timestamp edge
cases, _extract_numeric fallbacks, _coerce_numeric_input boundary,
_build_ohlcv_records filtering, _build_ticker_snapshot alt fields,
_process_ohlcv_batch_results error path, _default_kite_factory missing
KiteConnect attribute, _calculate_date_range, _process_ohlcv_data clipping.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_timestamp
from iatb.data.base import OHLCVBar, TickerSnapshot
from iatb.data.kite_provider import (
    KiteProvider,
    _coerce_numeric_input,
    _ensure_supported_exchange,
    _extract_numeric,
    _format_trading_symbol,
    _map_timeframe,
    _parse_kite_timestamp,
    _process_ohlcv_batch_results,
)
from iatb.data.rate_limiter import (
    CircuitBreaker,
    CircuitOpenError,
    RateLimiter,
    RetryConfig,
)


def _make_historical_data(
    count: int = 3,
    start: datetime | None = None,
) -> list[dict[str, object]]:
    start = start or datetime(2024, 3, 1, 9, 15, tzinfo=UTC)
    return [
        {
            "date": start + timedelta(days=i),
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 98.0 + i,
            "close": 103.0 + i,
            "volume": 1_000_000 + i * 50_000,
        }
        for i in range(count)
    ]


def _make_quote_data(
    trading_symbol: str = "NSE:RELIANCE",
    last_price: object = Decimal("2450.50"),
    bid: object = Decimal("2450.00"),
    ask: object = Decimal("2451.00"),
    volume: object = 1_500_000,
) -> dict[str, dict[str, object]]:
    return {
        trading_symbol: {
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "volume": volume,
        }
    }


def _make_provider(
    *,
    mock_client: MagicMock | None = None,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    retry_config: RetryConfig | None = None,
) -> KiteProvider:
    client = mock_client or MagicMock()
    if mock_client is None:
        client.historical_data.return_value = _make_historical_data()
        client.quote.return_value = _make_quote_data()
    return KiteProvider(
        api_key="test_key",
        access_token="test_token",
        kite_connect_factory=lambda k, t: client,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        retry_config=retry_config,
    )


class TestParseKiteTimestampCoverage:
    """Extended _parse_kite_timestamp coverage."""

    def test_naive_datetime_gets_utc_assigned(self) -> None:
        dt = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        dt_naive = dt.replace(tzinfo=None)
        result = _parse_kite_timestamp(dt_naive)
        assert result.tzinfo is UTC

    def test_aware_datetime_preserved(self) -> None:
        dt = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        result = _parse_kite_timestamp(dt)
        assert result == dt

    def test_iso_z_suffix(self) -> None:
        result = _parse_kite_timestamp("2024-06-01T10:00:00Z")
        assert result.tzinfo is not None
        assert result.year == 2024

    def test_iso_with_offset(self) -> None:
        result = _parse_kite_timestamp("2024-06-01T10:00:00+05:30")
        assert result.tzinfo is not None

    def test_naive_iso_raises(self) -> None:
        with pytest.raises(ConfigError, match="must include timezone"):
            _parse_kite_timestamp("2024-06-01T10:00:00")

    def test_integer_timestamp_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported timestamp"):
            _parse_kite_timestamp(12345)

    def test_none_timestamp_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported timestamp"):
            _parse_kite_timestamp(None)


class TestExtractNumericCoverage:
    """Extended _extract_numeric coverage."""

    def test_first_key_present(self) -> None:
        assert _extract_numeric({"open": 100}, ("open", "Open")) == 100

    def test_second_key_fallback(self) -> None:
        assert _extract_numeric({"Open": 200}, ("open", "Open")) == 200

    def test_none_value_skipped(self) -> None:
        assert _extract_numeric({"open": None}, ("open", "Open"), default=0) == 0

    def test_all_keys_missing_default(self) -> None:
        assert _extract_numeric({}, ("open", "Open"), default=42) == 42

    def test_default_is_zero(self) -> None:
        assert _extract_numeric({}, ("x",)) == 0


class TestCoerceNumericInputCoverage:
    """Extended _coerce_numeric_input coverage."""

    def test_bool_true_rejected(self) -> None:
        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(True, field_name="bid")

    def test_bool_false_rejected(self) -> None:
        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(False, field_name="bid")

    def test_decimal_passes_through(self) -> None:
        result = _coerce_numeric_input(Decimal("99.99"), field_name="price")
        assert result == Decimal("99.99")

    def test_int_passes_through(self) -> None:
        assert _coerce_numeric_input(42, field_name="vol") == 42

    def test_str_passes_through(self) -> None:
        assert _coerce_numeric_input("123.45", field_name="p") == "123.45"

    def test_float_converted_to_str(self) -> None:
        assert _coerce_numeric_input(3.14, field_name="p") == "3.14"

    def test_list_rejected(self) -> None:
        with pytest.raises(ConfigError, match="must be numeric-compatible"):
            _coerce_numeric_input([1], field_name="p")

    def test_dict_rejected(self) -> None:
        with pytest.raises(ConfigError, match="must be numeric-compatible"):
            _coerce_numeric_input({"a": 1}, field_name="p")


class TestMapTimeframeCoverage:
    """Extended timeframe mapping coverage."""

    def test_all_valid_timeframes(self) -> None:
        mapping = {
            "1m": "minute",
            "5m": "5minute",
            "15m": "15minute",
            "30m": "30minute",
            "1h": "hour",
            "1d": "day",
        }
        for tf, expected in mapping.items():
            assert _map_timeframe(tf) == expected

    def test_unsupported_timeframe_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported Kite timeframe"):
            _map_timeframe("3m")


class TestFormatTradingSymbolCoverage:
    """Extended trading symbol formatting coverage."""

    def test_all_supported_exchanges(self) -> None:
        assert _format_trading_symbol("SYM", Exchange.NSE) == "NSE:SYM"
        assert _format_trading_symbol("SYM", Exchange.BSE) == "BSE:SYM"
        assert _format_trading_symbol("SYM", Exchange.MCX) == "MCX:SYM"
        assert _format_trading_symbol("SYM", Exchange.CDS) == "CDS:SYM"

    def test_unsupported_exchange_raises(self) -> None:
        class FakeExchange:
            value = "FAKE"

        with pytest.raises(ConfigError, match="Cannot format trading symbol"):
            _format_trading_symbol("SYM", FakeExchange())  # type: ignore[arg-type]


class TestEnsureSupportedExchangeCoverage:
    """Extended exchange validation coverage."""

    def test_all_supported(self) -> None:
        for ex in (Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS):
            _ensure_supported_exchange(ex)

    def test_binance_unsupported(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            _ensure_supported_exchange(Exchange.BINANCE)

    def test_coindcx_unsupported(self) -> None:
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            _ensure_supported_exchange(Exchange.COINDCX)


class TestProcessOhlcvBatchResultsCoverage:
    """Cover _process_ohlcv_batch_results error paths."""

    def test_exception_in_results_raises(self) -> None:
        exc = RuntimeError("API down")
        with pytest.raises(ConfigError, match="Failed to fetch OHLCV for B"):
            _process_ohlcv_batch_results(
                ["A", "B"],
                [("A", []), exc],
            )

    def test_tuple_results(self) -> None:
        bars_a = [MagicMock(spec=OHLCVBar)]
        bars_b = [MagicMock(spec=OHLCVBar)]
        result = _process_ohlcv_batch_results(
            ["A", "B"],
            [("A", bars_a), ("B", bars_b)],
        )
        assert result["A"] is bars_a
        assert result["B"] is bars_b

    def test_non_exception_non_tuple_result_skipped(self) -> None:
        result = _process_ohlcv_batch_results(
            ["A", "B"],
            [("A", [MagicMock(spec=OHLCVBar)]), 42],
        )
        assert "A" in result
        assert "B" not in result

    def test_empty_results(self) -> None:
        result = _process_ohlcv_batch_results([], [])
        assert result == {}

    def test_all_non_tuple_results(self) -> None:
        result = _process_ohlcv_batch_results(
            ["A", "B"],
            [99, "invalid"],
        )
        assert result == {}


class TestKiteProviderInitCoverage:
    """Extended initialization coverage."""

    def test_empty_api_key_raises(self) -> None:
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteProvider(api_key="  ", access_token="tok")

    def test_empty_access_token_raises(self) -> None:
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteProvider(api_key="key", access_token="  ")

    def test_custom_factory_assigned(self) -> None:
        factory = MagicMock()
        provider = KiteProvider(api_key="k", access_token="t", kite_connect_factory=factory)
        assert provider._kite_connect_factory is factory

    def test_default_rate_limiter_created(self) -> None:
        provider = _make_provider()
        assert provider._rate_limiter is not None
        assert provider._rate_limiter._requests_per_second == 3.0

    def test_default_circuit_breaker_created(self) -> None:
        provider = _make_provider()
        assert provider._circuit_breaker is not None

    def test_default_retry_config_created(self) -> None:
        provider = _make_provider()
        assert provider._retry_config is not None

    def test_client_lazy_initialization(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data()
        factory = MagicMock(return_value=mock_client)
        provider = KiteProvider(api_key="k", access_token="t", kite_connect_factory=factory)
        factory.assert_not_called()
        _ = provider._get_client()
        factory.assert_called_once_with("k", "t")

    def test_client_cached_after_creation(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data()
        factory = MagicMock(return_value=mock_client)
        provider = KiteProvider(api_key="k", access_token="t", kite_connect_factory=factory)
        c1 = provider._get_client()
        c2 = provider._get_client()
        assert c1 is c2
        assert factory.call_count == 1


class TestDefaultKiteFactoryCoverage:
    """Cover _default_kite_factory error paths."""

    def test_kiteconnect_module_not_found(self) -> None:
        with patch(
            "iatb.data.kite_provider.importlib.import_module",
            side_effect=ModuleNotFoundError("kiteconnect"),
        ):
            with pytest.raises(ConfigError, match="kiteconnect dependency is required"):
                KiteProvider._default_kite_factory("k", "t")

    def test_kiteconnect_class_missing(self) -> None:
        mock_module = MagicMock(spec=[])
        with patch(
            "iatb.data.kite_provider.importlib.import_module",
            return_value=mock_module,
        ):
            with pytest.raises(ConfigError, match="kiteconnect.KiteConnect is not available"):
                KiteProvider._default_kite_factory("k", "t")

    def test_kiteconnect_class_present_returns_instance(self) -> None:
        mock_kite_instance = MagicMock()
        mock_module = MagicMock()
        mock_module.KiteConnect.return_value = mock_kite_instance
        with patch(
            "iatb.data.kite_provider.importlib.import_module",
            return_value=mock_module,
        ):
            result = KiteProvider._default_kite_factory("my_key", "my_token")
            mock_module.KiteConnect.assert_called_once_with(
                api_key="my_key", access_token="my_token"
            )
            assert result is mock_kite_instance


class TestGetOhlcvCoverage:
    """Extended get_ohlcv coverage."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data(3)
        provider = _make_provider(mock_client=mock_client)

        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=10
        )
        assert len(bars) == 3
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_unsupported_exchange_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ohlcv(symbol="BTC", exchange=Exchange.BINANCE, timeframe="1d")

    @pytest.mark.asyncio
    async def test_unsupported_timeframe_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="Unsupported Kite timeframe"):
            await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="3m")

    @pytest.mark.asyncio
    async def test_zero_limit_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=0
            )

    @pytest.mark.asyncio
    async def test_negative_limit_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=-5
            )

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = []
        provider = _make_provider(mock_client=mock_client)

        bars = await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d")
        assert bars == []

    @pytest.mark.asyncio
    async def test_limit_clips_records(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data(10)
        provider = _make_provider(mock_client=mock_client)

        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=3
        )
        assert len(bars) == 3

    @pytest.mark.asyncio
    async def test_since_filter(self) -> None:
        data = _make_historical_data(5)
        mock_client = MagicMock()
        mock_client.historical_data.return_value = data
        provider = _make_provider(mock_client=mock_client)

        since = create_timestamp(datetime(2024, 3, 3, tzinfo=UTC))
        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            since=since,
            limit=10,
        )
        for bar in bars:
            assert bar.timestamp >= since

    @pytest.mark.asyncio
    async def test_client_missing_historical_data(self) -> None:
        mock_client = MagicMock(spec=[])
        provider = _make_provider(mock_client=mock_client)

        with pytest.raises(ConfigError, match="must have historical_data"):
            await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d")

    @pytest.mark.asyncio
    async def test_historical_data_returns_non_list(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = "not_a_list"
        provider = _make_provider(mock_client=mock_client)

        with pytest.raises(ConfigError, match="must return list"):
            await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d")

    @pytest.mark.asyncio
    async def test_all_supported_timeframes(self) -> None:
        for tf in ("1m", "5m", "15m", "30m", "1h", "1d"):
            mock_client = MagicMock()
            mock_client.historical_data.return_value = _make_historical_data(1)
            provider = _make_provider(mock_client=mock_client)
            bars = await provider.get_ohlcv(
                symbol="RELIANCE", exchange=Exchange.NSE, timeframe=tf, limit=1
            )
            assert len(bars) == 1

    @pytest.mark.asyncio
    async def test_all_supported_exchanges(self) -> None:
        for ex in (Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS):
            mock_client = MagicMock()
            mock_client.historical_data.return_value = _make_historical_data(1)
            provider = _make_provider(mock_client=mock_client)
            bars = await provider.get_ohlcv(symbol="SYM", exchange=ex, timeframe="1d", limit=1)
            assert len(bars) == 1


class TestGetOhlcvBatchCoverage:
    """Extended get_ohlcv_batch coverage."""

    @pytest.mark.asyncio
    async def test_empty_symbols_returns_empty(self) -> None:
        provider = _make_provider()
        result = await provider.get_ohlcv_batch(symbols=[], exchange=Exchange.NSE, timeframe="1d")
        assert result == {}

    @pytest.mark.asyncio
    async def test_single_symbol(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data(2)
        provider = _make_provider(mock_client=mock_client)

        result = await provider.get_ohlcv_batch(
            symbols=["RELIANCE"], exchange=Exchange.NSE, timeframe="1d", limit=5
        )
        assert "RELIANCE" in result
        assert len(result["RELIANCE"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_symbols(self) -> None:
        mock_client = MagicMock()
        mock_client.historical_data.return_value = _make_historical_data(2)
        provider = _make_provider(mock_client=mock_client)

        result = await provider.get_ohlcv_batch(
            symbols=["RELIANCE", "TCS", "INFY"],
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=5,
        )
        assert len(result) == 3
        for sym in ("RELIANCE", "TCS", "INFY"):
            assert sym in result

    @pytest.mark.asyncio
    async def test_zero_limit_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv_batch(
                symbols=["RELIANCE"], exchange=Exchange.NSE, timeframe="1d", limit=0
            )

    @pytest.mark.asyncio
    async def test_unsupported_exchange_raises(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ohlcv_batch(
                symbols=["BTC"], exchange=Exchange.BINANCE, timeframe="1d"
            )

    @pytest.mark.asyncio
    async def test_batch_partial_failure_raises(self) -> None:
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("429 Too Many Requests")
            return _make_historical_data(1)

        mock_client = MagicMock()
        mock_client.historical_data.side_effect = side_effect
        provider = _make_provider(mock_client=mock_client)

        with pytest.raises(ConfigError, match="Failed to fetch OHLCV"):
            await provider.get_ohlcv_batch(
                symbols=["A", "B"], exchange=Exchange.NSE, timeframe="1d"
            )


class TestGetTickerCoverage:
    """Extended get_ticker coverage."""

    @pytest.mark.asyncio
    async def test_successful_ticker_fetch(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = _make_quote_data()
        provider = _make_provider(mock_client=mock_client)

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert isinstance(snapshot, TickerSnapshot)
        assert snapshot.symbol == "RELIANCE"
        assert snapshot.exchange == Exchange.NSE
        assert snapshot.source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_ticker_unsupported_exchange(self) -> None:
        provider = _make_provider()
        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ticker(symbol="BTC", exchange=Exchange.BINANCE)

    @pytest.mark.asyncio
    async def test_ticker_client_missing_quote(self) -> None:
        mock_client = MagicMock(spec=[])
        provider = _make_provider(mock_client=mock_client)

        with pytest.raises(ConfigError, match="must have quote"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_ticker_quote_returns_non_dict(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = [1, 2, 3]
        provider = _make_provider(mock_client=mock_client)

        with pytest.raises(ConfigError, match="must return dict"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_ticker_alt_field_names(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = {
            "NSE:RELIANCE": {
                "last": Decimal("2450.00"),
                "buy": Decimal("2449.50"),
                "sell": Decimal("2450.50"),
                "total_buy_qty": 500_000,
            }
        }
        provider = _make_provider(mock_client=mock_client)

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert snapshot.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_ticker_best_bid_offer_fields(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": Decimal("2450.00"),
                "best_bid": Decimal("2449.50"),
                "best_offer": Decimal("2450.50"),
                "volume": 500_000,
            }
        }
        provider = _make_provider(mock_client=mock_client)

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert snapshot.symbol == "RELIANCE"

    @pytest.mark.asyncio
    async def test_ticker_float_values_converted(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 2450.50,
                "bid": 2450.00,
                "ask": 2451.00,
                "volume": 1500000,
            }
        }
        provider = _make_provider(mock_client=mock_client)

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert isinstance(snapshot.last, Decimal)
        assert isinstance(snapshot.bid, Decimal)
        assert isinstance(snapshot.ask, Decimal)

    @pytest.mark.asyncio
    async def test_ticker_missing_quote_key_returns_defaults(self) -> None:
        mock_client = MagicMock()
        mock_client.quote.return_value = {"NSE:OTHER": {"last_price": 100}}
        provider = _make_provider(mock_client=mock_client)

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)
        assert snapshot.symbol == "RELIANCE"
        assert snapshot.bid == Decimal("0")
        assert snapshot.ask == Decimal("0")


class TestFromEnvCoverage:
    """Extended from_env coverage."""

    def test_success_with_defaults(self) -> None:
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "key123", "ZERODHA_ACCESS_TOKEN": "tok456"},
            clear=False,
        ):
            provider = KiteProvider.from_env()
            assert provider._api_key == "key123"
            assert provider._access_token == "tok456"

    def test_missing_api_key_raises(self) -> None:
        with patch.dict("os.environ", {"ZERODHA_ACCESS_TOKEN": "tok"}, clear=True):
            with pytest.raises(
                ConfigError, match="ZERODHA_API_KEY environment variable is required"
            ):
                KiteProvider.from_env()

    def test_missing_access_token_raises(self) -> None:
        with patch.dict("os.environ", {"ZERODHA_API_KEY": "key"}, clear=True):
            with pytest.raises(
                ConfigError,
                match="ZERODHA_ACCESS_TOKEN environment variable is required",
            ):
                KiteProvider.from_env()

    def test_whitespace_only_values_treated_as_missing(self) -> None:
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "   ", "ZERODHA_ACCESS_TOKEN": "tok"},
            clear=True,
        ):
            with pytest.raises(ConfigError, match="ZERODHA_API_KEY"):
                KiteProvider.from_env()

    def test_custom_env_var_names(self) -> None:
        with patch.dict(
            "os.environ",
            {"MY_KEY": "k", "MY_TOKEN": "t"},
            clear=True,
        ):
            provider = KiteProvider.from_env(
                api_key_env_var="MY_KEY",
                access_token_env_var="MY_TOKEN",
            )
            assert provider._api_key == "k"
            assert provider._access_token == "t"

    def test_custom_rate_limiter_passed_through(self) -> None:
        limiter = RateLimiter(requests_per_second=5.0, burst_capacity=20)
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "k", "ZERODHA_ACCESS_TOKEN": "t"},
            clear=True,
        ):
            provider = KiteProvider.from_env(rate_limiter=limiter)
            assert provider._rate_limiter is limiter

    def test_custom_circuit_breaker_passed_through(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=30.0)
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "k", "ZERODHA_ACCESS_TOKEN": "t"},
            clear=True,
        ):
            provider = KiteProvider.from_env(circuit_breaker=cb)
            assert provider._circuit_breaker is cb

    def test_custom_retry_config_passed_through(self) -> None:
        rc = RetryConfig(max_retries=5, initial_delay=0.05)
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "k", "ZERODHA_ACCESS_TOKEN": "t"},
            clear=True,
        ):
            provider = KiteProvider.from_env(retry_config=rc)
            assert provider._retry_config is rc


class TestRateLimiterIntegration:
    """Rate limiter integration with KiteProvider."""

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self) -> None:
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)
        provider = _make_provider(rate_limiter=limiter)

        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=5
        )
        assert isinstance(bars, list)

    @pytest.mark.asyncio
    async def test_burst_capacity_respected(self) -> None:
        limiter = RateLimiter(requests_per_second=3.0, burst_capacity=2)
        provider = _make_provider(rate_limiter=limiter)

        results = await asyncio.gather(
            provider.get_ohlcv(symbol="A", exchange=Exchange.NSE, timeframe="1d", limit=1),
            provider.get_ohlcv(symbol="B", exchange=Exchange.NSE, timeframe="1d", limit=1),
        )
        assert len(results) == 2


class TestRetryWithBackoffCoverage:
    """Retry with backoff integration coverage."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_transient_failure(self) -> None:
        call_count = 0

        async def flaky_func(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("429 Too Many Requests")
            return "ok"

        provider = _make_provider(retry_config=RetryConfig(max_retries=3, initial_delay=0.01))
        result = await provider._retry_with_backoff(flaky_func)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self) -> None:
        async def always_fail(**kwargs: Any) -> Any:
            raise Exception("503 Service Unavailable")

        provider = _make_provider(retry_config=RetryConfig(max_retries=2, initial_delay=0.01))
        with pytest.raises(ConfigError, match="failed after 2 retries"):
            await provider._retry_with_backoff(always_fail)

    @pytest.mark.asyncio
    async def test_non_retryable_401_raises(self) -> None:
        async def auth_fail(**kwargs: Any) -> Any:
            raise Exception("401 Unauthorized")

        provider = _make_provider(retry_config=RetryConfig(max_retries=3, initial_delay=0.01))
        with pytest.raises(ConfigError, match="Non-retryable error.*401"):
            await provider._retry_with_backoff(auth_fail)

    @pytest.mark.asyncio
    async def test_non_retryable_403_raises(self) -> None:
        async def forbidden_fail(**kwargs: Any) -> Any:
            raise Exception("403 Forbidden")

        provider = _make_provider(retry_config=RetryConfig(max_retries=3, initial_delay=0.01))
        with pytest.raises(ConfigError, match="Non-retryable error.*403"):
            await provider._retry_with_backoff(forbidden_fail)

    @pytest.mark.asyncio
    async def test_non_retryable_generic_raises(self) -> None:
        async def bad_request(**kwargs: Any) -> Any:
            raise Exception("400 Bad Request")

        provider = _make_provider(retry_config=RetryConfig(max_retries=3, initial_delay=0.01))
        with pytest.raises(ConfigError, match="Non-retryable error"):
            await provider._retry_with_backoff(bad_request)


class TestCircuitBreakerInteraction:
    """Circuit breaker integration with KiteProvider."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=60.0)

        async def failing(**kwargs: Any) -> Any:
            raise Exception("429 Too Many Requests")

        provider = _make_provider(
            circuit_breaker=cb,
            retry_config=RetryConfig(max_retries=0, initial_delay=0.01),
        )

        with pytest.raises(ConfigError):
            await provider._retry_with_backoff(failing)
        with pytest.raises(ConfigError):
            await provider._retry_with_backoff(failing)

        assert cb.state.value == "open"

    @pytest.mark.asyncio
    async def test_circuit_open_blocks_request(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=60.0)

        async def failing(**kwargs: Any) -> Any:
            raise Exception("429 Too Many Requests")

        provider = _make_provider(
            circuit_breaker=cb,
            retry_config=RetryConfig(max_retries=0, initial_delay=0.01),
        )

        with pytest.raises(ConfigError):
            await provider._retry_with_backoff(failing)

        with pytest.raises((CircuitOpenError, ConfigError)):
            await provider._retry_with_backoff(failing)


class TestBuildOhlcvRecordsCoverage:
    """Extended _build_ohlcv_records coverage."""

    def test_skips_non_dict_items(self) -> None:
        provider = _make_provider()
        data: list[Any] = [
            {
                "date": datetime(2024, 1, 1, tzinfo=UTC),
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000,
            },
            "not_a_dict",
            {
                "date": datetime(2024, 1, 2, tzinfo=UTC),
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 2000,
            },
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 2

    def test_skips_missing_date(self) -> None:
        provider = _make_provider()
        data: list[dict[str, object]] = [
            {
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000,
            },
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 0

    def test_skips_invalid_timestamp(self) -> None:
        provider = _make_provider()
        data: list[dict[str, object]] = [
            {
                "date": "not-a-valid-timestamp",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000,
            },
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 0

    def test_filters_by_since(self) -> None:
        provider = _make_provider()
        since = create_timestamp(datetime(2024, 1, 5, tzinfo=UTC))
        data = _make_historical_data(10)
        records = provider._build_ohlcv_records(data, since=since)
        for rec in records:
            assert rec["timestamp"] >= since

    def test_alt_ohlcv_keys(self) -> None:
        provider = _make_provider()
        data = [
            {
                "date": datetime(2024, 1, 1, tzinfo=UTC),
                "Open": 100,
                "High": 105,
                "Low": 95,
                "Close": 103,
                "Volume": 1000,
            }
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 1

    def test_naive_datetime_date_gets_utc(self) -> None:
        provider = _make_provider()
        naive_dt = datetime(2024, 1, 1, 9, 15, tzinfo=UTC).replace(tzinfo=None)
        data = [
            {
                "date": naive_dt,
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000,
            }
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 1

    def test_none_date_skipped(self) -> None:
        provider = _make_provider()
        data: list[dict[str, object]] = [
            {
                "date": None,
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000,
            },
        ]
        records = provider._build_ohlcv_records(data)
        assert len(records) == 0


class TestCalculateDateRangeCoverage:
    """Cover _calculate_date_range."""

    def test_with_since(self) -> None:
        provider = _make_provider()
        since = create_timestamp(datetime(2024, 1, 1, tzinfo=UTC))
        start, end = provider._calculate_date_range(since, 100)
        assert start.year == 2024
        assert start.month == 1
        assert start.day == 1
        assert end.tzinfo is not None

    def test_without_since(self) -> None:
        provider = _make_provider()
        start, end = provider._calculate_date_range(None, 30)
        expected_diff = timedelta(days=30)
        actual_diff = end - start
        assert abs(actual_diff - expected_diff) < timedelta(seconds=5)


class TestProcessOhlcvDataCoverage:
    """Cover _process_ohlcv_data clipping behavior."""

    def test_clips_when_records_exceed_limit(self) -> None:
        provider = _make_provider()
        data = _make_historical_data(10)
        result = provider._process_ohlcv_data(data, "RELIANCE", Exchange.NSE, "1d", None, 3)
        assert len(result) == 3

    def test_no_clip_when_within_limit(self) -> None:
        provider = _make_provider()
        data = _make_historical_data(3)
        result = provider._process_ohlcv_data(data, "RELIANCE", Exchange.NSE, "1d", None, 100)
        assert len(result) == 3


class TestBuildTickerSnapshotCoverage:
    """Extended _build_ticker_snapshot coverage."""

    def test_float_bid_ask_converted(self) -> None:
        provider = _make_provider()
        quote_data = {
            "NSE:RELIANCE": {
                "last_price": 2450.50,
                "bid": 2450.00,
                "ask": 2451.00,
                "volume": 1500000,
            }
        }
        snapshot = provider._build_ticker_snapshot(
            "RELIANCE", Exchange.NSE, quote_data, "NSE:RELIANCE"
        )
        assert isinstance(snapshot, TickerSnapshot)
        assert isinstance(snapshot.bid, Decimal)
        assert isinstance(snapshot.ask, Decimal)

    def test_alt_field_buy_sell(self) -> None:
        provider = _make_provider()
        quote_data = {
            "NSE:RELIANCE": {
                "last": Decimal("2450.00"),
                "buy": Decimal("2449.50"),
                "sell": Decimal("2450.50"),
                "total_buy_qty": 500_000,
            }
        }
        snapshot = provider._build_ticker_snapshot(
            "RELIANCE", Exchange.NSE, quote_data, "NSE:RELIANCE"
        )
        assert snapshot.symbol == "RELIANCE"

    def test_missing_trading_symbol_key_uses_empty(self) -> None:
        provider = _make_provider()
        quote_data: dict[str, dict[str, object]] = {}
        snapshot = provider._build_ticker_snapshot(
            "RELIANCE", Exchange.NSE, quote_data, "NSE:RELIANCE"
        )
        assert snapshot.bid == Decimal("0")
        assert snapshot.ask == Decimal("0")


class TestRetryWithBackoffIntegration:
    """Integration tests for _retry_with_backoff with rate limiter."""

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire_release_called(self) -> None:
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)
        provider = _make_provider(rate_limiter=limiter)

        async def simple_func(**kwargs: Any) -> Any:
            return "done"

        result = await provider._retry_with_backoff(simple_func)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_rate_limiter_released_on_error(self) -> None:
        limiter = RateLimiter(requests_per_second=10.0, burst_capacity=5)
        provider = _make_provider(
            rate_limiter=limiter,
            retry_config=RetryConfig(max_retries=0, initial_delay=0.01),
        )

        async def fail_once(**kwargs: Any) -> Any:
            raise Exception("429 Rate Limit")

        with pytest.raises(ConfigError):
            await provider._retry_with_backoff(fail_once)

        assert limiter.concurrent_requests == 0


class TestRetryConfigValidation:
    """RetryConfig validation edge cases."""

    def test_max_retries_zero_accepted(self) -> None:
        config = RetryConfig(max_retries=0, initial_delay=0.01)
        assert config.max_retries == 0

    def test_negative_max_retries_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryConfig(max_retries=-1)

    def test_negative_initial_delay_rejected(self) -> None:
        with pytest.raises(ValueError, match="initial_delay must be non-negative"):
            RetryConfig(initial_delay=-1.0)

    def test_zero_max_delay_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_delay must be positive"):
            RetryConfig(max_delay=0)

    def test_backoff_multiplier_le_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="backoff_multiplier must be greater"):
            RetryConfig(backoff_multiplier=1.0)

    def test_negative_jitter_rejected(self) -> None:
        with pytest.raises(ValueError, match="jitter_seconds must be non-negative"):
            RetryConfig(jitter_seconds=-0.5)

    def test_zero_circuit_failure_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="circuit_failure_threshold must be positive"):
            RetryConfig(circuit_failure_threshold=0)

    def test_zero_circuit_reset_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="circuit_reset_timeout must be positive"):
            RetryConfig(circuit_reset_timeout=0)


class TestCircuitBreakerValidation:
    """CircuitBreaker validation edge cases."""

    def test_zero_failure_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            CircuitBreaker(failure_threshold=0)

    def test_zero_reset_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="reset_timeout must be positive"):
            CircuitBreaker(reset_timeout=0)

    def test_initial_state_is_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        assert cb.state.value == "closed"

    def test_initial_failure_count_zero(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        assert cb.failure_count == 0


class TestRateLimiterValidation:
    """RateLimiter validation edge cases."""

    def test_zero_rps_rejected(self) -> None:
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            RateLimiter(requests_per_second=0)

    def test_negative_rps_rejected(self) -> None:
        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            RateLimiter(requests_per_second=-1)

    def test_zero_burst_rejected(self) -> None:
        with pytest.raises(ValueError, match="burst_capacity must be positive"):
            RateLimiter(requests_per_second=3, burst_capacity=0)

    def test_valid_construction(self) -> None:
        limiter = RateLimiter(requests_per_second=5.0, burst_capacity=10)
        assert limiter.burst_capacity == 10
