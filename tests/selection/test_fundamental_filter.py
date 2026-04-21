"""
Tests for fundamental_filter module.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.fundamental_filter import (
    FilterResult,
    FundamentalFilter,
    FundamentalFilterConfig,
    FundamentalMetrics,
)


class TestFundamentalFilterConfig:
    """Test FundamentalFilterConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = FundamentalFilterConfig()
        assert config.min_roe == Decimal("0.05")
        assert config.max_debt_to_equity == Decimal("2.0")
        assert config.min_current_ratio == Decimal("1.0")
        assert config.require_profitability is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = FundamentalFilterConfig(
            min_pe=Decimal("10"),
            max_pe=Decimal("50"),
            min_roe=Decimal("0.1"),
            require_profitability=False,
        )
        assert config.min_pe == Decimal("10")
        assert config.max_pe == Decimal("50")
        assert config.min_roe == Decimal("0.1")
        assert config.require_profitability is False

    def test_min_pe_greater_than_max_pe_raises_error(self) -> None:
        """Test that min_pe > max_pe raises ConfigError."""
        with pytest.raises(ConfigError, match="min_pe cannot be greater than max_pe"):
            FundamentalFilterConfig(min_pe=Decimal("50"), max_pe=Decimal("10"))

    def test_min_pb_greater_than_max_pb_raises_error(self) -> None:
        """Test that min_pb > max_pb raises ConfigError."""
        with pytest.raises(ConfigError, match="min_pb cannot be greater than max_pb"):
            FundamentalFilterConfig(min_pb=Decimal("5"), max_pb=Decimal("2"))

    def test_negative_min_roe_raises_error(self) -> None:
        """Test that negative min_roe raises ConfigError."""
        with pytest.raises(ConfigError, match="min_roe cannot be negative"):
            FundamentalFilterConfig(min_roe=Decimal("-0.1"))

    def test_negative_max_debt_to_equity_raises_error(self) -> None:
        """Test that negative max_debt_to_equity raises ConfigError."""
        with pytest.raises(ConfigError, match="max_debt_to_equity cannot be negative"):
            FundamentalFilterConfig(max_debt_to_equity=Decimal("-1"))


