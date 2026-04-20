"""
Comprehensive tests for MigrationProvider (Risk 4 mitigation).

Tests cover:
- Incremental migration with dual-path support
- A/B testing comparison logic
- Feature flag behavior
- Fallback mechanisms
- Error handling
- Edge cases
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.core.types import create_price, create_quantity, create_timestamp
from iatb.data.base import OHLCVBar, TickerSnapshot
from iatb.data.migration_provider import ABTestResult, MigrationProvider


@pytest.fixture
def mock_config_path():
    """Create mock config path."""
    return Path("config/settings.toml")


@pytest.fixture
def mock_default_provider():
    """Create mock default provider."""
    provider = AsyncMock()
    provider.__class__.__name__ = "JugaadProvider"
    return provider


@pytest.fixture
def mock_fallback_provider():
    """Create mock fallback provider."""
    provider = AsyncMock()
    provider.__class__.__name__ = "KiteProvider"
    return provider


@pytest.fixture
def sample_ohlcv_bars():
    """Create sample OHLCV bars for testing."""
    timestamp = create_timestamp(datetime.now(UTC) - timedelta(days=30))
    bars = []
    for i in range(30):
        bar = OHLCVBar(
            timestamp=timestamp + timedelta(days=i),
            exchange=Exchange.NSE,
            symbol="TCS",
            open=create_price(str(1000 + i)),
            high=create_price(str(1010 + i)),
            low=create_price(str(990 + i)),
            close=create_price(str(1005 + i)),
            volume=create_quantity(str(1000000 + i * 10000)),
            source="test",
        )
        bars.append(bar)
    return bars


@pytest.fixture
def sample_ohlcv_bars_different():
    """Create sample OHLCV bars with different values for A/B testing."""
    timestamp = create_timestamp(datetime.now(UTC) - timedelta(days=30))
    bars = []
    for i in range(30):
        # 10% price difference to test threshold
        bar = OHLCVBar(
            timestamp=timestamp + timedelta(days=i),
            exchange=Exchange.NSE,
            symbol="TCS",
            open=create_price(str(1100 + i)),
            high=create_price(str(1110 + i)),
            low=create_price(str(1090 + i)),
            close=create_price(str(1105 + i)),
            volume=create_price(str(1100000 + i * 10000)),
            source="test",
        )
        bars.append(bar)
    return bars


@pytest.fixture
def sample_ticker_snapshot():
    """Create sample ticker snapshot."""
    return TickerSnapshot(
        timestamp=create_timestamp(datetime.now(UTC)),
        exchange=Exchange.NSE,
        symbol="TCS",
        bid=create_price("1000"),
        ask=create_price("1001"),
        last=create_price("1000.5"),
        volume_24h=create_quantity("1000000"),
        source="test",
    )


class TestMigrationProviderInit:
    """Test MigrationProvider initialization and configuration."""

    def test_init_with_providers(self, mock_default_provider, mock_fallback_provider):
        """Test initialization with providers."""
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=False,
            max_diff_pct=Decimal("5.0"),
        )
        assert provider._default_provider == mock_default_provider
        assert provider._fallback_provider == mock_fallback_provider
        assert provider._enable_ab_testing is False
        assert provider._max_diff_pct == Decimal("5.0")

    def test_from_config_success(
        self, mock_config_path, mock_default_provider, mock_fallback_provider
    ):
        """Test creation from configuration."""
        providers = {
            "jugaad": mock_default_provider,
            "kite": mock_fallback_provider,
        }
        # Mock config file content
        with patch("builtins.open", MagicMock()):
            with patch("tomli.load", return_value={"data": {"enable_ab_testing": True}}):
                provider = MigrationProvider.from_config(mock_config_path, providers)
        assert provider._default_provider == mock_default_provider
        assert provider._fallback_provider == mock_fallback_provider

    def test_from_config_missing_default(self, mock_config_path, mock_fallback_provider):
        """Test from_config fails when default provider is missing."""
        providers = {"kite": mock_fallback_provider}
        with patch("tomli.load", return_value={"data": {"data_provider_default": "nonexistent"}}):
            with pytest.raises(ConfigError, match="Default provider 'nonexistent' not found"):
                MigrationProvider.from_config(mock_config_path, providers)

    def test_from_config_missing_fallback(self, mock_config_path, mock_default_provider):
        """Test from_config fails when fallback provider is missing."""
        providers = {"jugaad": mock_default_provider}
        with patch("tomli.load", return_value={"data": {"data_provider_fallback": "nonexistent"}}):
            with pytest.raises(ConfigError, match="Fallback provider 'nonexistent' not found"):
                MigrationProvider.from_config(mock_config_path, providers)


class TestMigrationProviderGetOHLCV:
    """Test get_ohlcv method with various scenarios."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_single_path_success(self, mock_default_provider, sample_ohlcv_bars):
        """Test single-path execution with default provider success."""
        mock_default_provider.get_ohlcv.return_value = sample_ohlcv_bars
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=AsyncMock(),
            enable_ab_testing=False,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars
        mock_default_provider.get_ohlcv.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ohlcv_single_path_fallback(
        self, mock_default_provider, mock_fallback_provider, sample_ohlcv_bars
    ):
        """Test single-path execution with fallback on default failure."""
        mock_default_provider.get_ohlcv.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ohlcv.return_value = sample_ohlcv_bars
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=False,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars
        mock_fallback_provider.get_ohlcv.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ohlcv_both_fail(self, mock_default_provider, mock_fallback_provider):
        """Test ConfigError when both providers fail."""
        mock_default_provider.get_ohlcv.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ohlcv.side_effect = Exception("Fallback failed")
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=False,
        )
        with pytest.raises(ConfigError, match="Both providers failed"):
            await provider.get_ohlcv(
                symbol="TCS",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=30,
            )


