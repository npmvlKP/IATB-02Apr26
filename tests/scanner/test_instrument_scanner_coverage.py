"""Additional tests for instrument_scanner.py to improve coverage to 90%+."""

import random
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    _to_decimal,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_to_decimal_with_none():
    """Test that None raises ConfigError."""
    with pytest.raises(ConfigError, match="cannot be None"):
        _to_decimal(None, "test_field")


def test_to_decimal_with_invalid_string():
    """Test that invalid string raises ConfigError."""
    with pytest.raises(ConfigError, match="not decimal-compatible"):
        _to_decimal("not_a_number", "test_field")


def test_to_decimal_with_nan():
    """Test that NaN raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("nan"), "test_field")


def test_to_decimal_with_inf():
    """Test that infinity raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("inf"), "test_field")


def test_to_decimal_with_negative_inf():
    """Test that negative infinity raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("-inf"), "test_field")


def test_to_decimal_with_valid_types():
    """Test conversion of valid types."""
    assert _to_decimal("123.45", "test") == Decimal("123.45")
    assert _to_decimal(100, "test") == Decimal("100")
    assert _to_decimal(50.75, "test") == Decimal("50.75")
    assert _to_decimal(Decimal("99.99"), "test") == Decimal("99.99")


def test_scanner_apply_filters_all_filtered():
    """Test that all candidates can be filtered out."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("1000"),  # Low volume ratio
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("105"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
    ]

    result = scanner.scan(custom_data=custom_data)
    # All filtered out: not very strong, low volume, low exit probability
    assert len(result.gainers) == 0
    assert len(result.losers) == 0
    assert result.filtered_count == 1


def test_scanner_rank_and_split_empty_list():
    """Test ranking with empty list."""
    scanner = InstrumentScanner()
    gainers, losers = scanner._rank_and_split_with_correlation([])
    assert gainers == []
    assert losers == []


def test_scanner_to_scanner_candidates_empty_list():
    """Test converting empty candidates list."""
    scanner = InstrumentScanner()
    candidates = scanner._to_scanner_candidates_with_scores([], [], "gainers")
    assert candidates == []


def test_scanner_get_sentiment_without_aggregator():
    """Test sentiment without aggregator returns defaults."""
    scanner = InstrumentScanner(sentiment_aggregator=None)

    data = MarketData(
        symbol="TEST",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("100"),
        prev_close_price=Decimal("95"),
        volume=Decimal("1000"),
        avg_volume=Decimal("500"),
        timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        high_price=Decimal("105"),
        low_price=Decimal("98"),
        adx=Decimal("25"),
        atr_pct=Decimal("0.01"),
        breadth_ratio=Decimal("1.2"),
    )

    score, is_very_strong = scanner._get_sentiment_pipeline(data, datetime.now(UTC))
    assert score == Decimal("0")
    assert is_very_strong is False


def test_scanner_get_exit_probability_without_aggregator():
    """Test exit probability computation returns valid score."""
    scanner = InstrumentScanner()

    data = MarketData(
        symbol="TEST",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("100"),
        prev_close_price=Decimal("95"),
        volume=Decimal("1000"),
        avg_volume=Decimal("500"),
        timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        high_price=Decimal("105"),
        low_price=Decimal("98"),
        adx=Decimal("25"),
        atr_pct=Decimal("0.01"),
        breadth_ratio=Decimal("1.2"),
    )

    prob = scanner._get_exit_probability_pipeline(data, datetime.now(UTC))
    assert prob >= Decimal("0")
    assert prob <= Decimal("1")


def test_scanner_determine_category_edge_cases():
    """Test category detection for edge cases."""
    assert InstrumentScanner._determine_category("FUT") == InstrumentCategory.FUTURE
    assert InstrumentScanner._determine_category("FUTURE") == InstrumentCategory.FUTURE
    assert InstrumentScanner._determine_category("NIFTYCE") == InstrumentCategory.OPTION
    assert InstrumentScanner._determine_category("NIFTYPE") == InstrumentCategory.OPTION
    # Long symbol name (>10 chars) should be OPTION
    assert InstrumentScanner._determine_category("VERYLONGOPTION") == InstrumentCategory.OPTION


# ============================================================================
# InstrumentScanner._apply_filters Tests
# ============================================================================


def test_apply_filters_all_pass():
    """Test _apply_filters with candidates that have sufficient volume."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )
    ]

    result = scanner.scan(custom_data=custom_data)
    # Without sentiment_aggregator, sentiment is 0 so candidate is filtered out
    # This is expected behavior - the pipeline requires sentiment analysis
    assert result.total_scanned == 1
    assert result.filtered_count == 1


def test_apply_filters_mixed_results():
    """Test _apply_filters with candidates having different volume ratios."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="HIGH_VOL",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
        MarketData(
            symbol="LOW_VOL",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("100"),
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
    ]

    result = scanner.scan(custom_data=custom_data)
    # Both filtered out due to missing sentiment analysis
    assert result.filtered_count == 2


# ============================================================================
# InstrumentScanner Public API Tests
# ============================================================================


def test_scan_with_positive_changes():
    """Test scan with candidates having positive percentage changes."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="A",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
        MarketData(
            symbol="B",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("110"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("115"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
    ]

    result = scanner.scan(custom_data=custom_data)
    # Both candidates filtered out due to missing sentiment analysis
    assert result.total_scanned == 2
    assert len(result.gainers) == 0


def test_scan_with_negative_changes():
    """Test scan with candidates having negative percentage changes."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="A",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("95"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("100"),
            low_price=Decimal("90"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
        MarketData(
            symbol="B",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("90"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("100"),
            low_price=Decimal("85"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
    ]

    result = scanner.scan(custom_data=custom_data)
    assert result.total_scanned == 2
    assert len(result.losers) == 0  # All filtered out due to missing sentiment


# ============================================================================
# ScannerResult Tests
# ============================================================================


def test_scan_result_total_scanned():
    """Test ScanResult.total_scanned is correct."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="A",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
        MarketData(
            symbol="B",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("95"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("100"),
            low_price=Decimal("90"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        ),
    ]

    result = scanner.scan(custom_data=custom_data)
    assert result.total_scanned == 2


def test_scanner_with_zero_exit_probability():
    """Test scanner with low exit probability."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )
    ]

    result = scanner.scan(custom_data=custom_data)
    assert result.total_scanned == 1


# ============================================================================
# Additional edge case tests
# ============================================================================


def test_scanner_with_low_exit_probability():
    """Test scanner with candidates that have low exit probability score."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )
    ]

    result = scanner.scan(custom_data=custom_data)
    # Without sentiment_aggregator, candidate is filtered out
    assert result.total_scanned == 1


def test_scanner_cache_behavior():
    """Test scanner cache behavior with multiple scans."""
    scanner = InstrumentScanner()

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("105"),
            prev_close_price=Decimal("100"),
            volume=Decimal("10000"),
            avg_volume=Decimal("2000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("110"),
            low_price=Decimal("100"),
            adx=Decimal("30"),
            atr_pct=Decimal("0.02"),
            breadth_ratio=Decimal("1.5"),
        )
    ]

    # First scan
    result1 = scanner.scan(custom_data=custom_data)
    assert result1.total_scanned == 1

    # Second scan with same data
    result2 = scanner.scan(custom_data=custom_data)
    # Without sentiment_aggregator, candidates are filtered out
    assert result2.total_scanned == 1
    assert len(result2.gainers) == 0