class TestFundamentalFilter:
    """Test FundamentalFilter class."""

    def test_filter_with_passing_metrics(self) -> None:
        """Test filtering with metrics that pass all criteria."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("15"),
            pb_ratio=Decimal("2"),
            roe=Decimal("0.15"),
            debt_to_equity=Decimal("0.5"),
            current_ratio=Decimal("1.5"),
            dividend_yield=Decimal("0.02"),
            earnings_growth=Decimal("0.1"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.score <= Decimal("1")
        assert len(result.reasons) == 0

    def test_filter_with_failing_pe_ratio(self) -> None:
        """Test filtering with failing P/E ratio."""
        config = FundamentalFilterConfig(min_pe=Decimal("10"), max_pe=Decimal("30"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("50"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert len(result.reasons) > 0
        assert "P/E ratio" in result.reasons[0]

    def test_filter_with_failing_roe(self) -> None:
        """Test filtering with failing ROE."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", roe=Decimal("0.02"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert len(result.reasons) > 0
        assert "ROE" in result.reasons[0]

    def test_filter_with_failing_debt_to_equity(self) -> None:
        """Test filtering with failing debt-to-equity."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", debt_to_equity=Decimal("3.0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert len(result.reasons) > 0
        assert "Debt-to-equity" in result.reasons[0]

    def test_filter_with_negative_roe(self) -> None:
        """Test filtering with negative ROE when profitability required."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", roe=Decimal("-0.05"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        # Negative ROE fails the min_roe check first
        assert "ROE" in result.reasons[0]

    def test_filter_with_partial_metrics(self) -> None:
        """Test filtering with only some metrics provided."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("20"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_filter_with_no_metrics(self) -> None:
        """Test filtering with no metrics."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST")
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        # When only profitability check runs and ROE is None, it passes with score=1
        assert result.score == Decimal("1")

    def test_filter_batch_empty(self) -> None:
        """Test batch filtering with empty list."""
        filter_obj = FundamentalFilter()
        results = filter_obj.filter_batch([])
        assert results == []

    def test_filter_batch_multiple_instruments(self) -> None:
        """Test batch filtering with multiple instruments."""
        filter_obj = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(
                symbol=f"TEST{i}",
                pe_ratio=Decimal(str(10 + i * 5)),
                roe=Decimal(str(0.1 + i * 0.05)),
            )
            for i in range(3)
        ]
        results = filter_obj.filter_batch(metrics_list)
        assert len(results) == 3
        assert all(isinstance(r, FilterResult) for r in results)

    def test_get_passed(self) -> None:
        """Test getting passed instruments."""
        filter_obj = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(symbol="PASS", pe_ratio=Decimal("15"), roe=Decimal("0.1")),
            FundamentalMetrics(symbol="FAIL", pe_ratio=Decimal("50"), roe=Decimal("0.02")),
        ]
        results = filter_obj.filter_batch(metrics_list)
        passed = filter_obj.get_passed(results)
        assert len(passed) == 1
        assert passed[0].symbol == "PASS"

    def test_pe_scoring_ideal_value(self) -> None:
        """Test that ideal P/E gets higher score."""
        config = FundamentalFilterConfig(min_pe=Decimal("10"), max_pe=Decimal("30"))
        filter_obj = FundamentalFilter(config)
        metrics_ideal = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("20"))
        metrics_edge = FundamentalMetrics(symbol="TEST2", pe_ratio=Decimal("10"))
        result_ideal = filter_obj.evaluate(metrics_ideal)
        result_edge = filter_obj.evaluate(metrics_edge)
        assert result_ideal.score > result_edge.score

    def test_pb_scoring(self) -> None:
        """Test P/B ratio scoring."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", pb_ratio=Decimal("2"))
        result = filter_obj.evaluate(metrics)
        assert Decimal("0") <= result.score <= Decimal("1")

    def test_current_ratio_scoring(self) -> None:
        """Test current ratio scoring."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", current_ratio=Decimal("2.0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.5")

    def test_dividend_yield_scoring(self) -> None:
        """Test dividend yield scoring."""
        config = FundamentalFilterConfig(min_dividend_yield=Decimal("0.01"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", dividend_yield=Decimal("0.03"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_earnings_growth_scoring(self) -> None:
        """Test earnings growth scoring."""
        config = FundamentalFilterConfig(min_earnings_growth=Decimal("0.05"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", earnings_growth=Decimal("0.15"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_market_cap_scoring(self) -> None:
        """Test market cap scoring."""
        config = FundamentalFilterConfig(
            min_market_cap=Decimal("1000"), max_market_cap=Decimal("10000")
        )
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", market_cap=Decimal("5000"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_market_cap_below_minimum(self) -> None:
        """Test market cap below minimum fails."""
        config = FundamentalFilterConfig(min_market_cap=Decimal("10000"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", market_cap=Decimal("5000"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_market_cap_above_maximum(self) -> None:
        """Test market cap above maximum fails."""
        config = FundamentalFilterConfig(max_market_cap=Decimal("1000"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", market_cap=Decimal("5000"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_revenue_growth_scoring(self) -> None:
        """Test revenue growth scoring."""
        config = FundamentalFilterConfig(min_revenue_growth=Decimal("0.05"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", revenue_growth=Decimal("0.1"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_multiple_failure_reasons(self) -> None:
        """Test that multiple failures return all reasons."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("200"),
            roe=Decimal("0.01"),
            debt_to_equity=Decimal("5.0"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert len(result.reasons) >= 2

    def test_require_profitability_false_with_positive_roe(self) -> None:
        """Test with require_profitability=False and positive ROE passes."""
        # require_profitability=False disables the negative ROE check
        # But min_roe still applies
        config = FundamentalFilterConfig(require_profitability=False, min_roe=Decimal("0.01"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", roe=Decimal("0.02"))
        result = filter_obj.evaluate(metrics)
        # This should pass because ROE is above min_roe
        assert result.passed is True

    def test_very_low_pe_ratio(self) -> None:
        """Test very low P/E ratio."""
        config = FundamentalFilterConfig(min_pe=Decimal("10"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("3"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_very_high_debt_to_equity(self) -> None:
        """Test very high debt-to-equity ratio."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", debt_to_equity=Decimal("10.0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        # Score is exactly 0.5 when only debt-to-equity check fails
        assert result.score == Decimal("0.5")

    def test_very_high_current_ratio(self) -> None:
        """Test very high current ratio."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", current_ratio=Decimal("10.0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.5")

    def test_dividend_yield_below_minimum(self) -> None:
        """Test dividend yield below minimum."""
        config = FundamentalFilterConfig(min_dividend_yield=Decimal("0.03"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", dividend_yield=Decimal("0.01"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_earnings_growth_below_minimum(self) -> None:
        """Test earnings growth below minimum."""
        config = FundamentalFilterConfig(min_earnings_growth=Decimal("0.1"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", earnings_growth=Decimal("0.05"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_negative_earnings_growth(self) -> None:
        """Test negative earnings growth."""
        config = FundamentalFilterConfig(min_earnings_growth=Decimal("0.05"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", earnings_growth=Decimal("-0.1"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False

    def test_zero_debt_to_equity(self) -> None:
        """Test zero debt-to-equity ratio."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", debt_to_equity=Decimal("0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.8")

    def test_perfect_fundamentals(self) -> None:
        """Test with perfect fundamental metrics."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("15"),
            pb_ratio=Decimal("1.5"),
            roe=Decimal("0.2"),
            debt_to_equity=Decimal("0.3"),
            current_ratio=Decimal("2.0"),
            dividend_yield=Decimal("0.05"),
            earnings_growth=Decimal("0.15"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.7")

    def test_metrics_returned_in_result(self) -> None:
        """Test that metrics are returned in result."""
        filter_obj = FundamentalFilter()
        metrics = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("20"))
        result = filter_obj.evaluate(metrics)
        assert result.metrics == metrics

    def test_score_ranges_from_zero_to_one(self) -> None:
        """Test that scores always range from 0 to 1."""
        filter_obj = FundamentalFilter()
        for pe in [Decimal("5"), Decimal("15"), Decimal("50"), Decimal("100")]:
            metrics = FundamentalMetrics(symbol="TEST", pe_ratio=pe)
            result = filter_obj.evaluate(metrics)
            assert Decimal("0") <= result.score <= Decimal("1")

    def test_min_pe_not_set_when_max_pe_set_raises(self) -> None:
        """Test that ValueError is raised when max_pe is set but min_pe is not."""
        config = FundamentalFilterConfig(max_pe=Decimal("50"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", pe_ratio=Decimal("25"))
        with pytest.raises(ValueError, match="min_pe must be set when max_pe is set"):
            filter_obj.evaluate(metrics)

    def test_min_pb_not_set_when_max_pb_set_raises(self) -> None:
        """Test that ValueError is raised when max_pb is set but min_pb is not."""
        config = FundamentalFilterConfig(max_pb=Decimal("5"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", pb_ratio=Decimal("2.5"))
        with pytest.raises(ValueError, match="min_pb must be set when max_pb is set"):
            filter_obj.evaluate(metrics)

    def test_very_low_current_ratio(self) -> None:
        """Test filter with very low current ratio."""
        config = FundamentalFilterConfig(min_current_ratio=Decimal("2.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("2"),
            roe=Decimal("0.15"),
            current_ratio=Decimal("0.5"),
        )
        result = filter_obj.evaluate(metrics)
        assert not result.passed
        assert "Current ratio" in "; ".join(result.reasons)

    def test_very_high_pb_ratio(self) -> None:
        """Test filter with very high P/B ratio."""
        config = FundamentalFilterConfig(max_pb=Decimal("3"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("10"),
            roe=Decimal("0.15"),
        )
        result = filter_obj.evaluate(metrics)
        assert not result.passed
        assert "P/B ratio" in "; ".join(result.reasons)

    def test_negative_pe_ratio(self) -> None:
        """Test filter with negative P/E ratio (edge case)."""
        config = FundamentalFilterConfig(min_pe=Decimal("5"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("-10"),  # Negative P/E (possible for loss-making companies)
            pb_ratio=Decimal("2"),
            roe=Decimal("-0.05"),  # Negative ROE
        )
        result = filter_obj.evaluate(metrics)
        assert not result.passed

    def test_market_cap_with_only_min(self) -> None:
        """Test market cap filter with only minimum set."""
        config = FundamentalFilterConfig(min_market_cap=Decimal("1000"))
        filter_obj = FundamentalFilter(config)
        # Below minimum
        metrics_low = FundamentalMetrics(symbol="TEST_LOW", market_cap=Decimal("500"))
        result_low = filter_obj.evaluate(metrics_low)
        assert not result_low.passed
        assert "Market cap" in "; ".join(result_low.reasons)
        # Above minimum
        metrics_high = FundamentalMetrics(symbol="TEST_HIGH", market_cap=Decimal("2000"))
        result_high = filter_obj.evaluate(metrics_high)
        assert result_high.passed

    def test_profitability_with_none_roe(self) -> None:
        """Test profitability check when ROE is None."""
        config = FundamentalFilterConfig(require_profitability=True)
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(symbol="TEST", roe=None)
        result = filter_obj.evaluate(metrics)
        assert result.passed  # Should pass when ROE is None (no data available)

    def test_zero_pe_ratio(self) -> None:
        """Test filter with zero P/E ratio (edge case)."""
        config = FundamentalFilterConfig(min_pe=Decimal("5"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="TEST",
            pe_ratio=Decimal("0"),
            pb_ratio=Decimal("2"),
            roe=Decimal("0.15"),
        )
        result = filter_obj.evaluate(metrics)
        assert not result.passed
        assert "P/E ratio" in "; ".join(result.reasons)
