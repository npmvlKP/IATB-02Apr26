"""
Comprehensive coverage tests for fundamental_filter.py.

Tests PE/PB/ROE filters, fundamental metrics evaluation.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.fundamental_filter import (
    FundamentalFilter,
    FundamentalFilterConfig,
    FundamentalMetrics,
)


class TestFundamentalFilterConfig:
    """Test configuration validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = FundamentalFilterConfig()
        assert config.min_roe == Decimal("0.05")
        assert config.max_debt_to_equity == Decimal("2.0")
        assert config.min_current_ratio == Decimal("1.0")
        assert config.require_profitability is True

    def test_invalid_pe_range_raises_error(self):
        """Test that invalid P/E range raises ConfigError."""
        with pytest.raises(ConfigError, match="min_pe cannot be greater than max_pe"):
            FundamentalFilterConfig(min_pe=Decimal("100"), max_pe=Decimal("10"))

    def test_invalid_pb_range_raises_error(self):
        """Test that invalid P/B range raises ConfigError."""
        with pytest.raises(ConfigError, match="min_pb cannot be greater than max_pb"):
            FundamentalFilterConfig(min_pb=Decimal("10"), max_pb=Decimal("0.5"))

    def test_negative_roe_raises_error(self):
        """Test that negative ROE raises ConfigError."""
        with pytest.raises(ConfigError, match="min_roe cannot be negative"):
            FundamentalFilterConfig(min_roe=Decimal("-0.05"))

    def test_negative_debt_equity_raises_error(self):
        """Test that negative max_debt_to_equity raises ConfigError."""
        with pytest.raises(ConfigError, match="max_debt_to_equity cannot be negative"):
            FundamentalFilterConfig(max_debt_to_equity=Decimal("-1.0"))

    def test_negative_current_ratio_raises_error(self):
        """Test that negative min_current_ratio raises ConfigError."""
        with pytest.raises(ConfigError, match="min_current_ratio cannot be negative"):
            FundamentalFilterConfig(min_current_ratio=Decimal("-0.5"))

    def test_invalid_market_cap_range_raises_error(self):
        """Test that invalid market cap range raises ConfigError."""
        with pytest.raises(
            ConfigError, match="min_market_cap cannot be greater than max_market_cap"
        ):
            FundamentalFilterConfig(
                min_market_cap=Decimal("10000"), max_market_cap=Decimal("1000")
            )