class TestMigrationProviderABTesting:
    """Test A/B testing functionality."""

    @pytest.mark.asyncio
    async def test_ab_testing_success_no_anomaly(
        self,
        mock_default_provider,
        mock_fallback_provider,
        sample_ohlcv_bars,
    ):
        """Test A/B testing with matching results (no anomaly)."""
        mock_default_provider.get_ohlcv.return_value = sample_ohlcv_bars
        mock_fallback_provider.get_ohlcv.return_value = sample_ohlcv_bars
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
            max_diff_pct=Decimal("5.0"),
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars
        summary = provider.get_ab_test_summary()
        assert summary["total_tests"] == 1
        assert summary["anomalies"] == 0

    @pytest.mark.asyncio
    async def test_ab_testing_with_anomaly(
        self,
        mock_default_provider,
        mock_fallback_provider,
        sample_ohlcv_bars,
        sample_ohlcv_bars_different,
    ):
        """Test A/B testing with significant difference (anomaly)."""
        mock_default_provider.get_ohlcv.return_value = sample_ohlcv_bars
        mock_fallback_provider.get_ohlcv.return_value = sample_ohlcv_bars_different
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
            max_diff_pct=Decimal("5.0"),
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars  # Returns default
        summary = provider.get_ab_test_summary()
        assert summary["total_tests"] == 1
        assert summary["anomalies"] == 1
        assert summary["max_diff_pct"] > Decimal("5.0")

    @pytest.mark.asyncio
    async def test_ab_testing_bar_count_mismatch(
        self,
        mock_default_provider,
        mock_fallback_provider,
        sample_ohlcv_bars,
    ):
        """Test A/B testing with different bar counts."""
        mock_default_provider.get_ohlcv.return_value = sample_ohlcv_bars
        mock_fallback_provider.get_ohlcv.return_value = sample_ohlcv_bars[:20]
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars
        summary = provider.get_ab_test_summary()
        assert summary["anomalies"] == 1
        results = provider.get_ab_test_results()
        assert not results[0].bars_count_match

    @pytest.mark.asyncio
    async def test_ab_testing_default_fails_fallback_succeeds(
        self,
        mock_default_provider,
        mock_fallback_provider,
        sample_ohlcv_bars,
    ):
        """Test A/B testing when default fails but fallback succeeds."""
        mock_default_provider.get_ohlcv.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ohlcv.return_value = sample_ohlcv_bars
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == sample_ohlcv_bars  # Returns fallback

    @pytest.mark.asyncio
    async def test_ab_testing_both_fail(self, mock_default_provider, mock_fallback_provider):
        """Test A/B testing when both providers fail."""
        mock_default_provider.get_ohlcv.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ohlcv.side_effect = Exception("Fallback failed")
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
        )
        with pytest.raises(ConfigError, match="Both providers failed"):
            await provider.get_ohlcv(
                symbol="TCS",
                exchange=Exchange.NSE,
                timeframe="1d",
                limit=30,
            )


