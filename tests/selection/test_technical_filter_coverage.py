"""Tests for selection/technical_filter.py — ADX/ATR/RSI filters."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.technical_filter import (
    TechnicalFilter,
    TechnicalFilterConfig,
    TechnicalMetrics,
)


class TestTechnicalFilterConfig:
    def test_default_config(self) -> None:
        cfg = TechnicalFilterConfig()
        assert cfg.rsi_oversold == Decimal("30")
        assert cfg.rsi_overbought == Decimal("70")

    def test_rsi_min_gt_max_raises(self) -> None:
        with pytest.raises(ConfigError, match="rsi_min must be less than rsi_max"):
            TechnicalFilterConfig(rsi_min=Decimal("80"), rsi_max=Decimal("20"))

    def test_rsi_oversold_lt_min_raises(self) -> None:
        with pytest.raises(ConfigError, match="rsi_oversold must be >= rsi_min"):
            TechnicalFilterConfig(rsi_oversold=Decimal("10"), rsi_min=Decimal("20"))

    def test_rsi_overbought_gt_max_raises(self) -> None:
        with pytest.raises(ConfigError, match="rsi_overbought must be <= rsi_max"):
            TechnicalFilterConfig(rsi_overbought=Decimal("90"), rsi_max=Decimal("80"))

    def test_bollinger_position_out_of_range(self) -> None:
        with pytest.raises(ConfigError, match="min_bollinger_position must be in"):
            TechnicalFilterConfig(min_bollinger_position=Decimal("-0.1"))

    def test_min_gt_max_bollinger_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="min_bollinger_position cannot be greater"
        ):
            TechnicalFilterConfig(
                min_bollinger_position=Decimal("0.9"),
                max_bollinger_position=Decimal("0.1"),
            )

    def test_negative_volume_ratio_raises(self) -> None:
        with pytest.raises(ConfigError, match="min_volume_ratio cannot be negative"):
            TechnicalFilterConfig(min_volume_ratio=Decimal("-0.5"))

    def test_ma_period_short_ge_long_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="ma_period_short must be less than ma_period_long"
        ):
            TechnicalFilterConfig(ma_period_short=50, ma_period_long=20)


class TestTechnicalFilter:
    def test_rsi_in_range_passes(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(symbol="RSI_OK", rsi=Decimal("50"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_rsi_out_of_range_fails(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(symbol="RSI_BAD", rsi=Decimal("10"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_rsi_oversold_zone(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(symbol="RSI_OS", rsi=Decimal("25"))
        result = filt.evaluate(m)
        assert result.passed is True
        assert result.score >= Decimal("0")

    def test_rsi_overbought_zone(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(symbol="RSI_OB", rsi=Decimal("75"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_macd_bullish_pass(self) -> None:
        cfg = TechnicalFilterConfig(require_macd_bullish=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="MACD_OK", macd=Decimal("1.0"), macd_signal=Decimal("0.5")
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_macd_bearish_with_require_fails(self) -> None:
        cfg = TechnicalFilterConfig(require_macd_bullish=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="MACD_BD", macd=Decimal("0.5"), macd_signal=Decimal("1.0")
        )
        result = filt.evaluate(m)
        assert result.passed is False

    def test_ma_bullish_cross(self) -> None:
        cfg = TechnicalFilterConfig(require_ma_bullish=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="MA_OK", ma_short=Decimal("105"), ma_long=Decimal("100")
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_ma_bearish_cross_fails(self) -> None:
        cfg = TechnicalFilterConfig(require_ma_bullish=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="MA_BD", ma_short=Decimal("95"), ma_long=Decimal("100")
        )
        result = filt.evaluate(m)
        assert result.passed is False

    def test_bollinger_in_range(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="BB_OK",
            price=Decimal("100"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("100"),
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_bollinger_below_lower_fails(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="BB_LO",
            price=Decimal("85"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("100"),
        )
        result = filt.evaluate(m)
        assert result.passed is False

    def test_volume_ratio_pass(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="VOL_OK", volume_avg=Decimal("100"), volume_current=Decimal("120")
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_volume_ratio_fail(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="VOL_LO", volume_avg=Decimal("100"), volume_current=Decimal("50")
        )
        result = filt.evaluate(m)
        assert result.passed is False

    def test_momentum_pass(self) -> None:
        cfg = TechnicalFilterConfig(min_price_momentum=Decimal("0.01"))
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(symbol="MOM_OK", price_momentum=Decimal("0.05"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_momentum_fail(self) -> None:
        cfg = TechnicalFilterConfig(min_price_momentum=Decimal("0.05"))
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(symbol="MOM_LO", price_momentum=Decimal("0.01"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_atr_ratio_pass(self) -> None:
        cfg = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(symbol="ATR_OK", atr=Decimal("3"), price=Decimal("100"))
        result = filt.evaluate(m)
        assert result.passed is True

    def test_atr_ratio_fail(self) -> None:
        cfg = TechnicalFilterConfig(max_atr_ratio=Decimal("0.02"))
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(symbol="ATR_HI", atr=Decimal("5"), price=Decimal("100"))
        result = filt.evaluate(m)
        assert result.passed is False

    def test_trend_alignment_bullish(self) -> None:
        cfg = TechnicalFilterConfig(require_trend_alignment=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="TREND_B",
            rsi=Decimal("60"),
            ma_short=Decimal("105"),
            ma_long=Decimal("100"),
            macd=Decimal("1"),
            macd_signal=Decimal("0.5"),
            price=Decimal("102"),
            bollinger_middle=Decimal("100"),
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_trend_alignment_bearish_fails(self) -> None:
        cfg = TechnicalFilterConfig(require_trend_alignment=True)
        filt = TechnicalFilter(cfg)
        m = TechnicalMetrics(
            symbol="TREND_S",
            rsi=Decimal("30"),
            ma_short=Decimal("95"),
            ma_long=Decimal("100"),
            macd=Decimal("-1"),
            macd_signal=Decimal("0.5"),
            price=Decimal("98"),
            bollinger_middle=Decimal("100"),
        )
        result = filt.evaluate(m)
        assert result.passed is False

    def test_filter_batch(self) -> None:
        filt = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(symbol="A", rsi=Decimal("50")),
            TechnicalMetrics(symbol="B", rsi=Decimal("5")),
        ]
        results = filt.filter_batch(metrics_list)
        assert len(results) == 2

    def test_get_passed(self) -> None:
        filt = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(symbol="A", rsi=Decimal("50")),
            TechnicalMetrics(symbol="B", rsi=Decimal("5")),
        ]
        results = filt.filter_batch(metrics_list)
        passed = filt.get_passed(results)
        assert len(passed) >= 1

    def test_zero_volume_avg_returns_default(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="ZERO_VOL", volume_avg=Decimal("0"), volume_current=Decimal("100")
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_zero_bollinger_width(self) -> None:
        filt = TechnicalFilter()
        m = TechnicalMetrics(
            symbol="ZERO_BB",
            price=Decimal("100"),
            bollinger_upper=Decimal("100"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("100"),
        )
        result = filt.evaluate(m)
        assert result.passed is True

    def test_no_metrics_all_pass(self) -> None:
        filt = TechnicalFilter(TechnicalFilterConfig(require_trend_alignment=False))
        m = TechnicalMetrics(symbol="EMPTY")
        result = filt.evaluate(m)
        assert result.passed is True
