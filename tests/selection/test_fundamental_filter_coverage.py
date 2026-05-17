"""Tests for selection/fundamental_filter.py — PE/PB/ROE filters."""

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
    def test_default_config(self) -> None:
        cfg = FundamentalFilterConfig()
        assert cfg.min_roe == Decimal("0.05")
        assert cfg.max_debt_to_equity == Decimal("2.0")
        assert cfg.min_current_ratio == Decimal("1.0")

    def test_min_pe_gt_max_pe_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_pe cannot be greater than max_pe"):
            FundamentalFilterConfig(min_pe=Decimal("50"), max_pe=Decimal("10"))

    def test_min_pb_gt_max_pb_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_pb cannot be greater than max_pb"):
            FundamentalFilterConfig(min_pb=Decimal("10"), max_pb=Decimal("2"))

    def test_min_market_cap_gt_max_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_market_cap"):
            FundamentalFilterConfig(
                min_market_cap=Decimal("1e9"), max_market_cap=Decimal("1e8")
            )

    def test_negative_min_roe_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_roe cannot be negative"):
            FundamentalFilterConfig(min_roe=Decimal("-0.1"))

    def test_negative_max_de_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_debt_to_equity cannot be negative"):
            FundamentalFilterConfig(max_debt_to_equity=Decimal("-1"))

    def test_negative_min_current_ratio_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_current_ratio cannot be negative"):
            FundamentalFilterConfig(min_current_ratio=Decimal("-0.5"))


class TestFundamentalMetrics:
    def test_default_metrics(self) -> None:
        m = FundamentalMetrics(symbol="TEST")
        assert m.symbol == "TEST"
        assert m.pe_ratio is None
        assert m.pb_ratio is None


class TestFundamentalFilter:
    def test_all_metrics_pass(self) -> None:
        cfg = FundamentalFilterConfig(
            min_pe=Decimal("5"),
            max_pe=Decimal("50"),
            min_pb=Decimal("0.5"),
            max_pb=Decimal("5"),
            min_roe=Decimal("0.05"),
        )
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(
            symbol="PASS",
            pe_ratio=Decimal("20"),
            pb_ratio=Decimal("2"),
            roe=Decimal("0.15"),
            debt_to_equity=Decimal("0.5"),
            current_ratio=Decimal("1.5"),
        )
        result = filt.evaluate(m)
        assert isinstance(result, FilterResult)
        assert result.passed is True
        assert result.symbol == "PASS"

    def test_pe_above_max_fails(self) -> None:
        filt = FundamentalFilter(FundamentalFilterConfig(max_pe=Decimal("30")))
        m = FundamentalMetrics(symbol="HIPE", pe_ratio=Decimal("50"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_pe_below_min_fails(self) -> None:
        filt = FundamentalFilter(FundamentalFilterConfig(min_pe=Decimal("10")))
        m = FundamentalMetrics(symbol="LOPE", pe_ratio=Decimal("5"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_roe_below_min_fails(self) -> None:
        filt = FundamentalFilter()
        m = FundamentalMetrics(symbol="LOROE", roe=Decimal("0.01"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_high_debt_to_equity_fails(self) -> None:
        filt = FundamentalFilter()
        m = FundamentalMetrics(symbol="HIDE", debt_to_equity=Decimal("3.0"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_low_current_ratio_fails(self) -> None:
        filt = FundamentalFilter()
        m = FundamentalMetrics(symbol="LOCR", current_ratio=Decimal("0.5"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_negative_roe_profitability_fails(self) -> None:
        filt = FundamentalFilter(FundamentalFilterConfig(require_profitability=True))
        m = FundamentalMetrics(symbol="NEG", roe=Decimal("-0.1"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_profitability_disabled_passes(self) -> None:
        cfg = FundamentalFilterConfig(require_profitability=False)
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="NOPROF", roe=Decimal("0.10"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_none_metrics_skip(self) -> None:
        filt = FundamentalFilter(FundamentalFilterConfig(require_profitability=False))
        m = FundamentalMetrics(symbol="NONE")
        result = filt.evaluate(m)
        assert result.passed is True

    def test_filter_batch(self) -> None:
        filt = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(symbol="A", roe=Decimal("0.15")),
            FundamentalMetrics(symbol="B", roe=Decimal("0.01")),
        ]
        results = filt.filter_batch(metrics_list)
        assert len(results) == 2

    def test_get_passed(self) -> None:
        filt = FundamentalFilter()
        metrics_list = [
            FundamentalMetrics(symbol="A", roe=Decimal("0.15")),
            FundamentalMetrics(symbol="B", roe=Decimal("0.01")),
        ]
        results = filt.filter_batch(metrics_list)
        passed = filt.get_passed(results)
        assert all(m.symbol == "A" for m in passed)

    def test_dividend_yield_pass(self) -> None:
        cfg = FundamentalFilterConfig(min_dividend_yield=Decimal("0.02"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="DIV", dividend_yield=Decimal("0.03"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_dividend_yield_fail(self) -> None:
        cfg = FundamentalFilterConfig(min_dividend_yield=Decimal("0.05"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="DIVL", dividend_yield=Decimal("0.01"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_earnings_growth_pass(self) -> None:
        cfg = FundamentalFilterConfig(min_earnings_growth=Decimal("0.1"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="GRW", earnings_growth=Decimal("0.2"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_earnings_growth_fail(self) -> None:
        cfg = FundamentalFilterConfig(min_earnings_growth=Decimal("0.2"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="GRWL", earnings_growth=Decimal("0.05"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_market_cap_pass(self) -> None:
        cfg = FundamentalFilterConfig(
            min_market_cap=Decimal("1e9"), max_market_cap=Decimal("1e11")
        )
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="CAP", market_cap=Decimal("5e10"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_market_cap_below_min_fails(self) -> None:
        cfg = FundamentalFilterConfig(min_market_cap=Decimal("1e10"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="SMCAP", market_cap=Decimal("1e8"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_revenue_growth(self) -> None:
        cfg = FundamentalFilterConfig(min_revenue_growth=Decimal("0.1"))
        filt = FundamentalFilter(cfg)
        m = FundamentalMetrics(symbol="RGR", revenue_growth=Decimal("0.2"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_score_is_decimal(self) -> None:
        filt = FundamentalFilter()
        m = FundamentalMetrics(symbol="S", roe=Decimal("0.15"))
        result = filt.evaluate(m)
        assert isinstance(result.score, Decimal)

    def test_reasons_populated_on_fail(self) -> None:
        filt = FundamentalFilter()
        m = FundamentalMetrics(symbol="R", roe=Decimal("-0.5"))
        result = filt.evaluate(m)
        assert result.passed is False
        assert len(result.reasons) > 0
