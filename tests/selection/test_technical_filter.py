"""
Tests for technical_filter module.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.technical_filter import (
    FilterResult,
    TechnicalFilter,
    TechnicalFilterConfig,
    TechnicalMetrics,
)


class TestTechnicalFilterConfig:
    """Test TechnicalFilterConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = TechnicalFilterConfig()
        assert config.rsi_oversold == Decimal("30")
        assert config.rsi_overbought == Decimal("70")
        assert config.min_volume_ratio == Decimal("0.8")
        assert config.require_macd_bullish is False

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = TechnicalFilterConfig(
            rsi_oversold=Decimal("25"),
            rsi_overbought=Decimal("75"),
            min_volume_ratio=Decimal("1.0"),
            require_macd_bullish=True,
        )
        assert config.rsi_oversold == Decimal("25")
        assert config.rsi_overbought == Decimal("75")
        assert config.min_volume_ratio == Decimal("1.0")
        assert config.require_macd_bullish is True

    def test_rsi_min_greater_than_rsi_max_raises_error(self) -> None:
        """Test that rsi_min > rsi_max raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_min must be less than rsi_max"):
            TechnicalFilterConfig(rsi_min=Decimal("80"), rsi_max=Decimal("70"))

    def test_rsi_oversold_less_than_rsi_min_raises_error(self) -> None:
        """Test that rsi_oversold < rsi_min raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_oversold must be >= rsi_min"):
            TechnicalFilterConfig(rsi_min=Decimal("30"), rsi_oversold=Decimal("25"))

    def test_rsi_overbought_greater_than_rsi_max_raises_error(self) -> None:
        """Test that rsi_overbought > rsi_max raises ConfigError."""
        with pytest.raises(ConfigError, match="rsi_overbought must be <= rsi_max"):
            TechnicalFilterConfig(rsi_max=Decimal("70"), rsi_overbought=Decimal("75"))

    def test_invalid_bollinger_position_raises_error(self) -> None:
        """Test that invalid Bollinger position raises ConfigError."""
        with pytest.raises(ConfigError, match="min_bollinger_position must be in \\[0, 1\\]"):
            TechnicalFilterConfig(min_bollinger_position=Decimal("-0.1"))

    def test_min_bollinger_greater_than_max_raises_error(self) -> None:
        """Test that min > max Bollinger position raises ConfigError."""
        with pytest.raises(
            ConfigError,
            match="min_bollinger_position cannot be greater than max_bollinger_position",
        ):
            TechnicalFilterConfig(
                min_bollinger_position=Decimal("0.8"), max_bollinger_position=Decimal("0.2")
            )

    def test_negative_volume_ratio_raises_error(self) -> None:
        """Test that negative volume ratio raises ConfigError."""
        with pytest.raises(ConfigError, match="min_volume_ratio cannot be negative"):
            TechnicalFilterConfig(min_volume_ratio=Decimal("-0.1"))

    def test_ma_period_short_greater_than_long_raises_error(self) -> None:
        """Test that short MA period > long MA period raises ConfigError."""
        with pytest.raises(ConfigError, match="ma_period_short must be less than ma_period_long"):
            TechnicalFilterConfig(ma_period_short=50, ma_period_long=20)


