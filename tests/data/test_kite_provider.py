"""
Tests for Kite Connect provider integration.
"""

# ruff: noqa: S106, S105, DTZ001, B023, E501 - Test file uses fake credentials, naive dt for testing, loop var binding, long lines
import random
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.kite_provider import KiteProvider

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _FakeKiteConnect:
    """Mock KiteConnect client for testing."""

    def __init__(
        self,
        historical_data: list[dict[str, object]] | None = None,
        quote_data: dict[str, object] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._historical_data = historical_data or []
        self._quote_data = quote_data or {}
        self._raise_error = raise_error
        self.historical_call_count = 0
        self.quote_call_count = 0

    def historical_data(
        self,
        instrument_token: str,  # noqa: ARG002
        from_date: object,  # noqa: ARG002
        to_date: object,  # noqa: ARG002
        interval: str,  # noqa: ARG002
    ) -> list[dict[str, object]]:
        """Mock historical_data method."""
        self.historical_call_count += 1
        if self._raise_error:
            raise self._raise_error
        return self._historical_data

    def quote(self, instruments: list[str]) -> dict[str, object]:  # noqa: ARG002
        """Mock quote method."""
        self.quote_call_count += 1
        if self._raise_error:
            raise self._raise_error
        return self._quote_data


class _FakeKiteConnectNoMethods:
    """Mock KiteConnect client without required methods."""

    pass


class TestKiteProvider:
    @pytest.mark.asyncio
    async def test_get_ohlcv_normalizes_historical_data(self) -> None:
        """Test that get_ohlcv normalizes Kite historical data response."""
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        historical_data = [
            {
                "date": now,
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
            {
                "date": now + timedelta(days=1),
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 1700,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=2,
        )

        assert len(bars) == 2
        assert bars[0].open == create_price("100")
        assert bars[1].close == create_price("102")
        assert bars[0].source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_get_ohlcv_since_filters_rows(self) -> None:
        """Test that since parameter filters OHLCV bars correctly."""
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        historical_data = [
            {"date": now, "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1500},
            {
                "date": now + timedelta(days=1),
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 1700,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            since=create_timestamp(now + timedelta(hours=12)),
            limit=10,
        )

        assert len(bars) == 1
        assert bars[0].timestamp.day == 2

    @pytest.mark.asyncio
    async def test_get_ticker_normalizes_quote_data(self) -> None:
        """Test that get_ticker normalizes Kite quote response."""
        quote_data = {
            "NSE:RELIANCE": {
                "bid": 100.5,
                "ask": 101.5,
                "last_price": 101,
                "volume": 2200,
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")
        assert ticker.last == create_price("101")
        assert ticker.source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_get_ohlcv_unsupported_exchange_raises(self) -> None:
        """Test that unsupported exchange raises ConfigError."""
        fake_client = _FakeKiteConnect()
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ohlcv(
                symbol="BTCUSDT",
                exchange=Exchange.BINANCE,
                timeframe="1d",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_unsupported_timeframe_raises(self) -> None:
        """Test that unsupported timeframe raises ConfigError."""
        fake_client = _FakeKiteConnect()
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="Unsupported Kite timeframe"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="10m",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_client_without_historical_data_raises(self) -> None:
        """Test that client without historical_data method raises ConfigError."""
        fake_client = _FakeKiteConnectNoMethods()
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="historical_data"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ticker_unsupported_exchange_raises(self) -> None:
        """Test that unsupported exchange raises ConfigError for ticker."""
        fake_client = _FakeKiteConnect()
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="Unsupported exchange"):
            await provider.get_ticker(symbol="BTCUSDT", exchange=Exchange.BINANCE)

    @pytest.mark.asyncio
    async def test_empty_api_key_raises(self) -> None:
        """Test that empty API key raises ConfigError."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteProvider(api_key="", access_token="test_token")

    @pytest.mark.asyncio
    async def test_empty_access_token_raises(self) -> None:
        """Test that empty access token raises ConfigError."""
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteProvider(api_key="test_key", access_token="")

    @pytest.mark.asyncio
    async def test_invalid_max_retries_raises(self) -> None:
        """Test that invalid max_retries raises ConfigError."""
        with pytest.raises(ConfigError, match="max_retries must be positive"):
            KiteProvider(
                api_key="test_key",
                access_token="test_token",
                max_retries=0,
            )

    @pytest.mark.asyncio
    async def test_invalid_retry_delay_raises(self) -> None:
        """Test that negative retry delay raises ConfigError."""
        with pytest.raises(ConfigError, match="initial_retry_delay must be non-negative"):
            KiteProvider(
                api_key="test_key",
                access_token="test_token",
                initial_retry_delay=-1.0,
            )

    @pytest.mark.asyncio
    async def test_invalid_requests_per_second_raises(self) -> None:
        """Test that invalid requests_per_second raises ConfigError."""
        with pytest.raises(ConfigError, match="requests_per_second must be positive"):
            KiteProvider(
                api_key="test_key",
                access_token="test_token",
                requests_per_second=0,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_limit_positive_required(self) -> None:
        """Test that limit must be positive."""
        fake_client = _FakeKiteConnect()
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=0,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_iso_timestamps(self) -> None:
        """Test that ISO timestamp strings are parsed correctly."""
        historical_data = [
            {
                "date": "2026-01-01T09:15:00+05:30",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert bars[0].timestamp.hour == 3  # 09:15 IST = 03:45 UTC

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_z_suffix_timestamps(self) -> None:
        """Test that 'Z' suffix timestamps are parsed correctly."""
        historical_data = [
            {
                "date": "2026-01-01T09:15:00Z",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert bars[0].timestamp.hour == 9  # UTC time

    @pytest.mark.asyncio
    async def test_get_ticker_uses_fallback_keys(self) -> None:
        """Test that ticker falls back to alternative keys."""
        quote_data = {
            "NSE:RELIANCE": {
                "buy": 100.5,  # Alternative to 'bid'
                "sell": 101.5,  # Alternative to 'ask'
                "last": 101,  # Alternative to 'last_price'
                "total_buy_qty": 2200,  # Alternative to 'volume'
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")
        assert ticker.last == create_price("101")

    @pytest.mark.asyncio
    async def test_rate_limiter_respects_limit(self) -> None:
        """Test that rate limiter enforces request rate limit."""
        historical_data = [
            {
                "date": datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
            requests_per_second=1,  # Very low rate for testing
        )

        # Make 3 requests, should take at least 2 seconds due to rate limiting
        start = datetime.now(UTC)
        for _ in range(3):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=1,
            )
        elapsed = (datetime.now(UTC) - start).total_seconds()

        # With 1 request/sec, 3 requests should take at least 2 seconds
        assert elapsed >= 2.0

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_error(self) -> None:
        """Test that provider retries on 429 rate limit errors."""
        # First call raises 429, second succeeds
        call_count = [0]

        def failing_historical_data(*args: object, **kwargs: object) -> list[dict[str, object]]:
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("429 Too Many Requests")
            return [
                {
                    "date": datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 1500,
                }
            ]

        fake_client = _FakeKiteConnect()
        fake_client.historical_data = failing_historical_data  # type: ignore[method-assign]

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
            max_retries=2,
            initial_retry_delay=0.1,  # Fast retry for testing
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert call_count[0] == 2  # First failed, second succeeded

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self) -> None:
        """Test that provider retries on 5xx server errors."""
        call_count = [0]

        def failing_historical_data(*args: object, **kwargs: object) -> list[dict[str, object]]:
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("500 Internal Server Error")
            return [
                {
                    "date": datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 1500,
                }
            ]

        fake_client = _FakeKiteConnect()
        fake_client.historical_data = failing_historical_data  # type: ignore[method-assign]

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
            max_retries=2,
            initial_retry_delay=0.1,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(self) -> None:
        """Test that non-retryable errors fail immediately."""
        fake_client = _FakeKiteConnect(raise_error=Exception("400 Bad Request"))
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
            max_retries=5,
        )

        with pytest.raises(ConfigError, match="Kite API error"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises_error(self) -> None:
        """Test that exhausting retries raises ConfigError."""
        fake_client = _FakeKiteConnect(raise_error=Exception("429 Too Many Requests"))
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
            max_retries=1,
            initial_retry_delay=0.05,
        )

        with pytest.raises(ConfigError, match="failed after.*retries"):
            await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=1,
            )

    @pytest.mark.asyncio
    async def test_get_ohlcv_multiple_exchanges(self) -> None:
        """Test that provider works with multiple supported exchanges."""
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        historical_data = [
            {
                "date": now,
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
        ]

        for exchange in [Exchange.NSE, Exchange.BSE, Exchange.MCX, Exchange.CDS]:
            fake_client = _FakeKiteConnect(historical_data=historical_data)
            provider = KiteProvider(
                api_key="test_key",
                access_token="test_token",
                kite_connect_factory=lambda _, __: fake_client,
            )

            bars = await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=exchange,
                timeframe="1d",
                limit=1,
            )

            assert len(bars) == 1
            assert bars[0].exchange == exchange

    @pytest.mark.asyncio
    async def test_get_ohlcv_multiple_timeframes(self) -> None:
        """Test that provider works with multiple timeframes."""
        now = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        historical_data = [
            {
                "date": now,
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
        ]

        for timeframe in ["1m", "5m", "15m", "30m", "1h", "1d"]:
            fake_client = _FakeKiteConnect(historical_data=historical_data)
            provider = KiteProvider(
                api_key="test_key",
                access_token="test_token",
                kite_connect_factory=lambda _, __: fake_client,
            )

            bars = await provider.get_ohlcv(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                timeframe=timeframe,
                limit=1,
            )

            assert len(bars) == 1

    def test_default_kite_factory_missing_dependency_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that missing kiteconnect dependency raises ConfigError."""
        monkeypatch.setattr(
            "iatb.data.kite_provider.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="kiteconnect dependency"):
            KiteProvider._default_kite_factory("test_key", "test_token")

    @pytest.mark.asyncio
    async def test_from_env_missing_api_key_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that missing API key environment variable raises ConfigError."""
        monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
        monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "test_token")

        with pytest.raises(ConfigError, match="ZERODHA_API_KEY.*required"):
            KiteProvider.from_env()

    @pytest.mark.asyncio
    async def test_from_env_missing_access_token_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that missing access token environment variable raises ConfigError."""
        monkeypatch.setenv("ZERODHA_API_KEY", "test_key")
        monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)

        with pytest.raises(ConfigError, match="ZERODHA_ACCESS_TOKEN.*required"):
            KiteProvider.from_env()

    @pytest.mark.asyncio
    async def test_from_env_creates_provider(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that from_env creates provider with environment variables."""
        monkeypatch.setenv("ZERODHA_API_KEY", "env_key")
        monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "env_token")

        provider = KiteProvider.from_env()

        assert provider._api_key == "env_key"
        assert provider._access_token == "env_token"

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_missing_data_fields(self) -> None:
        """Test that missing OHLCV volume field defaults to 0."""
        historical_data = [
            {
                "date": datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                # Missing volume - should default to 0
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )

        assert len(bars) == 1
        assert bars[0].volume == 0

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_invalid_timestamp(self) -> None:
        """Test that invalid timestamps are skipped."""
        historical_data = [
            {
                "date": "invalid-timestamp",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
            {
                "date": datetime(2026, 1, 2, 9, 15, tzinfo=UTC),
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 1700,
            },
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        # Only valid bar should be returned
        assert len(bars) == 1
        assert bars[0].open == create_price("101")

    @pytest.mark.asyncio
    async def test_get_ohlcv_handles_non_dict_items(self) -> None:
        """Test that non-dict items in data list are skipped."""
        historical_data = [
            "not a dict",
            {
                "date": datetime(2026, 1, 1, 9, 15, tzinfo=UTC),
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1500,
            },
            None,
        ]

        fake_client = _FakeKiteConnect(historical_data=historical_data)  # type: ignore[arg-type]
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=10,
        )

        assert len(bars) == 1

    @pytest.mark.asyncio
    async def test_get_ticker_handles_missing_quote_data(self) -> None:
        """Test that missing quote fields use default values."""
        quote_data = {
            "NSE:RELIANCE": {
                # Missing bid, ask, last, volume
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.bid == create_price("0")
        assert ticker.ask == create_price("0")
        assert ticker.last == create_price("0")
        assert ticker.volume_24h == create_quantity("0")

    @pytest.mark.asyncio
    async def test_get_ticker_handles_float_values(self) -> None:
        """Test that float values from API are converted to strings."""
        quote_data = {
            "NSE:RELIANCE": {
                "bid": 100.5,
                "ask": 101.5,
                "last_price": 101.0,
                "volume": 2200.0,
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        ticker = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert ticker.bid == create_price("100.5")
        assert ticker.ask == create_price("101.5")
        assert ticker.last == create_price("101.0")

    @pytest.mark.asyncio
    async def test_get_ticker_raises_on_invalid_numeric_type(self) -> None:
        """Test that invalid numeric types raise ConfigError."""
        quote_data = {
            "NSE:RELIANCE": {
                "bid": True,  # Boolean not allowed
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="bid must not be boolean"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    @pytest.mark.asyncio
    async def test_get_ticker_raises_on_unsupported_numeric_type(self) -> None:
        """Test that unsupported numeric types raise ConfigError."""
        quote_data = {
            "NSE:RELIANCE": {
                "bid": [],  # List not allowed
            }
        }

        fake_client = _FakeKiteConnect(quote_data=quote_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="bid must be numeric-compatible"):
            await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

    def test_parse_kite_timestamp_handles_naive_datetime(self) -> None:
        """Test that naive datetimes are converted to UTC."""
        from iatb.data.kite_provider import _parse_kite_timestamp

        naive_dt = datetime(2026, 1, 1, 9, 15)
        result = _parse_kite_timestamp(naive_dt)

        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_parse_kite_timestamp_handles_aware_datetime(self) -> None:
        """Test that aware datetimes are preserved and converted to UTC."""
        from iatb.data.kite_provider import _parse_kite_timestamp

        ist_dt = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
        result = _parse_kite_timestamp(ist_dt)

        assert result.tzinfo == UTC

    def test_parse_kite_timestamp_raises_on_naive_string(self) -> None:
        """Test that naive timestamp strings raise ConfigError."""
        from iatb.data.kite_provider import _parse_kite_timestamp

        with pytest.raises(ConfigError, match="must include timezone"):
            _parse_kite_timestamp("2026-01-01T09:15:00")

    def test_parse_kite_timestamp_raises_on_invalid_type(self) -> None:
        """Test that invalid timestamp types raise ConfigError."""
        from iatb.data.kite_provider import _parse_kite_timestamp

        with pytest.raises(ConfigError, match="Unsupported timestamp"):
            _parse_kite_timestamp(12345)

    def test_extract_numeric_uses_fallback_keys(self) -> None:
        """Test that _extract_numeric tries fallback keys."""
        from iatb.data.kite_provider import _extract_numeric

        payload = {"not_open": 100, "Open": 200}
        result = _extract_numeric(payload, ("open", "Open"))

        assert result == 200

    def test_extract_numeric_returns_default_when_missing(self) -> None:
        """Test that _extract_numeric returns default when no keys found."""
        from iatb.data.kite_provider import _extract_numeric

        payload = {"other": 100}
        result = _extract_numeric(payload, ("open", "Open"), default="N/A")

        assert result == "N/A"

    def test_extract_numeric_skips_none_values(self) -> None:
        """Test that _extract_numeric skips None values."""
        from iatb.data.kite_provider import _extract_numeric

        payload = {"open": None, "Open": 200}
        result = _extract_numeric(payload, ("open", "Open"))

        assert result == 200

    @pytest.mark.asyncio
    async def test_rate_limiter_refills_tokens(self) -> None:
        """Test that rate limiter refills tokens after window expires."""
        import asyncio

        from iatb.data.kite_provider import _RateLimiter

        limiter = _RateLimiter(requests_per_window=2, window_seconds=0.5)

        # Use all tokens
        await limiter.acquire()
        await limiter.acquire()

        # Wait for refill
        await asyncio.sleep(0.6)

        # Should have new tokens
        await limiter.acquire()

    @pytest.mark.asyncio
    async def test_fetch_historical_data_validates_return_type(self) -> None:
        """Test that _fetch_historical_data validates return type."""
        fake_client = _FakeKiteConnect()
        fake_client.historical_data = lambda *args, **kwargs: "not a list"  # type: ignore[method-assign]

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="must return list"):
            await provider._fetch_historical_data(
                fake_client,
                "NSE:RELIANCE",
                "day",
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 2, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_fetch_quote_validates_return_type(self) -> None:
        """Test that _fetch_quote validates return type."""
        fake_client = _FakeKiteConnect()
        fake_client.quote = lambda *args, **kwargs: "not a dict"  # type: ignore[method-assign]

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda _, __: fake_client,
        )

        with pytest.raises(ConfigError, match="must return dict"):
            await provider._fetch_quote(fake_client, "NSE:RELIANCE")

    @pytest.mark.asyncio
    async def test_from_env_with_custom_env_vars(self) -> None:
        """Test that from_env works with custom environment variable names."""
        import os

        os.environ["CUSTOM_API_KEY"] = "custom_key"
        os.environ["CUSTOM_TOKEN"] = "custom_token"

        try:
            provider = KiteProvider.from_env(
                api_key_env_var="CUSTOM_API_KEY",
                access_token_env_var="CUSTOM_TOKEN",
            )

            assert provider._api_key == "custom_key"
            assert provider._access_token == "custom_token"
        finally:
            del os.environ["CUSTOM_API_KEY"]
            del os.environ["CUSTOM_TOKEN"]

    @pytest.mark.asyncio
    async def test_whitespace_only_api_key_raises(self) -> None:
        """Test that whitespace-only API key raises ConfigError."""
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteProvider(api_key="   ", access_token="test_token")

    @pytest.mark.asyncio
    async def test_whitespace_only_access_token_raises(self) -> None:
        """Test that whitespace-only access token raises ConfigError."""
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteProvider(api_key="test_key", access_token="  \t  ")
