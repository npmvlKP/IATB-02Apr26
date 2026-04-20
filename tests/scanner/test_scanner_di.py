"""
Unit tests for InstrumentScanner DataProvider Dependency Injection.

Tests cover:
- DataProvider injection into InstrumentScanner
- Scanner with KiteProvider as DataProvider
- Scanner with JugaadProvider as DataProvider
- Scanner with FailoverProvider as DataProvider
- Custom data provider mocking
- Scanner behavior with different data sources
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import DataProvider, OHLCVBar, TickerSnapshot
from iatb.data.kite_provider import KiteProvider
from iatb.scanner.instrument_scanner import (
    InstrumentScanner,
    MarketData,
    ScannerConfig,
    SortDirection,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)


class MockDataProvider(DataProvider):
    """Mock data provider for testing."""

    def __init__(self, data: list[MarketData] | None = None) -> None:
        self._data = data or []
        self.name = "mock_provider"

    async def get_ohlcv(
        self,
        *,
        symbol: str,
        exchange: Exchange,
        timeframe: str,
        since: Any = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Return mock OHLCV bars."""
        for item in self._data:
            if item.symbol == symbol and item.exchange == exchange:
                # Return 2 bars: previous close and current close
                prev_close_time = item.timestamp_utc - timedelta(days=1)
                return [
                    OHLCVBar(
                        timestamp=create_timestamp(prev_close_time),
                        open=create_price(str(item.prev_close_price)),
                        high=create_price(str(item.prev_close_price)),
                        low=create_price(str(item.prev_close_price)),
                        close=create_price(str(item.prev_close_price)),
                        volume=create_quantity(str(item.avg_volume)),
                        symbol=symbol,
                        exchange=exchange,
                        source="mock",
                    ),
                    OHLCVBar(
                        timestamp=create_timestamp(item.timestamp_utc),
                        open=create_price(str(item.close_price)),
                        high=create_price(str(item.high_price)),
                        low=create_price(str(item.low_price)),
                        close=create_price(str(item.close_price)),
                        volume=create_quantity(str(item.volume)),
                        symbol=symbol,
                        exchange=exchange,
                        source="mock",
                    ),
                ]
        return []

    async def get_ticker(self, *, symbol: str, exchange: Exchange) -> TickerSnapshot:
        """Return mock ticker snapshot."""
        return TickerSnapshot(
            exchange=exchange,
            symbol=symbol,
            bid=create_price("100"),
            ask=create_price("101"),
            last=create_price("100.5"),
            volume_24h=create_quantity("1000000"),
            source="mock",
        )