class TestTechnicalFilter:
    """Test TechnicalFilter class."""

    def test_filter_with_passing_metrics(self) -> None:
        """Test filtering with metrics that pass all criteria."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("50"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            price=Decimal("105"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("105"),
            volume_current=Decimal("1000"),
            volume_avg=Decimal("800"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.score <= Decimal("1")

    def test_filter_with_rsi_oversold(self) -> None:
        """Test filtering with oversold RSI."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("25"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.5")

    def test_filter_with_rsi_overbought(self) -> None:
        """Test filtering with overbought RSI."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("80"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score < Decimal("0.5")

    def test_filter_with_rsi_outside_range(self) -> None:
        """Test filtering with RSI outside acceptable range."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("15"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "RSI" in result.reasons[0]

    def test_filter_with_bearish_macd_required(self) -> None:
        """Test filtering with bearish MACD when bullish required."""
        config = TechnicalFilterConfig(require_macd_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", macd=Decimal("0.2"), macd_signal=Decimal("0.5"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "MACD" in result.reasons[0]

    def test_filter_with_bearish_ma_required(self) -> None:
        """Test filtering with bearish MA when bullish required."""
        config = TechnicalFilterConfig(require_ma_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", ma_short=Decimal("90"), ma_long=Decimal("100"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "MA" in result.reasons[0]

    def test_filter_with_price_below_bollinger_lower(self) -> None:
        """Test filtering with price below Bollinger lower band."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("95"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Bollinger" in result.reasons[0]

    def test_filter_with_price_above_bollinger_upper(self) -> None:
        """Test filtering with price above Bollinger upper band."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("115"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Bollinger" in result.reasons[0]

    def test_filter_with_low_volume_ratio(self) -> None:
        """Test filtering with low volume ratio."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST", volume_current=Decimal("500"), volume_avg=Decimal("1000")
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Volume ratio" in result.reasons[0]

    def test_filter_with_low_momentum(self) -> None:
        """Test filtering with low price momentum."""
        config = TechnicalFilterConfig(min_price_momentum=Decimal("0.05"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", price_momentum=Decimal("-0.1"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Momentum" in result.reasons[0]

    def test_filter_with_high_atr_ratio(self) -> None:
        """Test filtering with high ATR ratio."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", atr=Decimal("10"), price=Decimal("100"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "ATR ratio" in result.reasons[0]

    def test_filter_with_trend_alignment_bearish(self) -> None:
        """Test filtering with bearish trend alignment."""
        config = TechnicalFilterConfig(require_trend_alignment=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("40"),
            ma_short=Decimal("90"),
            ma_long=Decimal("100"),
            macd=Decimal("0.2"),
            macd_signal=Decimal("0.5"),
            price=Decimal("95"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "trend not aligned" in result.reasons[0]

    def test_filter_with_partial_metrics(self) -> None:
        """Test filtering with only some metrics provided."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("50"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_filter_with_no_metrics(self) -> None:
        """Test filtering with no metrics."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST")
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_filter_batch_empty(self) -> None:
        """Test batch filtering with empty list."""
        filter_obj = TechnicalFilter()
        results = filter_obj.filter_batch([])
        assert results == []

    def test_filter_batch_multiple_instruments(self) -> None:
        """Test batch filtering with multiple instruments."""
        filter_obj = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(
                symbol=f"TEST{i}",
                rsi=Decimal(str(40 + i * 10)),
                macd=Decimal(str(i * 0.1)),
                macd_signal=Decimal(str(i * 0.05)),
            )
            for i in range(3)
        ]
        results = filter_obj.filter_batch(metrics_list)
        assert len(results) == 3
        assert all(isinstance(r, FilterResult) for r in results)

    def test_get_passed(self) -> None:
        """Test getting passed instruments."""
        filter_obj = TechnicalFilter()
        metrics_list = [
            TechnicalMetrics(
                symbol="PASS",
                rsi=Decimal("50"),
                macd=Decimal("0.5"),
                macd_signal=Decimal("0.3"),
            ),
            TechnicalMetrics(
                symbol="FAIL",
                rsi=Decimal("15"),
                macd=Decimal("0.2"),
                macd_signal=Decimal("0.5"),
            ),
        ]
        results = filter_obj.filter_batch(metrics_list)
        passed = filter_obj.get_passed(results)
        assert len(passed) == 1
        assert passed[0].symbol == "PASS"

    def test_rsi_scoring_middle(self) -> None:
        """Test that RSI in middle range gets good score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("50"))
        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.5")

    def test_macd_histogram_positive(self) -> None:
        """Test positive MACD histogram gets higher score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", macd=Decimal("0.5"), macd_signal=Decimal("0.3"))
        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.5")

    def test_macd_histogram_negative(self) -> None:
        """Test negative MACD histogram gets lower score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", macd=Decimal("0.3"), macd_signal=Decimal("0.5"))
        result = filter_obj.evaluate(metrics)
        assert result.score < Decimal("0.5")

    def test_bullish_ma_cross(self) -> None:
        """Test bullish MA cross gets high score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", ma_short=Decimal("110"), ma_long=Decimal("100"))
        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.8")

    def test_bearish_ma_cross(self) -> None:
        """Test bearish MA cross gets lower score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", ma_short=Decimal("90"), ma_long=Decimal("100"))
        result = filter_obj.evaluate(metrics)
        # Bearish MA cross still gets good score, just not as high as bullish
        assert result.score > Decimal("0.5")

    def test_bollinger_position_middle(self) -> None:
        """Test price in middle of Bollinger bands gets good score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("105"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.5")

    def test_volume_ratio_high(self) -> None:
        """Test high volume ratio gets high score."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST", volume_current=Decimal("1500"), volume_avg=Decimal("1000")
        )
        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.8")

    def test_zero_band_width(self) -> None:
        """Test zero Bollinger band width doesn't cause error."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            price=Decimal("105"),
            bollinger_upper=Decimal("105"),
            bollinger_lower=Decimal("105"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_zero_avg_volume(self) -> None:
        """Test zero average volume doesn't cause error."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST", volume_current=Decimal("1000"), volume_avg=Decimal("0")
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_zero_price(self) -> None:
        """Test zero price doesn't cause ATR error."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", atr=Decimal("10"), price=Decimal("0"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_perfect_technicals(self) -> None:
        """Test with perfect technical metrics."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("50"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            price=Decimal("105"),
            bollinger_upper=Decimal("110"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("105"),
            volume_current=Decimal("1500"),
            volume_avg=Decimal("1000"),
            price_momentum=Decimal("0.1"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.7")

    def test_multiple_failure_reasons(self) -> None:
        """Test that multiple failures return all reasons."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("15"),
            macd=Decimal("0.2"),
            macd_signal=Decimal("0.5"),
            volume_current=Decimal("500"),
            volume_avg=Decimal("1000"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert len(result.reasons) >= 2

    def test_trend_alignment_all_bullish(self) -> None:
        """Test trend alignment with all bullish signals."""
        config = TechnicalFilterConfig(require_trend_alignment=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="TEST",
            rsi=Decimal("60"),
            ma_short=Decimal("110"),
            ma_long=Decimal("100"),
            macd=Decimal("0.5"),
            macd_signal=Decimal("0.3"),
            price=Decimal("110"),
            bollinger_middle=Decimal("105"),
        )
        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_metrics_returned_in_result(self) -> None:
        """Test that metrics are returned in result."""
        filter_obj = TechnicalFilter()
        metrics = TechnicalMetrics(symbol="TEST", rsi=Decimal("50"))
        result = filter_obj.evaluate(metrics)
        assert result.metrics == metrics

    def test_score_ranges_from_zero_to_one(self) -> None:
        """Test that scores always range from 0 to 1."""
        filter_obj = TechnicalFilter()
        for rsi in [Decimal("20"), Decimal("40"), Decimal("60"), Decimal("80")]:
            metrics = TechnicalMetrics(symbol="TEST", rsi=rsi)
            result = filter_obj.evaluate(metrics)
            assert Decimal("0") <= result.score <= Decimal("1")

    def test_atr_scoring(self) -> None:
        """Test ATR ratio scoring."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.1"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(symbol="TEST", atr=Decimal("5"), price=Decimal("100"))
        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        # ATR ratio is 0.05, which is exactly at threshold, gives score of 0.5
        assert result.score == Decimal("0.5")
