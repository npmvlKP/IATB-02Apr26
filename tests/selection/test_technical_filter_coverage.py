"""
Comprehensive coverage tests for technical_filter.py.

Tests RSI/MACD/MA/BB filters, technical indicators evaluation.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.technical_filter import (
    TechnicalFilter,
    TechnicalFilterConfig,
    TechnicalMetrics,
)


class TestTechnicalFilterConfig:
    """Test configuration validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TechnicalFilterConfig()
        assert config.rsi_oversold == Decimal("30")
        assert config.rsi_overbought == Decimal("70")
        assert config.rsi_min == Decimal("20")
        assert config.rsi_max == Decimal("80")
        assert config.require_macd_bullish is False
        assert config.require_ma_bullish is False

    def test_invalid_rsi_range_raises_error(self):
        """Test that invalid RSI range raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_min must be less than rsi_max"):
            TechnicalFilterConfig(rsi_min=Decimal("70"), rsi_max=Decimal("30"))

    def test_invalid_rsi_oversold_raises_error(self):
        """Test that invalid RSI oversold raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_oversold must be >= rsi_min"):
            TechnicalFilterConfig(rsi_oversold=Decimal("10"), rsi_min=Decimal("20"))

    def test_invalid_rsi_overbought_raises_error(self):
        """Test that invalid RSI overbought raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_overbought must be <= rsi_max"):
            TechnicalFilterConfig(rsi_overbought=Decimal("90"), rsi_max=Decimal("80"))

    def test_negative_volume_ratio_raises_error(self):
        """Test that negative volume ratio raises ConfigError."""
        with pytest.raises(ConfigError, match="min_volume_ratio cannot be negative"):
            TechnicalFilterConfig(min_volume_ratio=Decimal("-0.5"))

    def test_invalid_bollinger_position_raises_error(self):
        """Test that invalid Bollinger position raises ConfigError."""
        with pytest.raises(
            ConfigError, match="min_bollinger_position must be in \\[0, 1\\]"
        ):
            TechnicalFilterConfig(min_bollinger_position=Decimal("1.5"))

        with pytest.raises(
            ConfigError, match="max_bollinger_position must be in \\[0, 1\\]"
        ):
            TechnicalFilterConfig(max_bollinger_position=Decimal("-0.5"))

    def test_invalid_bollinger_range_raises_error(self):
        """Test that invalid Bollinger range raises ConfigError."""
        with pytest.raises(
            ConfigError, match="min_bollinger_position cannot be greater"
        ):
            TechnicalFilterConfig(
                min_bollinger_position=Decimal("0.8"),
                max_bollinger_position=Decimal("0.2"),
            )

    def test_invalid_ma_period_raises_error(self):
        """Test that invalid MA period raises ConfigError."""
        with pytest.raises(
            ConfigError, match="ma_period_short must be less than ma_period_long"
        ):
            TechnicalFilterConfig(ma_period_short=50, ma_period_long=20)


class TestTechnicalFilter:
    """Test technical filter evaluation."""

    def test_filter_with_all_metrics_passing(self):
        """Test filter with all metrics passing."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="RELIANCE",
            rsi=Decimal("50"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            macd_histogram=Decimal("0.2"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            price=Decimal("120"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("1500000"),
            price_momentum=Decimal("0.02"),
            atr=Decimal("2"),
        )

        result = filter.evaluate(metrics)

        assert result.passed is True
        assert result.symbol == "RELIANCE"
        assert result.score > Decimal("0")
        assert len(result.reasons) == 0

    def test_filter_with_low_rsi_fails(self):
        """Test that low RSI fails the filter."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="RELIANCE",
            rsi=Decimal("10"),  # Below rsi_min of 20
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert any("RSI" in reason for reason in result.reasons)

    def test_filter_with_high_rsi_fails(self):
        """Test that high RSI fails the filter."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="RELIANCE",
            rsi=Decimal("90"),  # Above rsi_max of 80
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert any("RSI" in reason for reason in result.reasons)

    def test_filter_with_missing_optional_metrics(self):
        """Test filter with only required metrics."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="RELIANCE",
            rsi=Decimal("50"),
        )

        result = filter.evaluate(metrics)

        # Should pass with only RSI
        assert result.passed is True
        assert result.score > Decimal("0")

    def test_filter_batch_processing(self):
        """Test filtering multiple instruments."""
        filter = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(
                symbol="RELIANCE",
                rsi=Decimal("50"),
            ),
            TechnicalMetrics(
                symbol="TCS",
                rsi=Decimal("55"),
            ),
            TechnicalMetrics(
                symbol="FAIL",
                rsi=Decimal("10"),  # Too low
            ),
        ]

        results = filter.filter_batch(metrics_list)

        assert len(results) == 3
        passed_count = sum(1 for r in results if r.passed)
        assert passed_count == 2

    def test_get_passed_instruments(self):
        """Test getting only passed instruments."""
        filter = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(symbol="PASS1", rsi=Decimal("50")),
            TechnicalMetrics(symbol="PASS2", rsi=Decimal("55")),
            TechnicalMetrics(symbol="FAIL", rsi=Decimal("10")),
        ]

        results = filter.filter_batch(metrics_list)
        passed = filter.get_passed(results)

        assert len(passed) == 2
        assert all(m.symbol.startswith("PASS") for m in passed)

    def test_rsi_scoring(self):
        """Test RSI scoring with threshold."""
        config = TechnicalFilterConfig(rsi_min=Decimal("20"), rsi_max=Decimal("80"))
        filter = TechnicalFilter(config)

        # Optimal RSI (50)
        metrics_optimal = TechnicalMetrics(symbol="TEST", rsi=Decimal("50"))
        result_optimal = filter.evaluate(metrics_optimal)
        assert result_optimal.score > Decimal("0.5")

        # Near lower bound
        metrics_low = TechnicalMetrics(symbol="TEST", rsi=Decimal("25"))
        result_low = filter.evaluate(metrics_low)
        assert result_low.score < result_optimal.score

    def test_atr_scoring(self):
        """Test ATR volatility scoring."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filter = TechnicalFilter(config)

        # Low volatility
        metrics_low = TechnicalMetrics(
            symbol="TEST", price=Decimal("100"), atr=Decimal("1"), rsi=Decimal("50")
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is True

        # High volatility
        metrics_high = TechnicalMetrics(
            symbol="TEST", price=Decimal("100"), atr=Decimal("8"), rsi=Decimal("50")
        )
        result_high = filter.evaluate(metrics_high)
        assert result_high.passed is False

    def test_rsi_scoring_middle_range(self):
        """Test RSI scoring with optimal middle range."""
        config = TechnicalFilterConfig(rsi_min=Decimal("20"), rsi_max=Decimal("80"))
        filter = TechnicalFilter(config)

        # Optimal RSI (50)
        metrics_optimal = TechnicalMetrics(symbol="TEST", rsi=Decimal("50"))
        result_optimal = filter.evaluate(metrics_optimal)
        assert result_optimal.score > Decimal("0.8")

        # Near lower bound
        metrics_low = TechnicalMetrics(symbol="TEST", rsi=Decimal("25"))
        result_low = filter.evaluate(metrics_low)
        assert result_low.score < result_optimal.score

        # Near upper bound
        metrics_high = TechnicalMetrics(symbol="TEST", rsi=Decimal("75"))
        result_high = filter.evaluate(metrics_high)
        assert result_high.score < result_optimal.score

    def test_macd_signal_scoring(self):
        """Test MACD signal scoring."""
        filter = TechnicalFilter()

        # Positive MACD
        metrics_positive = TechnicalMetrics(
            symbol="TEST",
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
        )
        result_positive = filter.evaluate(metrics_positive)
        assert result_positive.passed is True

        # Negative MACD
        metrics_negative = TechnicalMetrics(
            symbol="TEST",
            macd=Decimal("-0.5"),
            macd_signal=Decimal("-0.3"),
        )
        result_negative = filter.evaluate(metrics_negative)
        assert result_negative.passed is True  # MACD is optional

    def test_macd_bullish_requirement(self):
        """Test MACD bullish requirement."""
        config = TechnicalFilterConfig(require_macd_bullish=True)
        filter = TechnicalFilter(config)

        # Bullish MACD (above signal)
        metrics_bullish = TechnicalMetrics(
            symbol="TEST",
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
        )
        result_bullish = filter.evaluate(metrics_bullish)
        assert result_bullish.passed is True

        # Bearish MACD (below signal)
        metrics_bearish = TechnicalMetrics(
            symbol="TEST",
            macd=Decimal("0.3"),
            macd_signal=Decimal("0.5"),
        )
        result_bearish = filter.evaluate(metrics_bearish)
        assert result_bearish.passed is False

    def test_bollinger_position_scoring(self):
        """Test Bollinger band position scoring."""
        filter = TechnicalFilter()

        # Near middle
        metrics_middle = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("110"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
        )
        result_middle = filter.evaluate(metrics_middle)
        assert result_middle.score > Decimal("0")

        # Near upper band (but within bounds)
        metrics_upper = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("120"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
        )
        result_upper = filter.evaluate(metrics_upper)
        assert result_upper.score > Decimal("0")

    def test_bollinger_out_of_range_fails(self):
        """Test that price outside Bollinger bands fails."""
        config = TechnicalFilterConfig(
            min_bollinger_position=Decimal("0.2"), max_bollinger_position=Decimal("0.8")
        )
        filter = TechnicalFilter(config)

        # Below lower band
        metrics_low = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("85"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is False

    def test_volume_ratio_scoring(self):
        """Test volume ratio scoring."""
        config = TechnicalFilterConfig(min_volume_ratio=Decimal("1.2"))
        filter = TechnicalFilter(config)

        # High volume
        metrics_high = TechnicalMetrics(
            symbol="TEST",
            volume_current=Decimal("2000000"),
            volume_avg=Decimal("1000000"),
        )
        result_high = filter.evaluate(metrics_high)
        assert result_high.passed is True

        # Low volume
        metrics_low = TechnicalMetrics(
            symbol="TEST",
            volume_current=Decimal("800000"),
            volume_avg=Decimal("1000000"),
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is False

    def test_ma_alignment_scoring(self):
        """Test moving average alignment scoring."""
        filter = TechnicalFilter()

        # Golden cross (above both)
        metrics_golden = TechnicalMetrics(
            symbol="TEST",
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
        )
        result_golden = filter.evaluate(metrics_golden)
        assert result_golden.score > Decimal("0")

        # Death cross (below both)
        metrics_death = TechnicalMetrics(
            symbol="TEST",
            ma_short=Decimal("90"),
            ma_long=Decimal("100"),
        )
        result_death = filter.evaluate(metrics_death)
        # Should still pass but with lower score
        assert result_death.passed is True

    def test_ma_bullish_requirement(self):
        """Test MA bullish requirement."""
        config = TechnicalFilterConfig(require_ma_bullish=True)
        filter = TechnicalFilter(config)

        # Bullish (short above long)
        metrics_bullish = TechnicalMetrics(
            symbol="TEST",
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
        )
        result_bullish = filter.evaluate(metrics_bullish)
        assert result_bullish.passed is True

        # Bearish (short below long)
        metrics_bearish = TechnicalMetrics(
            symbol="TEST",
            ma_short=Decimal("90"),
            ma_long=Decimal("100"),
        )
        result_bearish = filter.evaluate(metrics_bearish)
        assert result_bearish.passed is False

    def test_custom_configuration(self):
        """Test filter with custom configuration."""
        config = TechnicalFilterConfig(
            rsi_min=Decimal("40"),
            rsi_max=Decimal("60"),
            rsi_oversold=Decimal("45"),
            rsi_overbought=Decimal("55"),
        )
        filter = TechnicalFilter(config)

        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("35"),  # Below custom rsi_min
        )

        result = filter.evaluate(metrics)
        assert result.passed is False

    def test_score_normalization(self):
        """Test that scores are normalized to [0, 1]."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("50"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            macd_histogram=Decimal("0.2"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            price=Decimal("120"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("1500000"),
            price_momentum=Decimal("0.02"),
        )

        result = filter.evaluate(metrics)

        assert Decimal("0") <= result.score <= Decimal("1")

    def test_multiple_failure_reasons(self):
        """Test that multiple failures are captured."""
        filter = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("10"),  # Too low
            volume_current=Decimal("500000"),
            volume_avg=Decimal("1000000"),
        )

        result = filter.evaluate(metrics)

        assert result.passed is False
        assert len(result.reasons) >= 1

    def test_combined_scoring(self):
        """Test that multiple metrics contribute to overall score."""
        filter = TechnicalFilter()

        # Strong across all metrics
        metrics_strong = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("50"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            macd_histogram=Decimal("0.2"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            price=Decimal("120"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("2000000"),
            price_momentum=Decimal("0.05"),
        )
        result_strong = filter.evaluate(metrics_strong)

        # Weak across all metrics (multiple low scores)
        metrics_weak = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("50"),
            macd=Decimal("-0.5"),
            macd_signal=Decimal("-0.3"),
            macd_histogram=Decimal("-0.2"),
            ma_short=Decimal("90"),
            ma_long=Decimal("100"),
            price=Decimal("100"),
            bollinger_upper=Decimal("130"),
            bollinger_lower=Decimal("90"),
            bollinger_middle=Decimal("110"),
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("500000"),
        )
        result_weak = filter.evaluate(metrics_weak)

        assert result_strong.score > result_weak.score

    def test_price_momentum_scoring(self):
        """Test price momentum scoring."""
        config = TechnicalFilterConfig(min_price_momentum=Decimal("0.03"))
        filter = TechnicalFilter(config)

        # Above threshold
        metrics_high = TechnicalMetrics(
            symbol="TEST",
            price_momentum=Decimal("0.05"),
        )
        result_high = filter.evaluate(metrics_high)
        assert result_high.passed is True

        # Below threshold
        metrics_low = TechnicalMetrics(
            symbol="TEST",
            price_momentum=Decimal("0.01"),
        )
        result_low = filter.evaluate(metrics_low)
        assert result_low.passed is False

    def test_trend_alignment(self):
        """Test trend alignment requirement."""
        config = TechnicalFilterConfig(require_trend_alignment=True)
        filter = TechnicalFilter(config)

        # Aligned (all bullish)
        metrics_aligned = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("60"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            price=Decimal("120"),
            bollinger_middle=Decimal("110"),
        )
        result_aligned = filter.evaluate(metrics_aligned)
        assert result_aligned.passed is True

        # Not aligned (bearish)
        metrics_not_aligned = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("30"),
            ma_short=Decimal("90"),
            ma_long=Decimal("100"),
            macd=Decimal("-0.5"),
            macd_signal=Decimal("-0.3"),
            price=Decimal("100"),
            bollinger_middle=Decimal("110"),
        )
        result_not_aligned = filter.evaluate(metrics_not_aligned)
        assert result_not_aligned.passed is False