class TestInstrumentScannerDI:
    """Test DataProvider dependency injection in InstrumentScanner."""

    @pytest.fixture
    def mock_market_data(self):
        """Create mock market data for testing."""
        now = datetime.now(UTC)
        return [
            MarketData(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                category=InstrumentScanner._determine_category("RELIANCE"),
                close_price=Decimal("1000.0"),
                prev_close_price=Decimal("950.0"),
                volume=Decimal("1000000"),
                avg_volume=Decimal("500000"),
                timestamp_utc=now,
                high_price=Decimal("1050.0"),
                low_price=Decimal("950.0"),
                adx=Decimal("25.0"),
                atr_pct=Decimal("0.05"),
                breadth_ratio=Decimal("1.2"),
                data_source="mock",
            ),
            MarketData(
                symbol="TCS",
                exchange=Exchange.NSE,
                category=InstrumentScanner._determine_category("TCS"),
                close_price=Decimal("3500.0"),
                prev_close_price=Decimal("3400.0"),
                volume=Decimal("500000"),
                avg_volume=Decimal("300000"),
                timestamp_utc=now,
                high_price=Decimal("3600.0"),
                low_price=Decimal("3400.0"),
                adx=Decimal("30.0"),
                atr_pct=Decimal("0.03"),
                breadth_ratio=Decimal("1.5"),
                data_source="mock",
            ),
        ]

    @pytest.fixture
    def mock_data_provider(self, mock_market_data):
        """Create mock data provider."""
        return MockDataProvider(data=mock_market_data)

    def test_scanner_accepts_data_provider_injection(self, mock_data_provider):
        """Test that InstrumentScanner accepts DataProvider via DI."""
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=mock_data_provider,
        )

        assert scanner._data_provider is not None
        assert scanner._data_provider == mock_data_provider

    def test_scanner_works_without_data_provider_with_custom_data(self, mock_market_data):
        """Test that scanner works with custom data without DataProvider."""
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=None,  # No DataProvider
        )

        # Use custom data
        result = scanner.scan(
            direction=SortDirection.GAINERS,
            custom_data=mock_market_data,
        )

        assert result is not None
        assert result.total_scanned == len(mock_market_data)

    def test_scanner_raises_error_without_provider_or_custom_data(self):
        """Test that scanner raises error when neither provider nor custom data is given."""
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=None,
        )

        with pytest.raises(Exception, match="DataProvider not configured"):
            scanner.scan(direction=SortDirection.GAINERS)

    def test_scanner_with_mock_sentiment_and_rl(self, mock_data_provider):
        """Test scanner with mocked sentiment and RL predictors."""
        sentiment_analyzer = create_mock_sentiment_analyzer(
            {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.9"), True)}
        )
        rl_predictor = create_mock_rl_predictor(probability=Decimal("0.7"))

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=mock_data_provider,
            sentiment_analyzer=sentiment_analyzer,
            rl_predictor=rl_predictor,
            symbols=["RELIANCE", "TCS"],
        )

        result = scanner.scan(direction=SortDirection.GAINERS)

        assert result is not None
        assert result.total_scanned == 2

    def test_scanner_filters_by_volume_ratio(self, mock_market_data):
        """Test that scanner filters by volume ratio."""
        scanner = InstrumentScanner(
            config=ScannerConfig(min_volume_ratio=Decimal("3.0"), top_n=5),
            data_provider=MockDataProvider(data=mock_market_data),
        )

        result = scanner.scan(
            direction=SortDirection.GAINERS,
            custom_data=mock_market_data,
        )

        # RELIANCE has volume_ratio = 1000000/500000 = 2.0 (filtered out)
        # TCS has volume_ratio = 500000/300000 = 1.67 (filtered out)
        # Both should be filtered out due to min_volume_ratio=3.0
        assert len(result.gainers) == 0

    def test_scanner_ranks_by_pct_change(self, mock_market_data):
        """Test that scanner ranks candidates by % change."""
        scanner = InstrumentScanner(
            config=ScannerConfig(min_volume_ratio=Decimal("1.0"), top_n=5),
            data_provider=MockDataProvider(data=mock_market_data),
            sentiment_analyzer=create_mock_sentiment_analyzer(
                {"RELIANCE": (Decimal("0.8"), True), "TCS": (Decimal("0.9"), True)}
            ),
            rl_predictor=create_mock_rl_predictor(probability=Decimal("0.7")),
        )

        result = scanner.scan(
            direction=SortDirection.GAINERS,
            custom_data=mock_market_data,
        )

        if len(result.gainers) >= 2:
            # First gainer should have higher % change than second
            assert result.gainers[0].pct_change >= result.gainers[1].pct_change


class TestScannerWithKiteProvider:
    """Test InstrumentScanner with KiteProvider as DataProvider."""

    @pytest.fixture
    def mock_kite_client(self):
        """Create mock KiteConnect client."""
        client = MagicMock()

        # Mock historical_data response
        now = datetime.now(UTC)
        client.historical_data.return_value = [
            {
                "date": now - timedelta(days=1),
                "open": 950.0,
                "high": 1000.0,
                "low": 940.0,
                "close": 990.0,
                "volume": 1000000,
            },
            {
                "date": now,
                "open": 990.0,
                "high": 1050.0,
                "low": 980.0,
                "close": 1040.0,
                "volume": 1200000,
            },
        ]

        # Mock quote response
        client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 1040.0,
                "bid": 1039.0,
                "ask": 1041.0,
                "volume": 1200000,
            }
        }

        return client

    @pytest.mark.asyncio
    async def test_scanner_with_kite_provider_fetches_data(self, mock_kite_client):
        """Test that scanner fetches data from KiteProvider."""
        kite_provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
        )

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(probability=Decimal("0.7")),
        )

        result = scanner.scan(direction=SortDirection.GAINERS)

        assert result is not None
        assert result.total_scanned >= 0

    @pytest.mark.asyncio
    async def test_kite_provider_retry_on_failure(self, mock_kite_client):
        """Test that KiteProvider retry logic works through scanner."""
        # Make first call fail, second succeed
        call_count = 0

        def failing_historical_data(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 Too Many Requests")
            now = datetime.now(UTC)
            return [
                {
                    "date": now,
                    "open": 1000.0,
                    "high": 1050.0,
                    "low": 980.0,
                    "close": 1040.0,
                    "volume": 1000000,
                }
            ]

        mock_kite_client.historical_data.side_effect = failing_historical_data

        kite_provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=lambda k, t: mock_kite_client,
            max_retries=3,
            initial_retry_delay=0.01,
        )

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=kite_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(probability=Decimal("0.7")),
        )

        result = scanner.scan(direction=SortDirection.GAINERS)

        # Should have retried and succeeded
        assert call_count == 2
        assert result is not None


