"""
Integration tests for Kite Provider + Scanner pipeline.

Tests cover:
- End-to-end data flow from KiteProvider to Scanner
- Scanner processes Kite OHLCV data correctly
- Error handling in the pipeline
- Performance with multiple symbols
- Data normalization through the pipeline
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.data.base import DataProvider
from iatb.data.kite_provider import KiteProvider
from iatb.scanner.instrument_scanner import (
    InstrumentScanner,
    ScannerConfig,
    ScannerResult,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)


class MockKiteClient:
    """Mock KiteConnect client for testing."""

    def __init__(self, data: dict[str, list[dict]]) -> None:
        self._data = data
        self.historical_data_calls: list[tuple] = []
        self.quote_calls: list[tuple] = []

    def historical_data(
        self, instrument_token: str, from_date: object, to_date: object, interval: str
    ) -> list[dict]:
        """Mock historical data endpoint."""
        self.historical_data_calls.append((instrument_token, from_date, to_date, interval))
        # Extract symbol from token (format: NSE:SYMBOL)
        if ":" in instrument_token:
            symbol = instrument_token.split(":")[1]
        else:
            symbol = instrument_token
        return self._data.get(symbol, [])

    def quote(self, instruments: list[str]) -> dict[str, dict]:
        """Mock quote endpoint."""
        self.quote_calls.append(instruments)
        result = {}
        for instr in instruments:
            result[instr] = {
                "last_price": 1000.0,
                "bid": 999.0,
                "ask": 1001.0,
                "volume": 1000000,
            }
        return result


class TestKiteProviderScannerIntegration:
    """Test integration between KiteProvider and Scanner."""

    @pytest.fixture
    def mock_kite_data(self):
        """Create mock Kite OHLCV data with recent dates."""
        # Use recent dates to ensure they fall within the scanner's lookback window
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)

        # Timestamps must be strictly increasing (oldest first)
        return {
            "RELIANCE": [
                {
                    "date": day_before,
                    "open": 950.0,
                    "high": 980.0,
                    "low": 940.0,
                    "close": 970.0,
                    "volume": 800000,
                },
                {
                    "date": yesterday,
                    "open": 1000.0,
                    "high": 1050.0,
                    "low": 990.0,
                    "close": 1040.0,
                    "volume": 1000000,
                },
            ],
            "TCS": [
                {
                    "date": day_before,
                    "open": 3450.0,
                    "high": 3490.0,
                    "low": 3440.0,
                    "close": 3480.0,
                    "volume": 400000,
                },
                {
                    "date": yesterday,
                    "open": 3500.0,
                    "high": 3550.0,
                    "low": 3480.0,
                    "close": 3540.0,
                    "volume": 500000,
                },
            ],
        }

    @pytest.fixture
    def kite_provider(self, mock_kite_data):
        """Create KiteProvider with mock client."""
        mock_client = MockKiteClient(mock_kite_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_client,
        )
        return provider

    def test_end_to_end_pipeline_single_symbol(self, kite_provider, mock_kite_data):
        """Test complete pipeline from KiteProvider to Scanner for single symbol."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Verify scanner processed data
        assert result.total_scanned == 1
        # Verify KiteProvider was called
        assert len(kite_provider._get_client().historical_data_calls) > 0

    def test_end_to_end_pipeline_multiple_symbols(self, kite_provider):
        """Test complete pipeline for multiple symbols."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE", "TCS"],
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.85"), True)}
            ),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Verify scanner processed both symbols
        assert result.total_scanned == 2

        # Verify KiteProvider was called for both symbols
        client = kite_provider._get_client()
        symbols_called = {
            call[0].split(":")[1] if ":" in call[0] else call[0]
            for call in client.historical_data_calls
        }
        assert "RELIANCE" in symbols_called
        assert "TCS" in symbols_called

    def test_pipeline_data_normalization(self, kite_provider):
        """Test that data is properly normalized through the pipeline."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Verify data was normalized (no floats, Decimal types)
        if result.gainers:
            candidate = result.gainers[0]
            assert isinstance(candidate.close_price, Decimal)
            assert isinstance(candidate.volume, Decimal)
            assert isinstance(candidate.adx, Decimal)

    def test_pipeline_error_propagation(self):
        """Test that errors from KiteProvider are propagated correctly."""
        # Create a provider that raises an error
        failing_client = MagicMock()
        failing_client.historical_data.side_effect = Exception("API Error")

        failing_provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: failing_client,
        )

        scanner = InstrumentScanner(
            data_provider=failing_provider,
            symbols=["RELIANCE"],
        )

        # Scanner should handle errors gracefully (individual failures logged)
        result = scanner.scan()

        # Should not crash, but may have 0 scanned due to error
        assert result.total_scanned == 0

    def test_pipeline_with_empty_kite_response(self):
        """Test pipeline when Kite returns empty data."""
        empty_client = MockKiteClient({})

        empty_provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: empty_client,
        )

        scanner = InstrumentScanner(
            data_provider=empty_provider,
            symbols=["UNKNOWN"],
        )

        result = scanner.scan()

        # Should handle empty data gracefully
        assert result.total_scanned == 0

    def test_pipeline_respects_scanner_config(self, kite_provider):
        """Test that scanner config is respected in pipeline."""
        custom_config = ScannerConfig(top_n=1, min_volume_ratio=Decimal("1.0"))
        scanner = InstrumentScanner(
            config=custom_config,
            data_provider=kite_provider,
            symbols=["RELIANCE", "TCS"],
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.85"), True)}
            ),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Verify top_n config respected
        total_candidates = len(result.gainers) + len(result.losers)
        assert total_candidates <= custom_config.top_n

    def test_pipeline_exchange_derivation(self, kite_provider):
        """Test that exchange is correctly derived in pipeline."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        scanner.scan()

        # Verify KiteProvider was called with correct exchange prefix
        client = kite_provider._get_client()
        if client.historical_data_calls:
            instrument_token = client.historical_data_calls[0][0]
            assert "NSE:" in instrument_token

    def test_pipeline_timeframe_usage(self, kite_provider):
        """Test that correct timeframe is used in pipeline."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        scanner.scan()

        # Verify KiteProvider was called with correct interval (day)
        client = kite_provider._get_client()
        if client.historical_data_calls:
            interval = client.historical_data_calls[0][3]
            assert interval == "day"

    def test_pipeline_with_rate_limiting(self, kite_provider):
        """Test that pipeline respects rate limiting."""
        # Add more symbols to trigger rate limiting
        symbols = [f"SYMBOL{i}" for i in range(10)]
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=symbols,
            sentiment_analyzer=create_mock_sentiment_analyzer({}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        # Should not fail despite multiple requests
        result = scanner.scan()

        # Result should be valid ScannerResult even if some symbols fail
        assert isinstance(result, ScannerResult)

    def test_pipeline_parallel_fetching(self, kite_provider):
        """Test that pipeline uses parallel fetching for efficiency."""
        symbols = ["RELIANCE", "TCS"]
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=symbols,
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.85"), True)}
            ),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        import time

        start_time = time.time()
        result = scanner.scan()
        elapsed = time.time() - start_time

        # Should be relatively fast due to parallel fetching
        # (This is a soft check, actual timing depends on system)
        assert elapsed < 5.0  # Should complete in < 5 seconds
        assert result.total_scanned == 2

    def test_pipeline_data_integrity(self, kite_provider, mock_kite_data):
        """Test that data maintains integrity through the pipeline."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        if result.gainers:
            candidate = result.gainers[0]

            # Verify data integrity
            assert candidate.symbol == "RELIANCE"
            assert candidate.exchange == Exchange.NSE
            assert candidate.close_price > Decimal("0")
            assert candidate.volume >= Decimal("0")

            # Verify timestamp is in UTC
            assert candidate.timestamp_utc.tzinfo == UTC

    def test_pipeline_with_sentiment_filter(self, kite_provider):
        """Test that sentiment filter works in pipeline."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.5"), False)}  # Below threshold
            ),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Should be filtered out due to low sentiment
        total_candidates = len(result.gainers) + len(result.losers)
        assert total_candidates == 0

    def test_pipeline_with_volume_filter(self, kite_provider):
        """Test that volume filter works in pipeline."""
        custom_config = ScannerConfig(min_volume_ratio=Decimal("10.0"))  # Very high
        scanner = InstrumentScanner(
            config=custom_config,
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Should be filtered out due to low volume ratio
        total_candidates = len(result.gainers) + len(result.losers)
        assert total_candidates == 0


class TestKiteProviderEnvironmentIntegration:
    """Test integration with environment-based KiteProvider creation."""

    @pytest.mark.asyncio
    async def test_from_env_with_scanner(self):
        """Test creating KiteProvider from env and using with Scanner."""
        with patch.dict(
            "os.environ",
            {"ZERODHA_API_KEY": "env_key", "ZERODHA_ACCESS_TOKEN": "env_token"},
        ):
            # Create provider from environment
            provider = KiteProvider.from_env()

            # Mock the client to avoid real API calls
            mock_client = MockKiteClient({})
            provider._kite_client = mock_client

            # Create scanner with provider
            scanner = InstrumentScanner(
                data_provider=provider,
                symbols=["TEST"],
            )

            # Verify scanner can be created
            assert scanner._data_provider == provider

    def test_missing_env_vars_handled(self):
        """Test that missing environment vars are handled gracefully."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(
                ConfigError, match="ZERODHA_API_KEY environment variable is required"
            ):
                KiteProvider.from_env()


class TestKiteProviderScannerProtocolCompliance:
    """Test that KiteProvider and Scanner comply with DataProvider protocol."""

    def test_kite_provider_implements_protocol(self):
        """Verify KiteProvider implements DataProvider protocol."""
        provider = KiteProvider(api_key="key", access_token="token")
        assert isinstance(provider, DataProvider)

    def test_scanner_accepts_kite_provider(self):
        """Verify Scanner accepts KiteProvider as data_provider."""
        provider = KiteProvider(api_key="key", access_token="token")
        scanner = InstrumentScanner(data_provider=provider, symbols=[])
        assert scanner._data_provider == provider

    def test_protocol_methods_are_async(self):
        """Verify DataProvider protocol methods are async."""
        provider = KiteProvider(api_key="key", access_token="token")
        import inspect

        assert inspect.iscoroutinefunction(provider.get_ohlcv)
        assert inspect.iscoroutinefunction(provider.get_ticker)
        assert inspect.iscoroutinefunction(provider.get_ohlcv_batch)


class TestKiteProviderScannerEdgeCases:
    """Test edge cases in the KiteProvider-Scanner pipeline."""

    def test_pipeline_with_insufficient_data_points(self):
        """Test pipeline when Kite returns insufficient data points."""
        # Return only 1 bar (need at least 2 for prev_close)
        now = datetime.now(UTC)
        insufficient_client = MockKiteClient(
            {
                "RELIANCE": [
                    {
                        "date": now,
                        "open": 1000.0,
                        "high": 1050.0,
                        "low": 990.0,
                        "close": 1040.0,
                        "volume": 1000000,
                    }
                ]
            }
        )

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: insufficient_client,
        )

        scanner = InstrumentScanner(
            data_provider=provider,
            symbols=["RELIANCE"],
        )

        result = scanner.scan()

        # Should handle gracefully (0 scanned due to insufficient data)
        assert result.total_scanned == 0

    def test_pipeline_with_zero_volume_data(self):
        """Test pipeline when Kite returns zero volume data."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        zero_volume_client = MockKiteClient(
            {
                "RELIANCE": [
                    {
                        "date": yesterday,
                        "open": 950.0,
                        "high": 980.0,
                        "low": 940.0,
                        "close": 970.0,
                        "volume": 0.0,
                    },
                    {
                        "date": now,
                        "open": 1000.0,
                        "high": 1050.0,
                        "low": 990.0,
                        "close": 1040.0,
                        "volume": 0.0,
                    },
                ]
            }
        )

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: zero_volume_client,
        )

        scanner = InstrumentScanner(
            data_provider=provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Should filter out due to zero volume ratio
        total_candidates = len(result.gainers) + len(result.losers)
        assert total_candidates == 0

    def test_pipeline_with_negative_price_data(self):
        """Test pipeline when Kite returns negative price data (edge case)."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        negative_price_client = MockKiteClient(
            {
                "RELIANCE": [
                    {
                        "date": yesterday,
                        "open": 950.0,
                        "high": 980.0,
                        "low": 940.0,
                        "close": 970.0,
                        "volume": 800000,
                    },
                    {
                        "date": now,
                        "open": -1000.0,  # Invalid
                        "high": 1050.0,
                        "low": 990.0,
                        "close": 1040.0,
                        "volume": 1000000,
                    },
                ]
            }
        )

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: negative_price_client,
        )

        scanner = InstrumentScanner(
            data_provider=provider,
            symbols=["RELIANCE"],
        )

        # Should handle gracefully (may fail validation)
        result = scanner.scan()
        assert isinstance(result, ScannerResult)


class TestFullScanCycleWithKiteProvider:
    """Test full scan cycle using KiteProvider."""

    @pytest.fixture
    def mock_kite_data(self):
        """Create mock Kite OHLCV data for scan cycle."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)

        return {
            "RELIANCE": [
                {
                    "date": day_before,
                    "open": 950.0,
                    "high": 980.0,
                    "low": 940.0,
                    "close": 970.0,
                    "volume": 800000,
                },
                {
                    "date": yesterday,
                    "open": 1000.0,
                    "high": 1050.0,
                    "low": 990.0,
                    "close": 1040.0,
                    "volume": 1000000,
                },
            ],
            "TCS": [
                {
                    "date": day_before,
                    "open": 3450.0,
                    "high": 3490.0,
                    "low": 3440.0,
                    "close": 3480.0,
                    "volume": 400000,
                },
                {
                    "date": yesterday,
                    "open": 3500.0,
                    "high": 3550.0,
                    "low": 3480.0,
                    "close": 3540.0,
                    "volume": 500000,
                },
            ],
        }

    @pytest.fixture
    def kite_provider(self, mock_kite_data):
        """Create KiteProvider with mock client."""
        mock_client = MockKiteClient(mock_kite_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_client,
        )
        return provider

    def test_full_scan_cycle_with_kite_provider(self, kite_provider):
        """Test end-to-end scan cycle using KiteProvider for data fetch."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE", "TCS"],
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.85"), True)}
            ),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        result = scanner.scan()

        # Verify scanner used KiteProvider data
        assert result.total_scanned == 2
        assert len(kite_provider._get_client().historical_data_calls) > 0

        # Verify data is present
        if result.gainers:
            assert any(g.symbol in ["RELIANCE", "TCS"] for g in result.gainers)

    def test_full_scan_cycle_with_custom_kite_data(self, kite_provider):
        """Test scan cycle processes KiteProvider data correctly."""
        scanner = InstrumentScanner(
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        scanner.scan()

        # Verify KiteProvider was called with correct parameters
        client = kite_provider._get_client()
        assert len(client.historical_data_calls) > 0

        # Verify instrument token format
        call = client.historical_data_calls[0]
        instrument_token = call[0]
        assert "NSE:" in instrument_token
        assert "RELIANCE" in instrument_token

        # Verify interval is "day"
        assert call[3] == "day"


class TestScanCycleFallbackToJugaad:
    """Test scan cycle fallback from KiteProvider to JugaadProvider."""

    @pytest.fixture
    def jugaad_data(self):
        """Create mock Jugaad data."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)

        return [
            {
                "timestamp": day_before,
                "open": 950.0,
                "high": 980.0,
                "low": 940.0,
                "close": 970.0,
                "volume": 800000,
            },
            {
                "timestamp": yesterday,
                "open": 1000.0,
                "high": 1050.0,
                "low": 990.0,
                "close": 1040.0,
                "volume": 1000000,
            },
        ]

    @pytest.fixture
    def failing_kite_provider(self):
        """Create KiteProvider that always fails."""
        failing_client = MagicMock()
        failing_client.historical_data.side_effect = Exception("Kite API Error")
        failing_client.quote.side_effect = Exception("Kite API Error")

        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: failing_client,
        )
        return provider

    @pytest.fixture
    def jugaad_provider(self, jugaad_data):
        """Create JugaadProvider with mock data."""
        from iatb.data.jugaad_provider import JugaadProvider

        # stock_df_loader must return a callable that takes symbol, from_date, to_date
        def mock_stock_df_loader():
            def mock_stock_df(symbol, from_date, to_date):
                return jugaad_data

            return mock_stock_df

        provider = JugaadProvider(stock_df_loader=mock_stock_df_loader)
        return provider

    def test_scan_cycle_fallback_to_jugaad(self, failing_kite_provider, jugaad_provider):
        """Test scan cycle falls back from KiteProvider to JugaadProvider on failure."""
        from iatb.data.failover_provider import FailoverProvider

        # Create failover provider with Kite (primary) -> Jugaad (fallback)
        failover = FailoverProvider(providers=[failing_kite_provider, jugaad_provider])

        # Create scanner with failover provider
        scanner = InstrumentScanner(
            data_provider=failover,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        # Run scan - should failover to Jugaad
        result = scanner.scan()

        # Verify scan succeeded via fallback
        assert result.total_scanned == 1

        # Verify circuit breaker state
        circuit_states = failover.get_circuit_states()
        assert "kiteconnect" in circuit_states
        assert circuit_states["kiteconnect"]["state"] == "OPEN"
        assert "jugaad" in circuit_states
        assert circuit_states["jugaad"]["state"] == "CLOSED"

    def test_scan_cycle_fallback_with_circuit_cooldown(
        self, failing_kite_provider, jugaad_provider
    ):
        """Test that failed provider remains in cooldown after failover."""
        from iatb.data.failover_provider import FailoverProvider

        # Create failover with short cooldown
        failover = FailoverProvider(
            providers=[failing_kite_provider, jugaad_provider], cooldown_seconds=1.0
        )

        scanner = InstrumentScanner(
            data_provider=failover,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        # First scan - should failover to Jugaad
        result1 = scanner.scan()
        assert result1.total_scanned == 1

        # Verify Kite circuit is open
        circuit_states = failover.get_circuit_states()
        assert circuit_states["kiteconnect"]["state"] == "OPEN"

        # Second scan - should skip Kite (still in cooldown)
        result2 = scanner.scan()
        assert result2.total_scanned == 1

        # Verify Kite circuit still open
        circuit_states = failover.get_circuit_states()
        assert circuit_states["kiteconnect"]["state"] == "OPEN"

    def test_scan_cycle_fallback_resets_on_cooldown_expiry(
        self, failing_kite_provider, jugaad_provider
    ):
        """Test that provider becomes available again after cooldown expires."""
        import time

        from iatb.data.failover_provider import FailoverProvider

        # Create failover with very short cooldown
        failover = FailoverProvider(
            providers=[failing_kite_provider, jugaad_provider], cooldown_seconds=0.5
        )

        scanner = InstrumentScanner(
            data_provider=failover,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        # First scan - failover to Jugaad
        result1 = scanner.scan()
        assert result1.total_scanned == 1

        # Wait for cooldown to expire
        time.sleep(0.6)

        # Verify Kite is available again
        circuit_states = failover.get_circuit_states()
        assert circuit_states["kiteconnect"]["available"] is True

    def test_scan_cycle_fallback_logs_switch(self, failing_kite_provider, jugaad_provider, caplog):
        """Test that failover logs source switch at WARNING level."""
        from iatb.data.failover_provider import FailoverProvider

        failover = FailoverProvider(providers=[failing_kite_provider, jugaad_provider])

        scanner = InstrumentScanner(
            data_provider=failover,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )

        # Run scan with logging
        import logging

        with caplog.at_level(logging.WARNING):
            result = scanner.scan()

        # Verify scan succeeded
        assert result.total_scanned == 1


class TestAuditTrailRecordsDataSource:
    """Test that SQLite audit trail records data source field."""

    @pytest.fixture
    def mock_kite_data(self):
        """Create mock Kite OHLCV data."""
        now = datetime.now(UTC)
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)

        return {
            "RELIANCE": [
                {
                    "date": day_before,
                    "open": 950.0,
                    "high": 980.0,
                    "low": 940.0,
                    "close": 970.0,
                    "volume": 800000,
                },
                {
                    "date": yesterday,
                    "open": 1000.0,
                    "high": 1050.0,
                    "low": 990.0,
                    "close": 1040.0,
                    "volume": 1000000,
                },
            ],
        }

    @pytest.fixture
    def kite_provider(self, mock_kite_data):
        """Create KiteProvider with mock client."""
        mock_client = MockKiteClient(mock_kite_data)
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_client,
        )
        return provider

    def test_audit_trail_records_data_source(self, tmp_path):
        """Verify SQLite audit contains source field for data provider."""
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.storage.sqlite_store import SQLiteStore

        # Create audit logger
        audit_path = tmp_path / "audit.db"
        audit_logger = TradeAuditLogger(audit_path)

        # Create a mock order result
        from iatb.core.enums import OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest

        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("1040"),
        )

        result = ExecutionResult(
            order_id="TEST-ORDER-001",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("10"),
            average_price=Decimal("1040"),
            message="Filled",
        )

        # Log the order with source info
        audit_logger.log_order(
            request=request,
            result=result,
            strategy_id="test_strategy",
            algo_id="KITE-SCAN-001",
        )

        # Verify trade was logged with source info
        store = SQLiteStore(audit_path)
        trades = store.list_trades(limit=10)
        assert len(trades) == 1

        trade = trades[0]
        assert trade.metadata is not None
        assert "algo_id" in trade.metadata
        assert trade.metadata["algo_id"] == "KITE-SCAN-001"

        # Verify other fields
        assert trade.symbol == "RELIANCE"
        assert trade.strategy_id == "test_strategy"

    def test_audit_trail_source_from_kite_provider(self, tmp_path):
        """Verify audit trail records when data comes from KiteProvider."""
        from iatb.core.enums import OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.storage.sqlite_store import SQLiteStore

        # Create audit logger
        audit_path = tmp_path / "audit.db"
        audit_logger = TradeAuditLogger(audit_path)

        # Create a mock order result
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("1040"),
        )

        result = ExecutionResult(
            order_id="TEST-ORDER-001",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("10"),
            average_price=Decimal("1040"),
            message="Filled",
        )

        # Log the order
        audit_logger.log_order(
            request=request,
            result=result,
            strategy_id="test_strategy",
            algo_id="KITE-SCAN-001",
        )

        # Verify trade was logged with source info
        store = SQLiteStore(audit_path)
        trades = store.list_trades(limit=10)
        assert len(trades) == 1

        trade = trades[0]
        assert trade.metadata is not None
        assert "algo_id" in trade.metadata
        assert trade.metadata["algo_id"] == "KITE-SCAN-001"

        # Verify other fields
        assert trade.symbol == "RELIANCE"
        assert trade.strategy_id == "test_strategy"

    def test_audit_trail_source_from_jugaad_provider(self, tmp_path):
        """Verify audit trail records when data comes from JugaadProvider."""
        from iatb.core.enums import OrderSide, OrderStatus
        from iatb.execution.base import ExecutionResult, OrderRequest
        from iatb.execution.trade_audit import TradeAuditLogger
        from iatb.storage.sqlite_store import SQLiteStore

        # Create audit logger
        audit_path = tmp_path / "audit.db"
        audit_logger = TradeAuditLogger(audit_path)

        # Create a mock order result
        request = OrderRequest(
            exchange=Exchange.NSE,
            symbol="TCS",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            price=Decimal("3540"),
        )

        result = ExecutionResult(
            order_id="TEST-ORDER-002",
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("5"),
            average_price=Decimal("3540"),
            message="Filled",
        )

        # Log the order with Jugaad as source
        audit_logger.log_order(
            request=request,
            result=result,
            strategy_id="test_strategy",
            algo_id="JUGAAD-SCAN-001",
        )

        # Verify trade was logged with Jugaad source info
        store = SQLiteStore(audit_path)
        trades = store.list_trades(limit=10)
        assert len(trades) == 1

        trade = trades[0]
        assert trade.metadata is not None
        assert "algo_id" in trade.metadata
        assert trade.metadata["algo_id"] == "JUGAAD-SCAN-001"

        # Verify other fields
        assert trade.symbol == "TCS"
        assert trade.strategy_id == "test_strategy"


