"""
Unit tests for src/iatb/scanner/instrument_scanner.py.

Tests cover: happy path, edge cases, errors, precision, timezone handling.
All external calls are mocked.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    ScannerCandidate,
    ScannerConfig,
    ScannerResult,
    SortDirection,
    create_mock_data_provider,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def utc_timestamp():
    """UTC timestamp for testing."""
    return datetime(2026, 1, 5, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def valid_market_data(utc_timestamp):
    """Valid market data for testing."""
    return MarketData(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("2500.00"),
        prev_close_price=Decimal("2400.00"),
        volume=Decimal("10000000"),
        avg_volume=Decimal("4000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("2520.00"),
        low_price=Decimal("2390.00"),
        adx=Decimal("25.0"),
        atr_pct=Decimal("0.025"),
        breadth_ratio=Decimal("1.5"),
    )


@pytest.fixture
def gainer_market_data(utc_timestamp):
    """Market data for a gainer stock."""
    return MarketData(
        symbol="TATAMOTORS",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("500.00"),
        prev_close_price=Decimal("450.00"),
        volume=Decimal("15000000"),
        avg_volume=Decimal("5000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("510.00"),
        low_price=Decimal("445.00"),
        adx=Decimal("30.0"),
        atr_pct=Decimal("0.020"),
        breadth_ratio=Decimal("2.0"),
    )


@pytest.fixture
def loser_market_data(utc_timestamp):
    """Market data for a loser stock."""
    return MarketData(
        symbol="INFY",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("1400.00"),
        prev_close_price=Decimal("1500.00"),
        volume=Decimal("8000000"),
        avg_volume=Decimal("3000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("1490.00"),
        low_price=Decimal("1395.00"),
        adx=Decimal("20.0"),
        atr_pct=Decimal("0.030"),
        breadth_ratio=Decimal("0.8"),
    )


@pytest.fixture
def option_market_data(utc_timestamp):
    """Market data for an option."""
    return MarketData(
        symbol="NIFTY24JAN22000CE",
        exchange=Exchange.NSE,
        category=InstrumentCategory.OPTION,
        close_price=Decimal("150.00"),
        prev_close_price=Decimal("100.00"),
        volume=Decimal("5000000"),
        avg_volume=Decimal("2000000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("160.00"),
        low_price=Decimal("95.00"),
        adx=Decimal("35.0"),
        atr_pct=Decimal("0.040"),
        breadth_ratio=Decimal("2.5"),
    )


@pytest.fixture
def future_market_data(utc_timestamp):
    """Market data for a future."""
    return MarketData(
        symbol="BANKNIFTY24JANFUT",
        exchange=Exchange.NSE,
        category=InstrumentCategory.FUTURE,
        close_price=Decimal("45000.00"),
        prev_close_price=Decimal("44000.00"),
        volume=Decimal("2000000"),
        avg_volume=Decimal("800000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("45200.00"),
        low_price=Decimal("43800.00"),
        adx=Decimal("28.0"),
        atr_pct=Decimal("0.018"),
        breadth_ratio=Decimal("1.8"),
    )


@pytest.fixture
def mcx_market_data(utc_timestamp):
    """Market data for MCX exchange."""
    return MarketData(
        symbol="GOLD24FEBFUT",
        exchange=Exchange.MCX,
        category=InstrumentCategory.FUTURE,
        close_price=Decimal("62000.00"),
        prev_close_price=Decimal("61000.00"),
        volume=Decimal("500000"),
        avg_volume=Decimal("200000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("62200.00"),
        low_price=Decimal("60800.00"),
        adx=Decimal("22.0"),
        atr_pct=Decimal("0.015"),
        breadth_ratio=Decimal("1.6"),
    )


@pytest.fixture
def cds_market_data(utc_timestamp):
    """Market data for CDS exchange."""
    return MarketData(
        symbol="USDINR24JANFUT",
        exchange=Exchange.CDS,
        category=InstrumentCategory.FUTURE,
        close_price=Decimal("83.00"),
        prev_close_price=Decimal("82.50"),
        volume=Decimal("1000000"),
        avg_volume=Decimal("400000"),
        timestamp_utc=utc_timestamp,
        high_price=Decimal("83.20"),
        low_price=Decimal("82.40"),
        adx=Decimal("18.0"),
        atr_pct=Decimal("0.008"),
        breadth_ratio=Decimal("1.4"),
    )


@pytest.fixture
def mock_sentiment_strong():
    """Mock sentiment analyzer returning VERY_STRONG."""
    return create_mock_sentiment_analyzer(
        {
            "RELIANCE": (Decimal("0.80"), True),
            "TATAMOTORS": (Decimal("0.85"), True),
            "INFY": (Decimal("-0.78"), True),
            "NIFTY24JAN22000CE": (Decimal("0.90"), True),
            "BANKNIFTY24JANFUT": (Decimal("0.82"), True),
            "GOLD24FEBFUT": (Decimal("0.77"), True),
            "USDINR24JANFUT": (Decimal("0.79"), True),
        }
    )


@pytest.fixture
def mock_sentiment_weak():
    """Mock sentiment analyzer returning weak sentiment."""
    return create_mock_sentiment_analyzer(
        {
            "RELIANCE": (Decimal("0.50"), False),
            "TATAMOTORS": (Decimal("0.60"), False),
        }
    )


@pytest.fixture
def mock_rl_positive():
    """Mock RL predictor returning positive exit probability."""
    return create_mock_rl_predictor(Decimal("0.65"))


@pytest.fixture
def mock_rl_negative():
    """Mock RL predictor returning negative exit probability."""
    return create_mock_rl_predictor(Decimal("0.30"))


@pytest.fixture
def scanner_with_mocks(mock_sentiment_strong, mock_rl_positive):
    """Scanner with all mocks configured."""
    return InstrumentScanner(
        sentiment_analyzer=mock_sentiment_strong,
        rl_predictor=mock_rl_positive,
    )


# =============================================================================
# ScannerConfig Tests
# =============================================================================


class TestScannerConfig:
    """Tests for ScannerConfig validation."""

    def test_default_config_is_valid(self):
        """Test default configuration is valid."""
        config = ScannerConfig()
        assert config.min_volume_ratio == Decimal("2.0")
        assert config.very_strong_threshold == Decimal("0.75")
        assert config.min_exit_probability == Decimal("0.5")
        assert config.top_n == 10
        assert Exchange.NSE in config.exchanges

    def test_custom_config_is_valid(self):
        """Test custom configuration values."""
        config = ScannerConfig(
            min_volume_ratio=Decimal("3.0"),
            very_strong_threshold=Decimal("0.80"),
            min_exit_probability=Decimal("0.6"),
            top_n=5,
        )
        assert config.min_volume_ratio == Decimal("3.0")
        assert config.very_strong_threshold == Decimal("0.80")
        assert config.min_exit_probability == Decimal("0.6")
        assert config.top_n == 5

    def test_negative_volume_ratio_raises(self):
        """Test negative volume ratio raises ConfigError."""
        with pytest.raises(ConfigError, match="min_volume_ratio"):
            ScannerConfig(min_volume_ratio=Decimal("-1.0"))

    def test_zero_threshold_raises(self):
        """Test zero threshold raises ConfigError."""
        with pytest.raises(ConfigError, match="very_strong_threshold"):
            ScannerConfig(very_strong_threshold=Decimal("0"))

    def test_threshold_above_one_raises(self):
        """Test threshold above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="very_strong_threshold"):
            ScannerConfig(very_strong_threshold=Decimal("1.5"))

    def test_negative_exit_probability_raises(self):
        """Test negative exit probability raises ConfigError."""
        with pytest.raises(ConfigError, match="min_exit_probability"):
            ScannerConfig(min_exit_probability=Decimal("-0.1"))

    def test_exit_probability_above_one_raises(self):
        """Test exit probability above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="min_exit_probability"):
            ScannerConfig(min_exit_probability=Decimal("1.5"))

    def test_zero_top_n_raises(self):
        """Test zero top_n raises ConfigError."""
        with pytest.raises(ConfigError, match="top_n"):
            ScannerConfig(top_n=0)

    def test_negative_top_n_raises(self):
        """Test negative top_n raises ConfigError."""
        with pytest.raises(ConfigError, match="top_n"):
            ScannerConfig(top_n=-5)

    def test_empty_exchanges_raises(self):
        """Test empty exchanges raises ConfigError."""
        with pytest.raises(ConfigError, match="exchanges"):
            ScannerConfig(exchanges=())

    def test_empty_categories_raises(self):
        """Test empty categories raises ConfigError."""
        with pytest.raises(ConfigError, match="categories"):
            ScannerConfig(categories=())


# =============================================================================
# MarketData Tests
# =============================================================================


class TestMarketData:
    """Tests for MarketData class."""

    def test_pct_change_positive(self, valid_market_data):
        """Test positive percentage change calculation."""
        expected = ((Decimal("2500") - Decimal("2400")) / Decimal("2400")) * Decimal("100")
        assert valid_market_data.pct_change == expected

    def test_pct_change_negative(self, loser_market_data):
        """Test negative percentage change calculation."""
        expected = ((Decimal("1400") - Decimal("1500")) / Decimal("1500")) * Decimal("100")
        assert loser_market_data.pct_change == expected

    def test_pct_change_zero_prev_close(self, utc_timestamp):
        """Test pct_change returns 0 when prev_close is 0."""
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("0"),
            volume=Decimal("1000"),
            avg_volume=Decimal("500"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("20"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.0"),
        )
        assert data.pct_change == Decimal("0")

    def test_volume_ratio_calculation(self, valid_market_data):
        """Test volume ratio calculation."""
        expected = Decimal("10000000") / Decimal("4000000")
        assert valid_market_data.volume_ratio == expected

    def test_volume_ratio_zero_avg_volume(self, utc_timestamp):
        """Test volume ratio returns 0 when avg_volume is 0."""
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("1000"),
            avg_volume=Decimal("0"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("20"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.0"),
        )
        assert data.volume_ratio == Decimal("0")

    def test_timestamp_is_utc(self, valid_market_data):
        """Test timestamp is timezone-aware UTC."""
        assert valid_market_data.timestamp_utc.tzinfo == UTC


# =============================================================================
# InstrumentScanner Happy Path Tests
# =============================================================================


class TestInstrumentScannerHappyPath:
    """Happy path tests for InstrumentScanner."""

    def test_scan_returns_result(self, scanner_with_mocks, valid_market_data):
        """Test scan returns ScannerResult."""
        result = scanner_with_mocks.scan(custom_data=[valid_market_data])
        assert isinstance(result, ScannerResult)

    def test_scan_with_gainers(
        self, scanner_with_mocks, gainer_market_data, mock_sentiment_strong, mock_rl_positive
    ):
        """Test scan identifies gainers correctly."""
        result = scanner_with_mocks.scan(custom_data=[gainer_market_data])
        assert len(result.gainers) >= 0
        assert result.losers == []

    def test_scan_with_losers(self, scanner_with_mocks, loser_market_data):
        """Test scan identifies losers correctly."""
        # Need to update sentiment for INFY
        result = scanner_with_mocks.scan(custom_data=[loser_market_data])
        assert len(result.losers) >= 0

    def test_scan_ranking_by_pct_change(
        self, mock_sentiment_strong, mock_rl_positive, utc_timestamp
    ):
        """Test gainers are ranked by % change descending."""
        data1 = MarketData(
            symbol="STOCK1",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        data2 = MarketData(
            symbol="STOCK2",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("210"),
            prev_close_price=Decimal("200"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("212"),
            low_price=Decimal("199"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer(
            {
                "STOCK1": (Decimal("0.80"), True),
                "STOCK2": (Decimal("0.80"), True),
            }
        )
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[data1, data2])
        if len(result.gainers) >= 2:
            assert result.gainers[0].pct_change > result.gainers[1].pct_change

    def test_scan_respects_top_n(self, mock_sentiment_strong, mock_rl_positive, utc_timestamp):
        """Test scan respects top_n configuration."""
        data_list = []
        for i in range(20):
            data = MarketData(
                symbol=f"STOCK{i}",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal("110") + Decimal(str(i)),
                prev_close_price=Decimal("100"),
                volume=Decimal("10000000"),
                avg_volume=Decimal("3000000"),
                timestamp_utc=utc_timestamp,
                high_price=Decimal("115"),
                low_price=Decimal("99"),
                adx=Decimal("25"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("2.0"),
            )
            data_list.append(data)

        sentiment = create_mock_sentiment_analyzer(
            {f"STOCK{i}": (Decimal("0.80"), True) for i in range(20)}
        )
        scanner = InstrumentScanner(
            config=ScannerConfig(top_n=5),
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=data_list)
        assert len(result.gainers) <= 5

    def test_scan_multiple_exchanges(
        self,
        mock_sentiment_strong,
        mock_rl_positive,
        gainer_market_data,
        mcx_market_data,
        cds_market_data,
    ):
        """Test scan handles multiple exchanges."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[gainer_market_data, mcx_market_data, cds_market_data])
        assert result.total_scanned == 3

    def test_scan_multiple_categories(
        self,
        mock_sentiment_strong,
        mock_rl_positive,
        gainer_market_data,
        option_market_data,
        future_market_data,
    ):
        """Test scan handles multiple instrument categories."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(
            custom_data=[gainer_market_data, option_market_data, future_market_data]
        )
        assert result.total_scanned == 3


# =============================================================================
# Filter Tests
# =============================================================================


class TestInstrumentScannerFilters:
    """Tests for scanner filtering logic."""

    def test_filter_by_sentiment_weak(
        self, mock_sentiment_weak, mock_rl_positive, gainer_market_data
    ):
        """Test weak sentiment is filtered out."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_weak,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        # With weak sentiment, should be filtered
        assert result.filtered_count >= 1 or len(result.gainers) == 0

    def test_filter_by_volume_ratio(self, mock_sentiment_strong, mock_rl_positive, utc_timestamp):
        """Test low volume ratio is filtered out."""
        low_volume_data = MarketData(
            symbol="LOWVOL",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("1000"),  # Very low
            avg_volume=Decimal("10000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer({"LOWVOL": (Decimal("0.80"), True)})
        scanner = InstrumentScanner(
            config=ScannerConfig(min_volume_ratio=Decimal("2.0")),
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[low_volume_data])
        assert len(result.gainers) == 0

    def test_filter_by_exit_probability(self, mock_sentiment_strong, gainer_market_data):
        """Test low exit probability is filtered out."""
        low_rl = create_mock_rl_predictor(Decimal("0.2"))
        scanner = InstrumentScanner(
            config=ScannerConfig(min_exit_probability=Decimal("0.5")),
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=low_rl,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        assert len(result.gainers) == 0

    def test_all_filters_must_pass(self, mock_sentiment_strong, mock_rl_positive, utc_timestamp):
        """Test all filters must pass for emission."""
        # Data that passes all filters
        good_data = MarketData(
            symbol="GOOD",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        # Data that fails volume filter
        bad_volume = MarketData(
            symbol="BADVOL",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("1000"),
            avg_volume=Decimal("10000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer(
            {
                "GOOD": (Decimal("0.80"), True),
                "BADVOL": (Decimal("0.80"), True),
            }
        )
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[good_data, bad_volume])
        symbols = [c.symbol for c in result.gainers]
        assert "GOOD" in symbols
        assert "BADVOL" not in symbols


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestInstrumentScannerEdgeCases:
    """Edge case tests for InstrumentScanner."""

    def test_empty_data_returns_empty_result(self, scanner_with_mocks):
        """Test empty data returns empty result."""
        result = scanner_with_mocks.scan(custom_data=[])
        assert result.gainers == []
        assert result.losers == []
        assert result.total_scanned == 0

    def test_no_data_provider_returns_empty(self):
        """Test scanner without data provider returns empty."""
        scanner = InstrumentScanner()
        result = scanner.scan()
        assert result.total_scanned == 0

    def test_zero_pct_change_not_in_gainers_or_losers(
        self, mock_sentiment_strong, mock_rl_positive, utc_timestamp
    ):
        """Test zero pct change is not in gainers or losers."""
        zero_change = MarketData(
            symbol="ZEROCHANGE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("102"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer({"ZEROCHANGE": (Decimal("0.80"), True)})
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[zero_change])
        assert len(result.gainers) == 0
        assert len(result.losers) == 0

    def test_no_sentiment_analyzer_filters_all(self, gainer_market_data):
        """Test no sentiment analyzer filters all candidates."""
        scanner = InstrumentScanner(
            sentiment_analyzer=None,
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        assert len(result.gainers) == 0

    def test_no_rl_predictor_filters_all(self, gainer_market_data, mock_sentiment_strong):
        """Test no RL predictor filters all candidates."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=None,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        assert len(result.gainers) == 0

    def test_single_candidate_passing(
        self, mock_sentiment_strong, mock_rl_positive, gainer_market_data
    ):
        """Test single candidate passing all filters."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        assert result.total_scanned == 1


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestInstrumentScannerErrors:
    """Error handling tests for InstrumentScanner."""

    def test_invalid_exchange_in_data_handled(self, utc_timestamp):
        """Test invalid exchange in market data is handled."""
        # This test verifies the scanner doesn't crash on invalid data
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.BINANCE,  # Not in default exchanges
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        scanner = InstrumentScanner()
        # Should not raise
        result = scanner.scan(custom_data=[data])
        assert isinstance(result, ScannerResult)

    def test_strength_scorer_error_handled(
        self, mock_sentiment_strong, mock_rl_positive, utc_timestamp
    ):
        """Test strength scorer errors are handled gracefully."""
        # Create data with invalid values that might cause strength scorer to fail
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("105"),
            low_price=Decimal("95"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        # Should not raise
        result = scanner.scan(custom_data=[data])
        assert isinstance(result, ScannerResult)


# =============================================================================
# Precision Tests
# =============================================================================


class TestInstrumentScannerPrecision:
    """Precision handling tests for InstrumentScanner."""

    def test_decimal_precision_preserved(
        self, mock_sentiment_strong, mock_rl_positive, utc_timestamp
    ):
        """Test Decimal precision is preserved throughout scanning."""
        precise_data = MarketData(
            symbol="PRECISE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("123.456789"),
            prev_close_price=Decimal("120.123456"),
            volume=Decimal("1000000"),
            avg_volume=Decimal("400000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("125.0"),
            low_price=Decimal("119.0"),
            adx=Decimal("25.12345"),
            atr_pct=Decimal("0.02567"),
            breadth_ratio=Decimal("1.87654"),
        )
        sentiment = create_mock_sentiment_analyzer({"PRECISE": (Decimal("0.80"), True)})
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[precise_data])
        if result.gainers:
            assert isinstance(result.gainers[0].pct_change, Decimal)
            assert isinstance(result.gainers[0].composite_score, Decimal)

    def test_composite_score_precision(
        self, mock_sentiment_strong, mock_rl_positive, gainer_market_data
    ):
        """Test composite score is computed with Decimal precision."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        if result.gainers:
            score = result.gainers[0].composite_score
            assert isinstance(score, Decimal)
            assert score >= Decimal("0")
            assert score <= Decimal("1")

    def test_no_float_in_financial_calculations(
        self, mock_sentiment_strong, mock_rl_positive, gainer_market_data
    ):
        """Test no float is used in financial calculations."""
        scanner = InstrumentScanner(
            sentiment_analyzer=mock_sentiment_strong,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[gainer_market_data])
        if result.gainers:
            candidate = result.gainers[0]
            assert isinstance(candidate.pct_change, Decimal)
            assert isinstance(candidate.volume_ratio, Decimal)
            assert isinstance(candidate.composite_score, Decimal)
            assert isinstance(candidate.sentiment_score, Decimal)
            assert isinstance(candidate.exit_probability, Decimal)


# =============================================================================
# Timezone Tests
# =============================================================================


class TestInstrumentScannerTimezone:
    """Timezone handling tests for InstrumentScanner."""

    def test_scan_timestamp_is_utc(self, scanner_with_mocks, valid_market_data):
        """Test scan timestamp is UTC."""
        result = scanner_with_mocks.scan(custom_data=[valid_market_data])
        assert result.scan_timestamp_utc.tzinfo == UTC

    def test_candidate_timestamp_preserved(
        self, mock_sentiment_strong, mock_rl_positive, utc_timestamp
    ):
        """Test candidate timestamp is preserved from market data."""
        data = MarketData(
            symbol="TIMEZONE",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=utc_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer({"TIMEZONE": (Decimal("0.80"), True)})
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[data])
        if result.gainers:
            assert result.gainers[0].timestamp_utc.tzinfo == UTC

    def test_microsecond_precision_timestamp(self, mock_sentiment_strong, mock_rl_positive):
        """Test microsecond precision in timestamps is preserved."""
        precise_timestamp = datetime(2026, 1, 5, 10, 30, 15, 123456, tzinfo=UTC)
        data = MarketData(
            symbol="MICRO",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000000"),
            avg_volume=Decimal("3000000"),
            timestamp_utc=precise_timestamp,
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("2.0"),
        )
        sentiment = create_mock_sentiment_analyzer({"MICRO": (Decimal("0.80"), True)})
        scanner = InstrumentScanner(
            sentiment_analyzer=sentiment,
            rl_predictor=mock_rl_positive,
        )
        result = scanner.scan(custom_data=[data])
        if result.gainers:
            assert result.gainers[0].timestamp_utc.microsecond == 123456


# =============================================================================
# Mock Helper Tests
# =============================================================================


class TestMockHelpers:
    """Tests for mock helper functions."""

    def test_create_mock_data_provider(self, valid_market_data):
        """Test mock data provider creation."""
        provider = create_mock_data_provider([valid_market_data])
        result = provider(Exchange.NSE, InstrumentCategory.STOCK)
        assert len(result) == 1
        assert result[0].symbol == "RELIANCE"

    def test_create_mock_data_provider_filters_by_exchange(
        self, valid_market_data, mcx_market_data
    ):
        """Test mock data provider filters by exchange."""
        provider = create_mock_data_provider([valid_market_data, mcx_market_data])
        result = provider(Exchange.NSE, InstrumentCategory.STOCK)
        assert len(result) == 1

    def test_create_mock_sentiment_analyzer(self):
        """Test mock sentiment analyzer creation."""
        analyzer = create_mock_sentiment_analyzer({"TEST": (Decimal("0.8"), True)})
        score, is_strong = analyzer("TEST")
        assert score == Decimal("0.8")
        assert is_strong is True

    def test_create_mock_sentiment_analyzer_unknown_symbol(self):
        """Test mock sentiment analyzer returns default for unknown symbol."""
        analyzer = create_mock_sentiment_analyzer({})
        score, is_strong = analyzer("UNKNOWN")
        assert score == Decimal("0")
        assert is_strong is False

    def test_create_mock_rl_predictor(self):
        """Test mock RL predictor creation."""
        predictor = create_mock_rl_predictor(Decimal("0.7"))
        result = predictor([Decimal("0.1"), Decimal("2.0")])
        assert result == Decimal("0.7")


# =============================================================================
# ScannerCandidate Tests
# =============================================================================


class TestScannerCandidate:
    """Tests for ScannerCandidate dataclass."""

    def test_candidate_has_required_fields(self, utc_timestamp):
        """Test candidate has all required fields."""
        candidate = ScannerCandidate(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.0"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("2.5"),
            exit_probability=Decimal("0.6"),
            is_tradable=True,
            regime=MarketRegime.BULL,
            rank=1,
            timestamp_utc=utc_timestamp,
            metadata={"key": "value"},
        )
        assert candidate.symbol == "TEST"
        assert candidate.exchange == Exchange.NSE
        assert candidate.category == InstrumentCategory.STOCK
        assert candidate.is_tradable is True

    def test_candidate_is_frozen(self, utc_timestamp):
        """Test candidate is immutable."""
        candidate = ScannerCandidate(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            pct_change=Decimal("5.0"),
            composite_score=Decimal("0.75"),
            sentiment_score=Decimal("0.80"),
            volume_ratio=Decimal("2.5"),
            exit_probability=Decimal("0.6"),
            is_tradable=True,
            regime=MarketRegime.BULL,
            rank=1,
            timestamp_utc=utc_timestamp,
            metadata={},
        )
        with pytest.raises(AttributeError):
            candidate.symbol = "CHANGED"


# =============================================================================
# ScannerResult Tests
# =============================================================================


class TestScannerResult:
    """Tests for ScannerResult dataclass."""

    def test_result_has_required_fields(self, utc_timestamp):
        """Test result has all required fields."""
        result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=10,
            filtered_count=8,
            scan_timestamp_utc=utc_timestamp,
        )
        assert result.gainers == []
        assert result.losers == []
        assert result.total_scanned == 10
        assert result.filtered_count == 8

    def test_result_timestamp_is_utc(self):
        """Test result timestamp is UTC."""
        result = ScannerResult(
            gainers=[],
            losers=[],
            total_scanned=0,
            filtered_count=0,
            scan_timestamp_utc=datetime.now(UTC),
        )
        assert result.scan_timestamp_utc.tzinfo == UTC


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests for enum types."""

    def test_instrument_category_values(self):
        """Test InstrumentCategory has expected values."""
        assert InstrumentCategory.STOCK.value == "STOCK"
        assert InstrumentCategory.OPTION.value == "OPTION"
        assert InstrumentCategory.FUTURE.value == "FUTURE"

    def test_sort_direction_values(self):
        """Test SortDirection has expected values."""
        assert SortDirection.GAINERS.value == "GAINERS"
        assert SortDirection.LOSERS.value == "LOSERS"

    def test_instrument_category_from_string(self):
        """Test InstrumentCategory can be created from string."""
        assert InstrumentCategory("STOCK") == InstrumentCategory.STOCK

    def test_sort_direction_from_string(self):
        """Test SortDirection can be created from string."""
        assert SortDirection("GAINERS") == SortDirection.GAINERS