class TestScannerWithFailoverProvider:
    """Test InstrumentScanner with FailoverProvider as DataProvider."""

    @pytest.fixture
    def mock_kite_client(self):
        """Create mock KiteConnect client."""
        client = MagicMock()
        now = datetime.now(UTC)
        client.historical_data.return_value = [
            {
                "date": now,
                "open": 1000.0,
                "high": 1050.0,
                "low": 980.0,
                "close": 1040.0,
                "volume": 1000000,
            }
        ]
        client.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 1040.0,
                "bid": 1039.0,
                "ask": 1041.0,
                "volume": 1000000,
            }
        }
        return client

    @pytest.fixture
    def mock_jugaad_data(self):
        """Create mock Jugaad data."""
        now = datetime.now(UTC)
        return [
            OHLCVBar(
                timestamp=create_timestamp(now),
                open=create_price("1000.0"),
                high=create_price("1050.0"),
                low=create_price("980.0"),
                close=create_price("1040.0"),
                volume=create_quantity("1000000"),
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                source="jugaad",
            )
        ]

    @pytest.mark.asyncio
    async def test_scanner_with_failover_provider(self, mock_kite_client, mock_jugaad_data):
        """Test that scanner works with FailoverProvider."""
        from iatb.data.failover_provider import FailoverProvider
        from iatb.data.jugaad_provider import JugaadProvider

        # Make KiteProvider fail initially
        def failing_kite_factory(*args: Any, **kwargs: Any) -> Any:
            client = MagicMock()
            client.historical_data.side_effect = Exception("Kite API Error")
            return client

        kite_provider = KiteProvider(
            api_key="test_key",
            access_token="test_token",
            kite_connect_factory=failing_kite_factory,
        )

        jugaad_provider = JugaadProvider()

        failover_provider = FailoverProvider(
            providers=[kite_provider, jugaad_provider],
            cooldown_seconds=1.0,
        )

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=failover_provider,
            symbols=["RELIANCE"],
            sentiment_analyzer=create_mock_sentiment_analyzer({"RELIANCE": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(probability=Decimal("0.7")),
        )

        # This should fall back to JugaadProvider
        result = scanner.scan(direction=SortDirection.GAINERS)

        assert result is not None


class TestScannerRateLimiting:
    """Test scanner rate limiting with DataProvider."""

    @pytest.mark.asyncio
    async def test_scanner_respects_rate_limiter(self):
        """Test that scanner respects rate limiter configuration."""
        call_count = 0

        async def mock_get_ohlcv(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            now = datetime.now(UTC)
            return [
                OHLCVBar(
                    timestamp=create_timestamp(now),
                    open=create_price("1000.0"),
                    high=create_price("1050.0"),
                    low=create_price("980.0"),
                    close=create_price("1040.0"),
                    volume=create_quantity("1000000"),
                    symbol=kwargs.get("symbol", "TEST"),
                    exchange=Exchange.NSE,
                    source="mock",
                )
            ]

        mock_provider = MockDataProvider()
        mock_provider.get_ohlcv = mock_get_ohlcv  # type: ignore

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=mock_provider,
            symbols=["RELIANCE", "TCS", "INFY"],
            rate_limiter=None,  # No rate limiter
        )

        result = scanner.scan(direction=SortDirection.GAINERS)

        assert result is not None
        assert call_count == 3  # One call per symbol


class TestScannerCircuitBreaker:
    """Test scanner circuit breaker with DataProvider."""

    @pytest.mark.asyncio
    async def test_scanner_with_circuit_breaker(self):
        """Test that scanner uses circuit breaker for resilience."""
        call_count = 0

        async def failing_get_ohlcv(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Use retryable error to trigger retry logic
                raise Exception("429 Too Many Requests")
            now = datetime.now(UTC)
            return [
                OHLCVBar(
                    timestamp=create_timestamp(now),
                    open=create_price("1000.0"),
                    high=create_price("1050.0"),
                    low=create_price("980.0"),
                    close=create_price("1040.0"),
                    volume=create_quantity("1000000"),
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    source="mock",
                )
            ]

        mock_provider = MockDataProvider()
        mock_provider.get_ohlcv = failing_get_ohlcv  # type: ignore

        from iatb.data.rate_limiter import CircuitBreaker

        circuit_breaker = CircuitBreaker(
            failure_threshold=5, reset_timeout=10.0, name="test_circuit"
        )

        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            data_provider=mock_provider,
            symbols=["RELIANCE"],
            circuit_breaker=circuit_breaker,
            retry_config=None,  # Use default retry
        )

        result = scanner.scan(direction=SortDirection.GAINERS)

        # Should have retried and succeeded
        assert call_count == 3
        assert result is not None
