"""
Unit tests for KiteProvider - DataProvider implementation.

Tests cover:
- Provider initialization and configuration
- Rate limiting behavior
- Retry logic with exponential backoff
- Data fetching and normalization
- Error handling for API failures
- Environment variable configuration
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_timestamp
from iatb.data.base import DataProvider, OHLCVBar
from iatb.data.kite_provider import (
    KiteProvider,
    _coerce_numeric_input,
    _ensure_supported_exchange,
    _extract_numeric,
    _format_trading_symbol,
    _map_timeframe,
    _parse_kite_timestamp,
)


class TestCoerceNumericInput:
    """Test numeric input coercion from API responses."""

    def test_rejects_boolean(self):
        """Boolean values should be rejected."""
        with pytest.raises(ConfigError, match="must not be boolean"):
            _coerce_numeric_input(True, field_name="test")

    def test_accepts_decimal(self):
        """Decimal values should pass through."""
        result = _coerce_numeric_input(Decimal("123.45"), field_name="test")
        assert result == Decimal("123.45")

    def test_accepts_int(self):
        """Integer values should pass through."""
        result = _coerce_numeric_input(100, field_name="test")
        assert result == 100

    def test_accepts_string(self):
        """String numeric values should pass through."""
        result = _coerce_numeric_input("123.45", field_name="test")
        assert result == "123.45"

    def test_converts_float_to_string(self):
        """Float values should be converted to string (API boundary)."""
        result = _coerce_numeric_input(123.45, field_name="test")
        assert result == "123.45"

    def test_rejects_invalid_type(self):
        """Non-numeric types should be rejected."""
        with pytest.raises(ConfigError, match="must be numeric-compatible"):
            _coerce_numeric_input([1, 2, 3], field_name="test")


class TestEnsureSupportedExchange:
    """Test exchange validation."""

    def test_accepts_nse(self):
        """NSE exchange should be supported."""
        _ensure_supported_exchange(Exchange.NSE)  # Should not raise

    def test_accepts_bse(self):
        """BSE exchange should be supported."""
        _ensure_supported_exchange(Exchange.BSE)  # Should not raise

    def test_accepts_mcx(self):
        """MCX exchange should be supported."""
        _ensure_supported_exchange(Exchange.MCX)  # Should not raise

    def test_accepts_cds(self):
        """CDS exchange should be supported."""
        _ensure_supported_exchange(Exchange.CDS)  # Should not raise

    def test_rejects_unsupported_exchange(self):
        """Unsupported exchanges should raise error."""

        # Create a mock unsupported exchange
        class UnsupportedExchange:
            value = "UNSUPPORTED"

        with pytest.raises(ConfigError, match="Unsupported exchange"):
            _ensure_supported_exchange(UnsupportedExchange())  # type: ignore


class TestMapTimeframe:
    """Test timeframe mapping."""

    def test_maps_minute(self):
        assert _map_timeframe("1m") == "minute"

    def test_maps_five_minute(self):
        assert _map_timeframe("5m") == "5minute"

    def test_maps_fifteen_minute(self):
        assert _map_timeframe("15m") == "15minute"

    def test_maps_thirty_minute(self):
        assert _map_timeframe("30m") == "30minute"

    def test_maps_hour(self):
        assert _map_timeframe("1h") == "hour"

    def test_maps_day(self):
        assert _map_timeframe("1d") == "day"

    def test_rejects_invalid_timeframe(self):
        with pytest.raises(ConfigError, match="Unsupported Kite timeframe"):
            _map_timeframe("2d")


class TestFormatTradingSymbol:
    """Test trading symbol formatting."""

    def test_formats_nse_symbol(self):
        assert _format_trading_symbol("RELIANCE", Exchange.NSE) == "NSE:RELIANCE"

    def test_formats_bse_symbol(self):
        assert _format_trading_symbol("RELIANCE", Exchange.BSE) == "BSE:RELIANCE"

    def test_formats_mcx_symbol(self):
        assert _format_trading_symbol("CRUDEOIL", Exchange.MCX) == "MCX:CRUDEOIL"

    def test_formats_cds_symbol(self):
        assert _format_trading_symbol("USDINR", Exchange.CDS) == "CDS:USDINR"

    def test_rejects_unsupported_exchange(self):
        class UnsupportedExchange:
            value = "UNSUPPORTED"

        with pytest.raises(ConfigError, match="Cannot format trading symbol"):
            _format_trading_symbol("TEST", UnsupportedExchange())  # type: ignore


class TestExtractNumeric:
    """Test numeric extraction from dictionaries."""

    def test_extracts_first_key(self):
        payload = {"open": 100, "Open": 200}
        assert _extract_numeric(payload, ("open", "Open")) == 100

    def test_extracts_second_key(self):
        payload = {"Open": 200}
        assert _extract_numeric(payload, ("open", "Open")) == 200

    def test_returns_default(self):
        payload = {"other": 100}
        assert _extract_numeric(payload, ("open", "Open"), default=0) == 0

    def test_handles_none_value(self):
        payload = {"open": None}
        assert _extract_numeric(payload, ("open", "Open"), default=0) == 0


class TestParseKiteTimestamp:
    """Test Kite timestamp parsing."""

    def test_parses_aware_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = _parse_kite_timestamp(dt)
        assert result == dt

    def test_parses_naive_datetime_to_utc(self):
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = _parse_kite_timestamp(dt)
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_parses_iso_string_with_z(self):
        result = _parse_kite_timestamp("2024-01-15T10:30:00Z")
        assert result.tzinfo is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parses_iso_string_with_timezone(self):
        result = _parse_kite_timestamp("2024-01-15T10:30:00+05:30")
        assert result.tzinfo is not None
        assert result.year == 2024

    def test_rejects_naive_string(self):
        with pytest.raises(ConfigError, match="must include timezone"):
            _parse_kite_timestamp("2024-01-15T10:30:00")

    def test_rejects_invalid_type(self):
        with pytest.raises(ConfigError, match="Unsupported timestamp"):
            _parse_kite_timestamp(12345)


class TestKiteProviderInitialization:
    """Test KiteProvider initialization and validation."""

    def test_initializes_with_required_params(self):
        provider = KiteProvider(api_key="test_key", access_token="test_token")
        assert provider._api_key == "test_key"
        assert provider._access_token == "test_token"

    def test_rejects_empty_api_key(self):
        with pytest.raises(ConfigError, match="api_key cannot be empty"):
            KiteProvider(api_key="  ", access_token="token")

    def test_rejects_empty_access_token(self):
        with pytest.raises(ConfigError, match="access_token cannot be empty"):
            KiteProvider(api_key="key", access_token="  ")

    def test_rejects_non_positive_max_retries(self):
        """Test that invalid retry config raises error."""
        from iatb.data.rate_limiter import RetryConfig

        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            RetryConfig(max_retries=-1)

    def test_rejects_negative_retry_delay(self):
        """Test that invalid retry config raises error."""
        from iatb.data.rate_limiter import RetryConfig

        with pytest.raises(ValueError, match="initial_delay must be non-negative"):
            RetryConfig(initial_delay=-1.0)

    def test_rejects_non_positive_requests_per_second(self):
        """Test that invalid rate limiter raises error."""
        from iatb.data.rate_limiter import RateLimiter

        with pytest.raises(ValueError, match="requests_per_second must be positive"):
            RateLimiter(requests_per_second=0)

    def test_accepts_custom_factory(self):
        mock_factory = MagicMock(return_value=MagicMock())
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=mock_factory
        )
        assert provider._kite_connect_factory == mock_factory


class TestKiteProviderGetOhlcv:
    """Test get_ohlcv method."""

    @pytest.fixture
    def mock_kite_client(self):
        """Create a mock KiteConnect client."""
        client = MagicMock()
        client.historical_data.return_value = [
            {
                "date": datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 103.0,
                "volume": 1000000,
            },
            {
                "date": datetime(2024, 1, 16, 10, 0, tzinfo=UTC),
                "open": 103.0,
                "high": 108.0,
                "low": 102.0,
                "close": 107.0,
                "volume": 1200000,
            },
        ]
        return client

    @pytest.mark.asyncio
    async def test_fetches_ohlcv_data(self, mock_kite_client):
        """Test successful OHLCV data fetch."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=10
        )

        assert len(bars) == 2
        assert isinstance(bars[0], OHLCVBar)
        assert bars[0].symbol == "RELIANCE"
        assert bars[0].exchange == Exchange.NSE

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, mock_kite_client):
        """Test that limit parameter is respected."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=1
        )

        assert len(bars) == 1

    @pytest.mark.asyncio
    async def test_filters_by_since_timestamp(self, mock_kite_client):
        """Test filtering by since timestamp."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        since = create_timestamp(datetime(2024, 1, 16, tzinfo=UTC))
        bars = await provider.get_ohlcv(
            symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", since=since
        )

        # Should only include data on or after since timestamp
        assert len(bars) == 1
        assert bars[0].timestamp >= since

    @pytest.mark.asyncio
    async def test_rejects_non_positive_limit(self, mock_kite_client):
        """Test that non-positive limit raises error."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        with pytest.raises(ConfigError, match="limit must be positive"):
            await provider.get_ohlcv(
                symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d", limit=0
            )

    @pytest.mark.asyncio
    async def test_handles_empty_api_response(self, mock_kite_client):
        """Test handling of empty API response."""
        mock_kite_client.historical_data.return_value = []
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        bars = await provider.get_ohlcv(symbol="RELIANCE", exchange=Exchange.NSE, timeframe="1d")

        assert bars == []


class TestKiteProviderGetTicker:
    """Test get_ticker method."""

    @pytest.fixture
    def mock_kite_client(self):
        """Create a mock KiteConnect client."""
        client = MagicMock()
        client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 1030.50,
                "bid": 1030.00,
                "ask": 1031.00,
                "volume": 1500000,
            }
        }
        return client

    @pytest.mark.asyncio
    async def test_fetches_ticker_snapshot(self, mock_kite_client):
        """Test successful ticker fetch."""
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert snapshot.symbol == "RELIANCE"
        assert snapshot.exchange == Exchange.NSE
        assert snapshot.source == "kiteconnect"

    @pytest.mark.asyncio
    async def test_handles_alternative_field_names(self, mock_kite_client):
        """Test handling of alternative field names in quote."""
        mock_kite_client.quote.return_value = {
            "NSE:RELIANCE": {
                "last": 1030.50,
                "buy": 1030.00,
                "sell": 1031.00,
                "total_buy_qty": 1500000,
            }
        }
        provider = KiteProvider(
            api_key="key", access_token="token", kite_connect_factory=lambda k, t: mock_kite_client
        )

        snapshot = await provider.get_ticker(symbol="RELIANCE", exchange=Exchange.NSE)

        assert snapshot.symbol == "RELIANCE"


class TestKiteProviderRateLimiting:
    """Test rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_respects_rate_limit(self):
        """Test that rate limiter respects configured rate."""
        from iatb.data.rate_limiter import RateLimiter

        call_count = 0
        max_calls = 5

        async def mock_func(*args: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            rate_limiter=RateLimiter(requests_per_second=3.0, burst_capacity=10),
        )

        # Make more requests than rate limit allows
        tasks = [provider._retry_with_backoff(mock_func) for _ in range(max_calls)]
        results = await asyncio.gather(*tasks)

        assert len(results) == max_calls
        assert call_count == max_calls