class TestFundamentalFilter:
    """Test fundamental filter evaluation."""

    def test_filter_with_all_metrics_passing(self):
        """Test filter with all metrics passing."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("2.0"),
            roe=Decimal("0.15"),
            debt_to_equity=Decimal("0.5"),
            current_ratio=Decimal("1.5"),
            dividend_yield=Decimal("0.02"),
            earnings_growth=Decimal("0.10"),
            market_cap=Decimal("500000"),
        )

        result = filter.evaluate(metrics)

        assert result.passed is True
        assert result.symbol == "RELIANCE"
        assert result.score > Decimal("0")
        assert len(result.reasons) == 0

    def test_filter_with_low_roe_fails(self):
        """Test that low ROE fails the filter."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            roe=Decimal("0.02"),  # Below min_roe of 0.05
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert "ROE" in str(result.reasons)

    def test_filter_with_high_debt_fails(self):
        """Test that high debt-to-equity fails the filter."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            roe=Decimal("0.10"),
            debt_to_equity=Decimal("3.0"),  # Above max_debt_to_equity of 2.0
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert any("Debt-to-equity" in reason for reason in result.reasons)

    def test_filter_with_low_current_ratio_fails(self):
        """Test that low current ratio fails the filter."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            roe=Decimal("0.10"),
            current_ratio=Decimal("0.5"),  # Below min_current_ratio of 1.0
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert any("Current ratio" in reason for reason in result.reasons)

    def test_filter_with_negative_roe_fails_profitability(self):
        """Test that negative ROE fails profitability check."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            roe=Decimal("-0.05"),  # Negative
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert any("unprofitability" in reason for reason in result.reasons)

    def test_filter_with_missing_optional_metrics(self):
        """Test filter with only required metrics."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            roe=Decimal("0.15"),
        )

        result = filter.evaluate(metrics)

        # Should pass with only ROE
        assert result.passed is True
        assert result.score > Decimal("0")

    def test_filter_batch_processing(self):
        """Test filtering multiple instruments."""
        filter = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(
                symbol="RELIANCE",
                pe_ratio=Decimal("20"),
                pb_ratio=Decimal("2.0"),
                roe=Decimal("0.15"),
            ),
            FundamentalMetrics(
                symbol="TCS",
                pe_ratio=Decimal("30"),
                pb_ratio=Decimal("3.0"),
                roe=Decimal("0.05"),
            ),
            FundamentalMetrics(
                symbol="FAIL",
                roe=Decimal("0.01"),  # Too low
            ),
        ]

        results = filter.filter_batch(metrics_list)

        assert len(results) == 3
        passed_count = sum(1 for r in results if r.passed)
        assert passed_count == 2

    def test_get_passed_instruments(self):
        """Test getting only passed instruments."""
        filter = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(symbol="PASS1", roe=Decimal("0.15")),
            FundamentalMetrics(symbol="PASS2", roe=Decimal("0.10")),
            FundamentalMetrics(symbol="FAIL", roe=Decimal("0.01")),
        ]

        results = filter.filter_batch(metrics_list)
        passed = filter.get_passed(results)

        assert len(passed) == 2
        assert all(m.symbol.startswith("PASS") for m in passed)

    def test_pe_ratio_scoring(self):
        """Test P/E ratio scoring."""
        config = FundamentalFilterConfig(min_pe=Decimal("10"), max_pe=Decimal("30"))
        filter = FundamentalFilter(config)

        # Ideal P/E (middle of range)
        metrics_ideal = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("20"))
        result_ideal = filter.evaluate(metrics_ideal)
        assert result_ideal.score > Decimal("0.8")

        # Low P/E (near min)
        metrics_low = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("10"))
        result_low = filter.evaluate(metrics_low)
        assert result_low.score < result_ideal.score

        # High P/E (near max)
        metrics_high = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("30"))
        result_high = filter.evaluate(metrics_high)
        assert result_high.score < result_ideal.score

    def test_pb_ratio_scoring(self):
        """Test P/B ratio scoring."""
        config = FundamentalFilterConfig(min_pb=Decimal("1.0"), max_pb=Decimal("5.0"))
        filter = FundamentalFilter(config)

        metrics = FundamentalMetrics(symbol="TEST", pb_ratio=Decimal("2.0"))
        result = filter.evaluate(metrics)
        assert result.score > Decimal("0")

    def test_custom_configuration(self):
        """Test filter with custom configuration."""
        config = FundamentalFilterConfig(
            min_roe=Decimal("0.10"),
            max_debt_to_equity=Decimal("1.0"),
            require_profitability=False,
        )
        filter = FundamentalFilter(config)

        # Test with ROE below threshold - should fail
        metrics_fail = FundamentalMetrics(
            symbol="TEST",
            roe=Decimal("0.08"),  # Below 0.10
            debt_to_equity=Decimal("0.8"),
        )

        result_fail = filter.evaluate(metrics_fail)
        assert result_fail.passed is False

        # Test with ROE above threshold - should pass
        metrics_pass = FundamentalMetrics(
            symbol="TEST",
            roe=Decimal("0.12"),  # Above 0.10
            debt_to_equity=Decimal("0.8"),
        )

        result_pass = filter.evaluate(metrics_pass)
        assert result_pass.passed is True

    def test_score_normalization(self):
        """Test that scores are normalized to [0, 1]."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("2.0"),
            roe=Decimal("0.15"),
            debt_to_equity=Decimal("0.5"),
            current_ratio=Decimal("1.5"),
        )

        result = filter.evaluate(metrics)

        assert Decimal("0") <= result.score <= Decimal("1")

    def test_multiple_failure_reasons(self):
        """Test that multiple failures are captured."""
        filter = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="TEST",
            roe=Decimal("0.01"),  # Too low
            debt_to_equity=Decimal("5.0"),  # Too high
            current_ratio=Decimal("0.5"),  # Too low
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert len(result.reasons) >= 2

    def test_dividend_yield_scoring(self):
        """Test dividend yield scoring with threshold."""
        config = FundamentalFilterConfig(min_dividend_yield=Decimal("0.02"))
        filter = FundamentalFilter(config)

        # Above threshold
        metrics_high = FundamentalMetrics(
            symbol="TEST", roe=Decimal("0.15"), dividend_yield=Decimal("0.05")
        )
        result_high = filter.evaluate(metrics_high)
        assert result_high.passed is True

        # Below threshold
        metrics_low = FundamentalMetrics(
            symbol="TEST", roe=Decimal("0.15"), dividend_yield=Decimal("0.01")
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is False

    def test_earnings_growth_scoring(self):
        """Test earnings growth scoring."""
        config = FundamentalFilterConfig(min_earnings_growth=Decimal("0.05"))
        filter = FundamentalFilter(config)

        metrics = FundamentalMetrics(
            symbol="TEST", roe=Decimal("0.15"), earnings_growth=Decimal("0.15")
        )
        result = filter.evaluate(metrics)
        assert result.passed is True

    def test_market_cap_scoring(self):
        """Test market cap filtering."""
        config = FundamentalFilterConfig(
            min_market_cap=Decimal("100000"), max_market_cap=Decimal("10000000")
        )
        filter = FundamentalFilter(config)

        # Within range
        metrics_ok = FundamentalMetrics(
            symbol="TEST", roe=Decimal("0.15"), market_cap=Decimal("500000")
        )
        result_ok = filter.evaluate(metrics_ok)
        assert result_ok.passed is True

        # Below min
        metrics_low = FundamentalMetrics(
            symbol="TEST", roe=Decimal("0.15"), market_cap=Decimal("50000")
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is False