class TestMigrationProviderGetTicker:
    """Test get_ticker method."""

    @pytest.mark.asyncio
    async def test_get_ticker_success(self, mock_default_provider, sample_ticker_snapshot):
        """Test get_ticker with default provider success."""
        mock_default_provider.get_ticker.return_value = sample_ticker_snapshot
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=AsyncMock(),
            enable_ab_testing=False,
        )
        result = await provider.get_ticker(symbol="TCS", exchange=Exchange.NSE)
        assert result == sample_ticker_snapshot
        mock_default_provider.get_ticker.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ticker_fallback(
        self, mock_default_provider, mock_fallback_provider, sample_ticker_snapshot
    ):
        """Test get_ticker with fallback on default failure."""
        mock_default_provider.get_ticker.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ticker.return_value = sample_ticker_snapshot
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=False,
        )
        result = await provider.get_ticker(symbol="TCS", exchange=Exchange.NSE)
        assert result == sample_ticker_snapshot
        mock_fallback_provider.get_ticker.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ticker_both_fail(self, mock_default_provider, mock_fallback_provider):
        """Test ConfigError when both providers fail for ticker."""
        mock_default_provider.get_ticker.side_effect = Exception("Default failed")
        mock_fallback_provider.get_ticker.side_effect = Exception("Fallback failed")
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=False,
        )
        with pytest.raises(ConfigError, match="Both providers failed ticker"):
            await provider.get_ticker(symbol="TCS", exchange=Exchange.NSE)


class TestMigrationProviderGetOHLCVBatch:
    """Test get_ohlcv_batch method."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_batch_supported(self, mock_default_provider, sample_ohlcv_bars):
        """Test batch fetch when provider supports it."""
        mock_default_provider.get_ohlcv_batch = AsyncMock(
            return_value={"TCS": sample_ohlcv_bars, "INFY": sample_ohlcv_bars}
        )
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=AsyncMock(),
            enable_ab_testing=False,
        )
        result = await provider.get_ohlcv_batch(
            symbols=["TCS", "INFY"],
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert "TCS" in result
        assert "INFY" in result
        mock_default_provider.get_ohlcv_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_ohlcv_batch_not_supported(self, mock_default_provider, sample_ohlcv_bars):
        """Test batch fetch when provider doesn't support it (parallel fallback)."""
        # Simulate provider without batch method
        delattr(mock_default_provider, "get_ohlcv_batch")
        mock_default_provider.get_ohlcv = AsyncMock(return_value=sample_ohlcv_bars)
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=AsyncMock(),
            enable_ab_testing=False,
        )
        result = await provider.get_ohlcv_batch(
            symbols=["TCS", "INFY"],
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert "TCS" in result
        assert "INFY" in result
        assert mock_default_provider.get_ohlcv.call_count == 2

    @pytest.mark.asyncio
    async def test_get_ohlcv_batch_with_ab_testing(
        self, mock_default_provider, mock_fallback_provider, sample_ohlcv_bars
    ):
        """Test batch fetch with A/B testing enabled."""
        # Providers don't support batch, will use parallel
        mock_default_provider.get_ohlcv = AsyncMock(return_value=sample_ohlcv_bars)
        mock_fallback_provider.get_ohlcv = AsyncMock(return_value=sample_ohlcv_bars)
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
        )
        # Remove batch method to force parallel fallback
        delattr(mock_default_provider, "get_ohlcv_batch")
        result = await provider.get_ohlcv_batch(
            symbols=["TCS", "INFY"],
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert "TCS" in result
        assert "INFY" in result
        summary = provider.get_ab_test_summary()
        assert summary["total_tests"] == 2


class TestMigrationProviderResults:
    """Test A/B test results management."""

    def test_get_ab_test_results_empty(self):
        """Test getting empty results."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
            enable_ab_testing=True,
        )
        results = provider.get_ab_test_results()
        assert results == []

    def test_clear_ab_test_results(self):
        """Test clearing results."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
            enable_ab_testing=True,
        )
        # Simulate adding a result
        result = ABTestResult(
            symbol="TCS",
            exchange=Exchange.NSE,
            default_source="jugaad",
            fallback_source="kite",
            timestamp_utc=datetime.now(UTC),
            bars_count_match=True,
            price_diff_pct=Decimal("0"),
            volume_diff_pct=Decimal("0"),
            max_diff_pct=Decimal("0"),
            exceeds_threshold=False,
        )
        provider._ab_test_results.append(result)
        assert len(provider.get_ab_test_results()) == 1
        provider.clear_ab_test_results()
        assert len(provider.get_ab_test_results()) == 0

    def test_get_ab_test_summary_empty(self):
        """Test summary with no results."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
            enable_ab_testing=True,
        )
        summary = provider.get_ab_test_summary()
        assert summary["total_tests"] == 0
        assert summary["anomalies"] == 0
        assert summary["max_diff_pct"] == Decimal("0")
        assert summary["avg_diff_pct"] == Decimal("0")

    def test_get_ab_test_summary_with_data(self):
        """Test summary with test data."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
            enable_ab_testing=True,
        )
        # Add test results
        for i in range(3):
            result = ABTestResult(
                symbol=f"SYMBOL{i}",
                exchange=Exchange.NSE,
                default_source="jugaad",
                fallback_source="kite",
                timestamp_utc=datetime.now(UTC),
                bars_count_match=True,
                price_diff_pct=Decimal(f"{i}.0"),
                volume_diff_pct=Decimal(f"{i}.0"),
                max_diff_pct=Decimal(f"{i * 2}.0"),
                exceeds_threshold=(i * 2 > 5.0),
            )
            provider._ab_test_results.append(result)
        summary = provider.get_ab_test_summary()
        assert summary["total_tests"] == 3
        assert summary["max_diff_pct"] == Decimal("4.0")  # 2*2
        assert summary["avg_diff_pct"] == Decimal("2.0")  # (0+2+4)/3


class TestMigrationProviderEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_get_ohlcv_empty_results(self, mock_default_provider):
        """Test handling of empty results."""
        mock_default_provider.get_ohlcv.return_value = []
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=AsyncMock(),
            enable_ab_testing=True,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=30,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ohlcv_zero_price_diff(self, mock_default_provider, mock_fallback_provider):
        """Test A/B testing with zero price difference."""
        bars1 = [
            OHLCVBar(
                timestamp=create_timestamp(datetime.now(UTC)),
                exchange=Exchange.NSE,
                symbol="TCS",
                open=create_price("1000"),
                high=create_price("1000"),
                low=create_price("1000"),
                close=create_price("1000"),
                volume=create_quantity("1000"),
                source="test",
            )
        ]
        bars2 = [
            OHLCVBar(
                timestamp=create_timestamp(datetime.now(UTC)),
                exchange=Exchange.NSE,
                symbol="TCS",
                open=create_price("1000"),
                high=create_price("1000"),
                low=create_price("1000"),
                close=create_price("1000"),
                volume=create_quantity("1000"),
                source="test",
            )
        ]
        mock_default_provider.get_ohlcv.return_value = bars1
        mock_fallback_provider.get_ohlcv.return_value = bars2
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )
        assert result == bars1
        summary = provider.get_ab_test_summary()
        assert summary["anomalies"] == 0

    @pytest.mark.asyncio
    async def test_get_ohlcv_max_diff_threshold_exactly(
        self, mock_default_provider, mock_fallback_provider
    ):
        """Test A/B testing when diff exactly equals threshold."""
        # Create bars with exactly 5% difference
        bars1 = [
            OHLCVBar(
                timestamp=create_timestamp(datetime.now(UTC)),
                exchange=Exchange.NSE,
                symbol="TCS",
                open=create_price("1000"),
                high=create_price("1000"),
                low=create_price("1000"),
                close=create_price("1000"),
                volume=create_quantity("1000"),
                source="test",
            )
        ]
        bars2 = [
            OHLCVBar(
                timestamp=create_timestamp(datetime.now(UTC)),
                exchange=Exchange.NSE,
                symbol="TCS",
                open=create_price("1000"),
                high=create_price("1000"),
                low=create_price("1000"),
                close=create_price("1050"),  # 5% higher
                volume=create_quantity("1000"),
                source="test",
            )
        ]
        mock_default_provider.get_ohlcv.return_value = bars1
        mock_fallback_provider.get_ohlcv.return_value = bars2
        provider = MigrationProvider(
            default_provider=mock_default_provider,
            fallback_provider=mock_fallback_provider,
            enable_ab_testing=True,
            max_diff_pct=Decimal("5.0"),
        )
        result = await provider.get_ohlcv(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe="1d",
            limit=1,
        )
        assert result == bars1
        summary = provider.get_ab_test_summary()
        # Should not exceed threshold (5% is exactly threshold)
        assert summary["anomalies"] == 0


class TestMigrationProviderUtilities:
    """Test utility methods."""

    def test_calculate_diff_pct_both_zero(self):
        """Test diff calculation with both values zero."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
        )
        diff = provider._calculate_diff_pct(Decimal("0"), Decimal("0"))
        assert diff == Decimal("0")

    def test_calculate_diff_pct_first_zero(self):
        """Test diff calculation when first value is zero."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
        )
        diff = provider._calculate_diff_pct(Decimal("0"), Decimal("100"))
        assert diff == Decimal("100")

    def test_calculate_diff_pct_normal(self):
        """Test normal diff calculation."""
        provider = MigrationProvider(
            default_provider=AsyncMock(),
            fallback_provider=AsyncMock(),
        )
        # (110 - 100) / 110 * 100 = 9.09%
        diff = provider._calculate_diff_pct(Decimal("110"), Decimal("100"))
        assert diff == Decimal("9.090909090909090909090909091")

    def test_get_provider_name(self):
        """Test provider name extraction."""
        mock_provider = MagicMock()
        mock_provider.__class__.__name__ = "JugaadProvider"
        name = MigrationProvider._get_provider_name(mock_provider)
        assert name == "jugaad"