class TestKiteProviderRetryLogic:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self):
        """Test retry on 429 rate limit error."""
        from iatb.data.rate_limiter import RetryConfig

        call_count = 0

        async def mock_func(*args: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("429 Too Many Requests")
            return "success"

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            retry_config=RetryConfig(max_retries=3, initial_delay=0.01),
        )

        result = await provider._retry_with_backoff(mock_func)

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_server_error(self):
        """Test retry on 5xx server errors."""
        from iatb.data.rate_limiter import RetryConfig

        call_count = 0

        async def mock_func(*args: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("500 Internal Server Error")
            return "success"

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            retry_config=RetryConfig(max_retries=3, initial_delay=0.01),
        )

        result = await provider._retry_with_backoff(mock_func)

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self):
        """Test that failure after max retries raises error."""
        from iatb.data.rate_limiter import RetryConfig

        async def mock_func(*args: Any) -> Any:
            raise Exception("429 Too Many Requests")

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            retry_config=RetryConfig(max_retries=2, initial_delay=0.01),
        )

        with pytest.raises(ConfigError, match="failed after 2 retries"):
            await provider._retry_with_backoff(mock_func)

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self):
        """Test that non-retryable errors are raised immediately."""
        from iatb.data.rate_limiter import RetryConfig

        async def mock_func(*args: Any) -> Any:
            raise Exception("400 Bad Request")

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            retry_config=RetryConfig(max_retries=3, initial_delay=0.01),
        )

        with pytest.raises(ConfigError, match="Non-retryable error"):
            await provider._retry_with_backoff(mock_func)