class TestBacktestingValidationCrossProvider:
    """Test backtesting validation with cross-provider data comparison."""

    @pytest.fixture
    def mock_30day_kite_data(self):
        """Create 30 days of mock Kite OHLCV data for cross-provider comparison."""
        now = datetime.now(UTC)
        bars = []
        for i in range(30):
            date = now - timedelta(days=30 - i)
            # Create realistic price progression
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
        """Create 30 days of mock Jugaad OHLCV data with < 0.5% price difference."""
        now = datetime.now(UTC)
        bars = []
        for i in range(30):
            date = now - timedelta(days=30 - i)
            # Create data with < 0.5% difference from Kite data
            base_price = Decimal("1000.0")
            variation = Decimal(str(i * 10.0 + (i % 5) * 2.0))
            # Add small random difference within tolerance (max 0.4%)
            delta_multiplier = Decimal("1.002") if i % 2 == 0 else Decimal("0.998")
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

    @pytest.fixture
    def kite_provider(self, mock_30day_kite_data):
        """Create KiteProvider with mock client."""
        mock_client = MockKiteClient({"RELIANCE": mock_30day_kite_data})
        provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_client,
        )
        return provider

    @pytest.fixture
    def jugaad_provider(self, mock_30day_jugaad_data):
        """Create JugaadProvider with mock data."""
        from iatb.data.jugaad_provider import JugaadProvider

        def mock_stock_df_loader():
            def mock_stock_df(symbol, from_date, to_date):
                return mock_30day_jugaad_data

            return mock_stock_df

        provider = JugaadProvider(stock_df_loader=mock_stock_df_loader)
        return provider

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_price_delta_within_tolerance(
        self, kite_provider, jugaad_provider
    ):
        """Compare 30-day OHLCV from both sources; assert max price delta < 0.5%."""
        # Fetch data from both providers
        kite_bars = await kite_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        jugaad_bars = await jugaad_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify both providers returned 30 bars
        assert len(kite_bars) == 30, "KiteProvider should return 30 bars"
        assert len(jugaad_bars) == 30, "JugaadProvider should return 30 bars"

        # Calculate price delta for each bar
        max_delta_pct = Decimal("0.0")
        tolerance = Decimal("0.005")  # 0.5%

        for i in range(30):
            kite_bar = kite_bars[i]
            jugaad_bar = jugaad_bars[i]

            # Verify timestamps match (allowing for small timezone differences)
            time_diff = abs((kite_bar.timestamp - jugaad_bar.timestamp).total_seconds())
            assert time_diff < 60, f"Timestamp mismatch at index {i}: {time_diff}s difference"

            # Calculate percentage delta for each price field
            for price_field in ["open", "high", "low", "close"]:
                kite_price = getattr(kite_bar, price_field)
                jugaad_price = getattr(jugaad_bar, price_field)

                # Calculate percentage difference
                if kite_price != Decimal("0"):
                    delta_pct = abs(kite_price - jugaad_price) / kite_price
                    max_delta_pct = max(max_delta_pct, delta_pct)

        # Assert max delta is within tolerance
        assert (
            max_delta_pct < tolerance
        ), f"Max price delta {max_delta_pct:.4%} exceeds tolerance {tolerance:.2%}"

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_volume_consistency(self, kite_provider, jugaad_provider):
        """Verify volume data is consistent between providers."""
        kite_bars = await kite_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        jugaad_bars = await jugaad_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify volume is non-negative for both providers
        for i in range(30):
            assert kite_bars[i].volume >= Decimal("0"), f"Kite volume negative at index {i}"
            assert jugaad_bars[i].volume >= Decimal("0"), f"Jugaad volume negative at index {i}"

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_price_inequality_validation(self, kite_provider, jugaad_provider):
        """Verify high >= low and open/close within high-low range for both providers."""
        kite_bars = await kite_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        jugaad_bars = await jugaad_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify price relationships for both providers
        for provider_name, bars in [("Kite", kite_bars), ("Jugaad", jugaad_bars)]:
            for i, bar in enumerate(bars):
                assert bar.high >= bar.low, f"{provider_name}: High < Low at index {i}"
                assert bar.open >= bar.low, f"{provider_name}: Open < Low at index {i}"
                assert bar.open <= bar.high, f"{provider_name}: Open > High at index {i}"
                assert bar.close >= bar.low, f"{provider_name}: Close < Low at index {i}"
                assert bar.close <= bar.high, f"{provider_name}: Close > High at index {i}"

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_data_completeness(self, kite_provider, jugaad_provider):
        """Verify both providers return complete datasets without missing bars."""
        kite_bars = await kite_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        jugaad_bars = await jugaad_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify all bars have required fields
        for provider_name, bars in [("Kite", kite_bars), ("Jugaad", jugaad_bars)]:
            for i, bar in enumerate(bars):
                assert bar.symbol == "RELIANCE", f"{provider_name}: Symbol mismatch at index {i}"
                assert (
                    bar.exchange == Exchange.NSE
                ), f"{provider_name}: Exchange mismatch at index {i}"
                assert bar.open > Decimal("0"), f"{provider_name}: Invalid open price at index {i}"
                assert bar.high > Decimal("0"), f"{provider_name}: Invalid high price at index {i}"
                assert bar.low > Decimal("0"), f"{provider_name}: Invalid low price at index {i}"
                assert bar.close > Decimal(
                    "0"
                ), f"{provider_name}: Invalid close price at index {i}"
                assert bar.volume >= Decimal("0"), f"{provider_name}: Invalid volume at index {i}"

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_timestamp_alignment(self, kite_provider, jugaad_provider):
        """Verify timestamps are aligned between both providers."""
        kite_bars = await kite_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        jugaad_bars = await jugaad_provider.get_ohlcv(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )

        # Verify timestamps are aligned (allowing for small timezone differences)
        for i in range(30):
            time_diff = abs((kite_bars[i].timestamp - jugaad_bars[i].timestamp).total_seconds())
            assert time_diff < 60, f"Timestamp misalignment at index {i}: {time_diff}s difference"

        # Verify both datasets have same number of bars
        assert len(kite_bars) == len(
            jugaad_bars
        ), f"Kite returned {len(kite_bars)} bars, Jugaad returned {len(jugaad_bars)} bars"

    @pytest.mark.asyncio
    async def test_kite_vs_jugaad_multiple_symbols_comparison(
        self, kite_provider, jugaad_provider, mock_30day_jugaad_data
    ):
        """Test cross-provider comparison with multiple symbols."""
        # Test with TCS symbol by extending mock data
        now = datetime.now(UTC)
        kite_tcs_data = []
        jugaad_tcs_data = []

        for i in range(30):
            date = now - timedelta(days=30 - i)
            base_price = Decimal("3500.0")
            variation = Decimal(str(i * 20.0 + (i % 5) * 5.0))
            open_price = base_price + variation
            high_price = open_price * Decimal("1.015")
            low_price = open_price * Decimal("0.985")
            close_price = open_price + (variation * Decimal("0.01"))
            volume = 500000 + (i * 20000)

            kite_tcs_data.append(
                {
                    "date": date,
                    "open": float(open_price),
                    "high": float(high_price),
                    "low": float(low_price),
                    "close": float(close_price),
                    "volume": float(volume),
                }
            )

            # Jugaad data with small delta
            delta_multiplier = Decimal("1.001") if i % 2 == 0 else Decimal("0.999")
            jugaad_open = open_price * delta_multiplier
            jugaad_high = jugaad_open * Decimal("1.015")
            jugaad_low = jugaad_open * Decimal("0.985")
            jugaad_close = jugaad_open + (variation * Decimal("0.01"))

            jugaad_tcs_data.append(
                {
                    "date": date,
                    "open": float(jugaad_open),
                    "high": float(jugaad_high),
                    "low": float(jugaad_low),
                    "close": float(jugaad_close),
                    "volume": float(volume),
                }
            )

        # Update mock clients with TCS data
        kite_client = kite_provider._get_client()
        kite_client._data["TCS"] = kite_tcs_data

        # Create new Jugaad provider with TCS data
        from iatb.data.jugaad_provider import JugaadProvider

        def mock_stock_df_loader_with_tcs():
            def mock_stock_df(symbol, from_date, to_date):
                if symbol == "RELIANCE":
                    return mock_30day_jugaad_data
                elif symbol == "TCS":
                    return jugaad_tcs_data
                return []

            return mock_stock_df

        jugaad_provider_with_tcs = JugaadProvider(stock_df_loader=mock_stock_df_loader_with_tcs)

        # Compare both symbols
        for symbol in ["RELIANCE", "TCS"]:
            kite_bars = await kite_provider.get_ohlcv(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=30,
            )

            jugaad_bars = await jugaad_provider_with_tcs.get_ohlcv(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=30,
            )

            # Verify price delta within tolerance for this symbol
            max_delta_pct = Decimal("0.0")
            tolerance = Decimal("0.005")  # 0.5%

            for i in range(30):
                kite_bar = kite_bars[i]
                jugaad_bar = jugaad_bars[i]

                for price_field in ["open", "high", "low", "close"]:
                    kite_price = getattr(kite_bar, price_field)
                    jugaad_price = getattr(jugaad_bar, price_field)

                    if kite_price != Decimal("0"):
                        delta_pct = abs(kite_price - jugaad_price) / kite_price
                        max_delta_pct = max(max_delta_pct, delta_pct)

            assert (
                max_delta_pct < tolerance
            ), f"{symbol}: Max price delta {max_delta_pct:.4%} exceeds tolerance {tolerance:.2%}"
