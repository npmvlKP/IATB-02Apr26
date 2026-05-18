"""
Comprehensive coverage tests for fundamental_filter.py.

Tests PE/PB/ROE filters, balance sheet metrics, growth metrics, and error paths.
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
    """Test FundamentalFilterConfig validation."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = FundamentalFilterConfig()
        assert config.min_roe == Decimal("0.05")
        assert config.max_debt_to_equity == Decimal("2.0")
        assert config.min_current_ratio == Decimal("1.0")
        assert config.require_profitability is True

    def test_invalid_pe_range(self) -> None:
        """Test raises ConfigError when min_pe > max_pe."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(min_pe=Decimal("30"), max_pe=Decimal("20"))
        assert "min_pe cannot be greater than max_pe" in str(exc_info.value)

    def test_invalid_pb_range(self) -> None:
        """Test raises ConfigError when min_pb > max_pb."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(min_pb=Decimal("5"), max_pb=Decimal("3"))
        assert "min_pb cannot be greater than max_pb" in str(exc_info.value)

    def test_invalid_market_cap_range(self) -> None:
        """Test raises ConfigError when min_market_cap > max_market_cap."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(
                min_market_cap=Decimal("10000"), max_market_cap=Decimal("1000")
            )
        assert "min_market_cap cannot be greater than max_market_cap" in str(
            exc_info.value
        )

    def test_negative_min_roe(self) -> None:
        """Test raises ConfigError when min_roe is negative."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(min_roe=Decimal("-0.05"))
        assert "min_roe cannot be negative" in str(exc_info.value)

    def test_negative_max_debt_to_equity(self) -> None:
        """Test raises ConfigError when max_debt_to_equity is negative."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(max_debt_to_equity=Decimal("-1.0"))
        assert "max_debt_to_equity cannot be negative" in str(exc_info.value)

    def test_negative_min_current_ratio(self) -> None:
        """Test raises ConfigError when min_current_ratio is negative."""
        with pytest.raises(ConfigError) as exc_info:
            FundamentalFilterConfig(min_current_ratio=Decimal("-0.5"))
        assert "min_current_ratio cannot be negative" in str(exc_info.value)


class TestFundamentalFilter:
    """Test FundamentalFilter evaluation."""

    def test_evaluate_perfect_metrics(self) -> None:
        """Test instrument with perfect fundamental metrics."""
        config = FundamentalFilterConfig()
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="RELIANCE",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("2.5"),
            roe=Decimal("0.20"),
            debt_to_equity=Decimal("0.5"),
            current_ratio=Decimal("2.0"),
            dividend_yield=Decimal("0.02"),
            earnings_growth=Decimal("0.15"),
            market_cap=Decimal("1000000000000"),
            revenue_growth=Decimal("0.10"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.5")
        assert result.symbol == "RELIANCE"

    def test_evaluate_low_roe(self) -> None:
        """Test instrument with ROE below minimum."""
        config = FundamentalFilterConfig(min_roe=Decimal("0.10"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            roe=Decimal("0.05"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "ROE" in " ".join(result.reasons)

    def test_evaluate_high_debt_to_equity(self) -> None:
        """Test instrument with high debt-to-equity."""
        config = FundamentalFilterConfig(max_debt_to_equity=Decimal("2.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            debt_to_equity=Decimal("3.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Debt-to-equity" in " ".join(result.reasons)

    def test_evaluate_low_current_ratio(self) -> None:
        """Test instrument with low current ratio."""
        config = FundamentalFilterConfig(min_current_ratio=Decimal("1.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            current_ratio=Decimal("0.8"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Current ratio" in " ".join(result.reasons)

    def test_evaluate_pe_out_of_range(self) -> None:
        """Test instrument with P/E outside range."""
        config = FundamentalFilterConfig(min_pe=Decimal("10"), max_pe=Decimal("30"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            pe_ratio=Decimal("40"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "P/E ratio" in " ".join(result.reasons)

    def test_evaluate_pb_out_of_range(self) -> None:
        """Test instrument with P/B outside range."""
        config = FundamentalFilterConfig(min_pb=Decimal("1.0"), max_pb=Decimal("5.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            pb_ratio=Decimal("6.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "P/B ratio" in " ".join(result.reasons)

    def test_evaluate_with_optional_dividend_yield(self) -> None:
        """Test evaluation with dividend yield filter."""
        config = FundamentalFilterConfig(min_dividend_yield=Decimal("0.01"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            dividend_yield=Decimal("0.015"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_low_dividend_yield(self) -> None:
        """Test instrument with dividend yield below minimum."""
        config = FundamentalFilterConfig(min_dividend_yield=Decimal("0.02"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            dividend_yield=Decimal("0.01"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Dividend yield" in " ".join(result.reasons)

    def test_evaluate_with_optional_earnings_growth(self) -> None:
        """Test evaluation with earnings growth filter."""
        config = FundamentalFilterConfig(min_earnings_growth=Decimal("0.10"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            earnings_growth=Decimal("0.15"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_with_market_cap_filter(self) -> None:
        """Test evaluation with market cap filter."""
        config = FundamentalFilterConfig(
            min_market_cap=Decimal("500000000000"),
            max_market_cap=Decimal("2000000000000"),
        )
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            market_cap=Decimal("1000000000000"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_market_cap_below_minimum(self) -> None:
        """Test instrument with market cap below minimum."""
        config = FundamentalFilterConfig(min_market_cap=Decimal("1000000000000"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            market_cap=Decimal("500000000000"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Market cap" in " ".join(result.reasons)

    def test_evaluate_profitability_requirement(self) -> None:
        """Test profitability requirement when enabled."""
        config = FundamentalFilterConfig(require_profitability=True)
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            roe=Decimal("-0.05"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "unprofitability" in " ".join(result.reasons)

    def test_evaluate_profitability_disabled(self) -> None:
        """Test profitability check when disabled - ROE below min still fails."""
        config = FundamentalFilterConfig(require_profitability=False)
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            roe=Decimal("0.15"),  # Above min_roe threshold
        )

        result = filter_obj.evaluate(metrics)
        # Should pass since ROE is above minimum and profitability check is disabled
        assert result.passed is True

    def test_evaluate_none_optional_metrics(self) -> None:
        """Test evaluation with None values for optional metrics."""
        config = FundamentalFilterConfig()
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            roe=Decimal("0.15"),
            debt_to_equity=Decimal("1.0"),
            current_ratio=Decimal("1.5"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_filter_batch(self, caplog) -> None:
        """Test batch filtering."""
        config = FundamentalFilterConfig()
        filter_obj = FundamentalFilter(config)
        metrics_list = [
            FundamentalMetrics(
                symbol=f"STOCK{i}",
                roe=Decimal("0.15") if i % 2 == 0 else Decimal("0.03"),
            )
            for i in range(5)
        ]

        results = filter_obj.filter_batch(metrics_list)
        assert len(results) == 5
        passed_count = sum(1 for r in results if r.passed)
        assert passed_count == 3  # 0, 2, 4 pass
        assert "Fundamental filter: 3/5 passed" in caplog.text

    def test_get_passed(self) -> None:
        """Test getting passed instruments."""
        config = FundamentalFilterConfig()
        filter_obj = FundamentalFilter(config)
        metrics_list = [
            FundamentalMetrics(
                symbol=f"STOCK{i}", roe=Decimal("0.15") if i < 3 else Decimal("0.03")
            )
            for i in range(5)
        ]

        results = filter_obj.filter_batch(metrics_list)
        passed = filter_obj.get_passed(results)
        assert len(passed) == 3
        assert passed[0].symbol == "STOCK0"

    def test_pe_scoring_with_range(self) -> None:
        """Test P/E scoring within range."""
        config = FundamentalFilterConfig(min_pe=Decimal("15"), max_pe=Decimal("25"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            pe_ratio=Decimal("20"),  # Ideal
        )

        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.8")

    def test_pb_scoring_with_range(self) -> None:
        """Test P/B scoring within range."""
        config = FundamentalFilterConfig(min_pb=Decimal("2"), max_pb=Decimal("4"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            pb_ratio=Decimal("2.5"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.5")

    def test_roe_scoring(self) -> None:
        """Test ROE scoring."""
        config = FundamentalFilterConfig(min_roe=Decimal("0.05"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            roe=Decimal("0.15"),
        )

        result = filter_obj.evaluate(metrics)
        # Score should be min(1, 0.15 / 0.10) = 1.0
        assert result.score > Decimal("0")

    def test_debt_to_equity_scoring(self) -> None:
        """Test debt-to-equity scoring."""
        config = FundamentalFilterConfig(max_debt_to_equity=Decimal("2.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            debt_to_equity=Decimal("0.5"),
        )

        result = filter_obj.evaluate(metrics)
        # Score should be max(0, 1 - 0.5 / 3.0) = 0.833
        assert result.score > Decimal("0.5")

    def test_current_ratio_scoring(self) -> None:
        """Test current ratio scoring."""
        config = FundamentalFilterConfig(min_current_ratio=Decimal("1.0"))
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            current_ratio=Decimal("2.0"),
        )

        result = filter_obj.evaluate(metrics)
        # Score should be min(1, 2.0 / 2.0) = 1.0
        assert result.score > Decimal("0")

    def test_market_cap_scoring(self) -> None:
        """Test market cap scoring."""
        config = FundamentalFilterConfig(
            min_market_cap=Decimal("1000"), max_market_cap=Decimal("2000")
        )
        filter_obj = FundamentalFilter(config)
        metrics = FundamentalMetrics(
            symbol="STOCK1",
            market_cap=Decimal("1500"),  # Ideal
        )

        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.8")