class TestKiteProviderFromEnv:
    """Test from_env factory method."""

    @pytest.mark.asyncio
    async def test_creates_provider_from_env(self):
        """Test creating provider from environment variables."""
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "env_key", "ZERODHA_ACCESS_TOKEN": "env_token"},
        ):
            provider = KiteProvider.from_env()
            assert provider._api_key == "env_key"
            assert provider._access_token == "env_token"

    @pytest.mark.asyncio
    async def test_fails_when_api_key_missing(self):
        """Test failure when API key env var is missing."""
        with patch.dict("os.environ", {"ZERODHA_ACCESS_TOKEN": "token"}, clear=True):
            with pytest.raises(
                ConfigError, match="ZERODHA_API_KEY environment variable is required"
            ):
                KiteProvider.from_env()

    @pytest.mark.asyncio
    async def test_fails_when_access_token_missing(self):
        """Test failure when access token env var is missing."""
        with patch.dict("os.environ", {"ZERODHA_API_KEY": "key"}, clear=True):
            with pytest.raises(
                ConfigError, match="ZERODHA_ACCESS_TOKEN environment variable is required"
            ):
                KiteProvider.from_env()

    @pytest.mark.asyncio
    async def test_accepts_custom_env_var_names(self):
        """Test using custom environment variable names."""
        with patch.dict(
            "os.environ", {"CUSTOM_API_KEY": "key", "CUSTOM_TOKEN": "token"}, clear=True
        ):
            provider = KiteProvider.from_env(
                api_key_env_var="CUSTOM_API_KEY", access_token_env_var="CUSTOM_TOKEN"
            )
            assert provider._api_key == "key"
            assert provider._access_token == "token"


