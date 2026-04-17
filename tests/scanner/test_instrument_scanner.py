"""Tests for instrument_scanner.py - focused on uncovered lines."""

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
    ScannerConfig,
    ScannerResult,
    _last_decimal,
    _to_decimal,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestToDecimal:
    def test_none_value_raises_error(self):
        with pytest.raises(ConfigError, match="cannot be None"):
            _to_decimal(None, "test_field")

    def test_invalid_string_raises_error(self):
        with pytest.raises(ConfigError, match="not decimal-compatible"):
            _to_decimal("invalid", "test_field")

    def test_nan_value_raises_error(self):
        with pytest.raises(ConfigError, match="must be finite"):
            _to_decimal(float("nan"), "test_field")

    def test_inf_value_raises_error(self):
        with pytest.raises(ConfigError, match="must be finite"):
            _to_decimal(float("inf"), "test_field")

    def test_valid_decimal_conversion(self):
        assert _to_decimal("123.45", "test") == Decimal("123.45")
        assert _to_decimal(100, "test") == Decimal("100")


class TestLastDecimal:
    def test_empty_sequence_raises_error(self):
        with pytest.raises(ConfigError, match="returned empty sequence"):
            _last_decimal([], "test_field")

    def test_unsupported_type_raises_error(self):
        with pytest.raises(ConfigError, match="unsupported output type"):
            _last_decimal("not_a_sequence", "test_field")

    def test_extracts_last_value(self):
        values = [10, 20, 30]
        assert _last_decimal(values, "test") == Decimal("30")


class TestInstrumentScanner:
    def test_scan_with_custom_data(self):
        """Test scan using custom data (bypasses jugaad fetch)."""
        custom_data = [
            MarketData(
                symbol="TCS",
                exchange=Exchange.NSE,
                category=InstrumentCategory.STOCK,
                close_price=Decimal("3500"),
                prev_close_price=Decimal("3400"),
                volume=Decimal("1000000"),
                avg_volume=Decimal("500000"),
                timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
                high_price=Decimal("3550"),
                low_price=Decimal("3450"),
                adx=Decimal("30"),
                atr_pct=Decimal("0.02"),
                breadth_ratio=Decimal("1.5"),
            )
        ]

        scanner = InstrumentScanner(
            sentiment_analyzer=create_mock_sentiment_analyzer({"TCS": (Decimal("0.8"), True)}),
            rl_predictor=create_mock_rl_predictor(Decimal("0.6")),
            symbols=[],
        )

        result = scanner.scan(custom_data=custom_data)
        assert isinstance(result, ScannerResult)
        assert result.total_scanned == 1

    def test_fetch_market_data_with_empty_symbols(self):
        scanner = InstrumentScanner(symbols=[])
        data = scanner._fetch_market_data()
        assert data == []

    def test_get_strength_with_unsupported_exchange(self):
        scanner = InstrumentScanner()
        # Test with exchange that might not be configured in strength_scorer
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

        # Should not raise exception, return defaults on error
        score, is_tradable = scanner._get_strength(data)
        assert score >= Decimal("0")


class TestScannerConfig:
    def test_negative_min_volume_ratio_raises_error(self):
        with pytest.raises(ConfigError, match="min_volume_ratio cannot be negative"):
            ScannerConfig(min_volume_ratio=Decimal("-1"))

    def test_invalid_very_strong_threshold_raises_error(self):
        with pytest.raises(ConfigError, match="very_strong_threshold must be in"):
            ScannerConfig(very_strong_threshold=Decimal("1.5"))

        with pytest.raises(ConfigError, match="very_strong_threshold must be in"):
            ScannerConfig(very_strong_threshold=Decimal("0"))

    def test_invalid_min_exit_probability_raises_error(self):
        with pytest.raises(ConfigError, match="min_exit_probability must be in"):
            ScannerConfig(min_exit_probability=Decimal("1.5"))

    def test_non_positive_top_n_raises_error(self):
        with pytest.raises(ConfigError, match="top_n must be positive"):
            ScannerConfig(top_n=0)

    def test_empty_exchanges_raises_error(self):
        with pytest.raises(ConfigError, match="exchanges cannot be empty"):
            ScannerConfig(exchanges=())

    def test_empty_categories_raises_error(self):
        with pytest.raises(ConfigError, match="categories cannot be empty"):
            ScannerConfig(categories=())


class TestMarketData:
    def test_pct_change_with_zero_prev_close(self):
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("0"),
            volume=Decimal("1000"),
            avg_volume=Decimal("500"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("105"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
        assert data.pct_change == Decimal("0")

    def test_volume_ratio_with_zero_avg_volume(self):
        data = MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("1000"),
            avg_volume=Decimal("0"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("105"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
        assert data.volume_ratio == Decimal("0")