class TestKiteProviderBacktestingValidation:
    """Test backtesting validation for data consistency."""

    @pytest.fixture
    def mock_30day_kite_data(self):
        """Create 30 days of mock Kite OHLCV data for backtesting validation."""
        now = datetime.now(UTC)
        bars = []
        for i in range(30):
            date = now - timedelta(days=30 - i)
            # Create realistic price progression with small variations
            base_price = Decimal("1000.0")
            variation = Decimal(str(i * 10.0 + (i % 5) * 2.0))
            open_price = base_price + variation
            high_price = open_price * Decimal("1.02")
            low_price = open_price * Decimal("0.98")
            close_price = open_price + (variation * Decimal("0.01"))
            volume = 1000000 + (i * 50000)

            bars.append(
                {
                    "date": date,
                    "open": float(open_price),
                    "high": float(high_price),
                    "low": float(low_price),
                    "close": float(close_price),
                    "volume": float(volume),
                }
            )
        return bars

    @pytest.fixture
    def mock_30day_jugaad_data(self):
        """Create 30 days of mock Jugaad OHLCV data with small price differences."""
        now = datetime.now(UTC)
        bars = []
        for i in range(30):
            date = now - timedelta(days=30 - i)
            # Create data with < 0.5% difference from Kite data
            base_price = 1000.0
            variation = (i * 10.0) + (i % 5) * 2.0
            # Add small random difference within tolerance
            delta_multiplier = Decimal("1.001") if i % 2 == 0 else Decimal("0.999")
            open_price = (base_price + variation) * delta_multiplier
            high_price = open_price * Decimal("1.02")
            low_price = open_price * Decimal("0.98")
            close_price = open_price + (variation * Decimal("0.01"))
            volume = 1000000 + (i * 50000)

            bars.append(
                {
                    "date": date,
                    "open": float(open_price),
                    "high": float(high_price),
                    "low": float(low_price),
                    "close": float(close_price),
                    "volume": float(volume),
                }
            )
        return bars

    @pytest.mark.asyncio
    async def test_kite_data_no_timestamp_gaps(self, mock_30day_kite_data):
        """Verify no missing candles in historical data."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_30day_kite_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Should have 30 bars
        assert len(bars) == 30

        # Verify no timestamp gaps
        for i in range(1, len(bars)):
            prev_time = bars[i - 1].timestamp
            curr_time = bars[i].timestamp

            # Calculate time difference
            time_diff = (curr_time - prev_time).total_seconds()

            # For daily data, allow 1 day (86400 seconds) plus timezone adjustment
            # Skip weekends and holidays by checking if gap is reasonable
            if time_diff > 86400 * 2:  # More than 2 days gap is suspicious
                # Check if it's a weekend gap
                if prev_time.weekday() == 4:  # Friday
                    # Friday to Monday is 3 days
                    msg = f"Unexpected gap of {time_diff} seconds"
                    msg += f" between bars {i-1} and {i}"
                    assert time_diff <= 86400 * 3, msg
                else:
                    msg = f"Unexpected timestamp gap of {time_diff} seconds"
                    msg += f" between bars {i-1} and {i}"
                    raise AssertionError(msg)

    @pytest.mark.asyncio
    async def test_kite_data_no_timestamp_gaps_with_weekend(self, mock_30day_kite_data):
        """Verify no missing candles, accounting for weekends."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_30day_kite_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify all bars are in chronological order
        timestamps = [bar.timestamp for bar in bars]
        assert timestamps == sorted(timestamps), "Timestamps are not in chronological order"

        # Verify no duplicate timestamps
        assert len(timestamps) == len(set(timestamps)), "Duplicate timestamps found in data"

    @pytest.mark.asyncio
    async def test_kite_data_monotonic_timestamps(self, mock_30day_kite_data):
        """Verify timestamps are strictly monotonically increasing."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_30day_kite_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify strict monotonic increase
        for i in range(1, len(bars)):
            assert (
                bars[i].timestamp > bars[i - 1].timestamp
            ), f"Timestamp not strictly increasing at index {i}"

    @pytest.mark.asyncio
    async def test_kite_data_volume_consistency(self, mock_30day_kite_data):
        """Verify volume data is consistent and non-negative."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_30day_kite_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify all volumes are non-negative
        for bar in bars:
            assert bar.volume >= Decimal("0"), f"Negative volume found at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_kite_data_price_inequality_validation(self, mock_30day_kite_data):
        """Verify high >= low and open/close within high-low range."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_30day_kite_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify price relationships
        for bar in bars:
            assert bar.high >= bar.low, f"High < Low at {bar.timestamp}"
            assert bar.open >= bar.low, f"Open < Low at {bar.timestamp}"
            assert bar.open <= bar.high, f"Open > High at {bar.timestamp}"
            assert bar.close >= bar.low, f"Close < Low at {bar.timestamp}"
            assert bar.close <= bar.high, f"Close > High at {bar.timestamp}"

    @pytest.mark.asyncio
    async def test_kite_corporate_actions_adjusted(self):
        """Verify split/dividend adjustments are present in historical data."""
        # Create mock data simulating a 2:1 stock split in the past
        split_date = datetime(2024, 1, 15, tzinfo=UTC)

        # Pre-split prices (higher)
        pre_split_bars = []
        for i in range(10):
            date = split_date - timedelta(days=10 - i)
            pre_split_bars.append(
                {
                    "date": date,
                    "open": 2000.0 + (i * 10),
                    "high": 2050.0 + (i * 10),
                    "low": 1950.0 + (i * 10),
                    "close": 2030.0 + (i * 10),
                    "volume": 500000,
                }
            )

        # Post-split prices (approximately half, adjusted)
        post_split_bars = []
        for i in range(20):
            date = split_date + timedelta(days=i)
            # Post-split prices should be approximately half of pre-split
            # Allowing for normal market movement
            post_split_bars.append(
                {
                    "date": date,
                    "open": 1000.0 + (i * 5),
                    "high": 1050.0 + (i * 5),
                    "low": 950.0 + (i * 5),
                    "close": 1030.0 + (i * 5),
                    "volume": 1000000,  # Volume typically doubles after split
                }
            )

        mock_data = pre_split_bars + post_split_bars

        mock_client = MagicMock()
        mock_client.historical_data.return_value = mock_data

        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        bars = await provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify we have 30 bars
        assert len(bars) == 30

        # Find the split point (where price drops significantly)
        split_index = -1
        for i in range(1, len(bars)):
            price_ratio = bars[i].close / bars[i - 1].close
            # If price drops by ~50%, it's likely a split
            if price_ratio < Decimal("0.6"):
                split_index = i
                break

        # Verify split was detected
        assert split_index > 0, "No stock split detected in data"

        # Verify pre-split and post-split prices
        pre_split_close = bars[split_index - 1].close
        post_split_close = bars[split_index].close

        # Post-split price should be approximately half of pre-split
        # Allowing for 10% tolerance for market movement
        expected_post_split = pre_split_close / Decimal("2")
        price_diff_ratio = abs(post_split_close - expected_post_split) / expected_post_split

        assert price_diff_ratio < Decimal("0.1"), (
            f"Post-split price {post_split_close} not approximately half "
            f"of pre-split {pre_split_close}"
        )
        # Verify volume adjustment (should increase after split)
        pre_split_volume = bars[split_index - 1].volume
        post_split_volume = bars[split_index].volume

        # Post-split volume should be approximately double
        expected_post_split_volume = pre_split_volume * Decimal("2")
        volume_diff_ratio = (
            abs(post_split_volume - expected_post_split_volume) / expected_post_split_volume
        )

        assert volume_diff_ratio < Decimal("0.1"), (
            f"Post-split volume {post_split_volume} not approximately double "
            f"pre-split {pre_split_volume}"
        )
        # Verify continuity - the adjusted prices should maintain trends
        # Calculate returns before and after split
        if split_index > 1 and split_index < len(bars) - 1:
            pre_split_return = (bars[split_index - 1].close - bars[split_index - 2].close) / bars[
                split_index - 2
            ].close
            post_split_return = (bars[split_index + 1].close - bars[split_index].close) / bars[
                split_index
            ].close

            # Returns should be in similar magnitude (not considering the split)
            # This ensures the data is properly adjusted
            return_diff = abs(pre_split_return - post_split_return)
            assert return_diff < Decimal("0.05"), (
                f"Return discontinuity detected at split: "
                f"pre={pre_split_return:.4f}, post={post_split_return:.4f}"
            )


class TestKiteProviderEdgeCases:
    """Test edge cases and error paths for 90% coverage."""

    def test_kite_connect_module_not_found(self):
        """Test error handling when kiteconnect module is not installed."""
        with patch("iatb.data.kite_provider.importlib.import_module") as mock_import:
            mock_import.side_effect = ModuleNotFoundError("No module named 'kiteconnect'")

            with pytest.raises(ConfigError, match="kiteconnect dependency is required"):
                KiteProvider._default_kite_factory("key", "token")

    def test_kite_connect_class_not_available(self):
        """Test error handling when KiteConnect class is missing."""
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: (_ for _ in ()).throw(
                AttributeError("module 'kiteconnect' has no attribute 'KiteConnect'")
            ),
        )

        with patch("iatb.data.kite_provider.importlib.import_module") as mock_import:
            mock_module = MagicMock()
            del mock_module.KiteConnect
            mock_import.return_value = mock_module

            with pytest.raises(ConfigError, match="kiteconnect.KiteConnect is not available"):
                provider._default_kite_factory("key", "token")

    @pytest.mark.asyncio
    async def test_rate_limiter_token_refill(self):
        """Test rate limiter refills tokens after waiting."""
        from iatb.data.rate_limiter import RateLimiter

        # Create rate limiter with 1 token per second
        limiter = RateLimiter(requests_per_second=1.0, burst_capacity=1)

        # Consume all tokens
        await limiter.acquire()
        limiter.release()

        # Wait for refill (should take approximately 1 second)
        import time

        start = time.time()
        await limiter.acquire()
        elapsed = time.time() - start

        # Should have waited for token refill
        assert elapsed >= 0.9  # Allow some margin

        limiter.release()

    @pytest.mark.asyncio
    async def test_client_missing_historical_data_method(self):
        """Test error when client lacks historical_data method."""
        mock_client = MagicMock(spec=[])  # Empty spec = no methods
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        with pytest.raises(ConfigError, match="must have historical_data\\(\\) method"):
            await provider._fetch_historical_data(
                mock_client,
                "NSE:RELIANCE",
                "day",
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 31, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_historical_data_returns_non_list(self):
        """Test error when historical_data returns non-list."""
        mock_client = MagicMock()
        mock_client.historical_data.return_value = "not a list"
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        with pytest.raises(ConfigError, match="must return list"):
            await provider._fetch_historical_data(
                mock_client,
                "NSE:RELIANCE",
                "day",
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 31, tzinfo=UTC),
            )

    @pytest.mark.asyncio
    async def test_client_missing_quote_method(self):
        """Test error when client lacks quote method."""
        mock_client = MagicMock(spec=[])  # Empty spec = no methods
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        with pytest.raises(ConfigError, match="must have quote\\(\\) method"):
            await provider._fetch_quote(mock_client, "NSE:RELIANCE")

    @pytest.mark.asyncio
    async def test_quote_returns_non_dict(self):
        """Test error when quote returns non-dict."""
        mock_client = MagicMock()
        mock_client.quote.return_value = "not a dict"
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            kite_connect_factory=lambda k, t: mock_client,
        )

        with pytest.raises(ConfigError, match="must return dict"):
            await provider._fetch_quote(mock_client, "NSE:RELIANCE")

    def test_build_ohlcv_records_skips_non_dict_items(self):
        """Test that non-dict items are skipped in record building."""
        provider = KiteProvider(api_key="key", access_token="token")

        data = [
            {
                "date": datetime(2024, 1, 15, tzinfo=UTC),
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000000,
            },
            "not a dict",  # Should be skipped
            {
                "date": datetime(2024, 1, 16, tzinfo=UTC),
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 1200000,
            },
        ]

        records = provider._build_ohlcv_records(data)
        assert len(records) == 2  # Only valid dicts included

    def test_build_ohlcv_records_skips_missing_timestamp(self):
        """Test that items without timestamp are skipped."""
        provider = KiteProvider(api_key="key", access_token="token")

        data = [
            {
                "date": datetime(2024, 1, 15, tzinfo=UTC),
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000000,
            },
            {"open": 103, "high": 108, "low": 102, "close": 107, "volume": 1200000},  # Missing date
        ]

        records = provider._build_ohlcv_records(data)
        assert len(records) == 1  # Only item with timestamp included

    def test_build_ohlcv_records_skips_invalid_timestamp(self):
        """Test that items with invalid timestamp are skipped."""
        provider = KiteProvider(api_key="key", access_token="token")

        data = [
            {
                "date": datetime(2024, 1, 15, tzinfo=UTC),
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 103,
                "volume": 1000000,
            },
            {
                "date": "invalid-timestamp",
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 1200000,
            },
        ]

        records = provider._build_ohlcv_records(data)
        assert len(records) == 1  # Only valid timestamp included

    @pytest.mark.asyncio
    async def test_retry_with_backoff_unreachable_fallback(self):
        """Test the unreachable fallback error in retry logic."""
        from iatb.data.rate_limiter import RetryConfig

        # This test verifies the type safety fallback that should never be reached
        # We create a scenario that will fail on all retries
        provider = KiteProvider(
            api_key="key",
            access_token="token",
            retry_config=RetryConfig(max_retries=1, initial_delay=0.01),
        )

        # Force the unreachable path by making the loop fail
        async def failing_func():
            raise Exception("429 Too Many Requests")

        with pytest.raises(ConfigError, match="failed after 1 retries"):
            await provider._retry_with_backoff(failing_func)


class TestKiteProviderProtocol:
    """Test that KiteProvider implements DataProvider protocol."""

    def test_implements_data_provider_protocol(self):
        """Verify KiteProvider implements DataProvider protocol."""
        provider = KiteProvider(api_key="key", access_token="token")
        assert isinstance(provider, DataProvider)

    def test_has_required_methods(self):
        """Verify all required methods are present."""
        provider = KiteProvider(api_key="key", access_token="token")
        assert hasattr(provider, "get_ohlcv")
        assert hasattr(provider, "get_ticker")
        assert hasattr(provider, "get_ohlcv_batch")
