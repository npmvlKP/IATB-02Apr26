"""
Comprehensive coverage tests for technical_filter.py.

Tests ADX/ATR/RSI filters, MACD, moving averages, Bollinger Bands, and error paths.
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
    """Test TechnicalFilterConfig validation."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = TechnicalFilterConfig()
        assert config.rsi_oversold == Decimal("30")
        assert config.rsi_overbought == Decimal("70")
        assert config.min_bollinger_position == Decimal("0.2")
        assert config.max_bollinger_position == Decimal("0.8")

    def test_invalid_rsi_range(self) -> None:
        """Test raises ConfigError when rsi_min >= rsi_max."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(rsi_min=Decimal("50"), rsi_max=Decimal("30"))
        assert "rsi_min must be less than rsi_max" in str(exc_info.value)

    def test_rsi_oversold_below_min(self) -> None:
        """Test raises ConfigError when rsi_oversold < rsi_min."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(rsi_min=Decimal("30"), rsi_oversold=Decimal("20"))
        assert "rsi_oversold must be >= rsi_min" in str(exc_info.value)

    def test_rsi_overbought_above_max(self) -> None:
        """Test raises ConfigError when rsi_overbought > rsi_max."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(rsi_max=Decimal("70"), rsi_overbought=Decimal("80"))
        assert "rsi_overbought must be <= rsi_max" in str(exc_info.value)

    def test_invalid_bollinger_position_negative(self) -> None:
        """Test raises ConfigError when min_bollinger_position is negative."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(min_bollinger_position=Decimal("-0.1"))
        assert "min_bollinger_position must be in [0, 1]" in str(exc_info.value)

    def test_invalid_bollinger_position_above_one(self) -> None:
        """Test raises ConfigError when min_bollinger_position > 1."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(min_bollinger_position=Decimal("1.5"))
        assert "min_bollinger_position must be in [0, 1]" in str(exc_info.value)

    def test_invalid_bollinger_range(self) -> None:
        """Test raises ConfigError when min > max."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(
                min_bollinger_position=Decimal("0.6"),
                max_bollinger_position=Decimal("0.4"),
            )
        assert (
            "min_bollinger_position cannot be greater than max_bollinger_position"
            in str(exc_info.value)
        )

    def test_negative_volume_ratio(self) -> None:
        """Test raises ConfigError when min_volume_ratio is negative."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(min_volume_ratio=Decimal("-0.5"))
        assert "min_volume_ratio cannot be negative" in str(exc_info.value)

    def test_invalid_ma_periods(self) -> None:
        """Test raises ConfigError when short >= long."""
        with pytest.raises(ConfigError) as exc_info:
            TechnicalFilterConfig(ma_period_short=50, ma_period_long=30)
        assert "ma_period_short must be less than ma_period_long" in str(exc_info.value)


class TestTechnicalFilter:
    """Test TechnicalFilter evaluation."""

    def test_evaluate_perfect_metrics(self) -> None:
        """Test instrument with perfect technical metrics."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="RELIANCE",
            rsi=Decimal("50"),
            macd=Decimal("1.0"),
            macd_signal=Decimal("0.5"),
            ma_short=Decimal("105"),
            ma_long=Decimal("100"),
            price=Decimal("102"),
            bollinger_upper=Decimal("105"),
            bollinger_lower=Decimal("95"),
            bollinger_middle=Decimal("100"),
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("1200000"),
            price_momentum=Decimal("0.02"),
            atr=Decimal("2.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        assert result.score > Decimal("0.5")
        assert result.symbol == "RELIANCE"

    def test_evaluate_rsi_oversold(self) -> None:
        """Test instrument with oversold RSI."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            rsi=Decimal("25"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        # Oversold should get good score
        assert result.score > Decimal("0.7")

    def test_evaluate_rsi_overbought(self) -> None:
        """Test instrument with overbought RSI."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            rsi=Decimal("75"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        # Overbought should get lower score
        assert result.score < Decimal("0.5")

    def test_evaluate_rsi_out_of_range(self) -> None:
        """Test instrument with RSI outside acceptable range."""
        config = TechnicalFilterConfig(rsi_min=Decimal("20"), rsi_max=Decimal("80"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            rsi=Decimal("85"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "RSI" in " ".join(result.reasons)

    def test_evaluate_macd_bullish(self) -> None:
        """Test bullish MACD."""
        config = TechnicalFilterConfig(require_macd_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            macd=Decimal("1.0"),
            macd_signal=Decimal("0.5"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_macd_bearish(self) -> None:
        """Test bearish MACD when required bullish."""
        config = TechnicalFilterConfig(require_macd_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            macd=Decimal("0.5"),
            macd_signal=Decimal("1.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "MACD" in " ".join(result.reasons)

    def test_evaluate_ma_bullish(self) -> None:
        """Test bullish moving average crossover."""
        config = TechnicalFilterConfig(require_ma_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            ma_short=Decimal("105"),
            ma_long=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_ma_bearish(self) -> None:
        """Test bearish moving average when required bullish."""
        config = TechnicalFilterConfig(require_ma_bullish=True)
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            ma_short=Decimal("95"),
            ma_long=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Short MA" in " ".join(result.reasons)

    def test_evaluate_bollinger_middle(self) -> None:
        """Test price in middle of Bollinger Bands."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("100"),
            bollinger_upper=Decimal("105"),
            bollinger_lower=Decimal("95"),
            bollinger_middle=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True
        # Middle position should get high score
        assert result.score > Decimal("0.8")

    def test_evaluate_bollinger_below_lower(self) -> None:
        """Test price below lower Bollinger Band."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("94"),
            bollinger_upper=Decimal("105"),
            bollinger_lower=Decimal("95"),
            bollinger_middle=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "below Bollinger lower band" in " ".join(result.reasons)

    def test_evaluate_bollinger_above_upper(self) -> None:
        """Test price above upper Bollinger Band."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("106"),
            bollinger_upper=Decimal("105"),
            bollinger_lower=Decimal("95"),
            bollinger_middle=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "above Bollinger upper band" in " ".join(result.reasons)

    def test_evaluate_volume_ratio_high(self) -> None:
        """Test high volume ratio."""
        config = TechnicalFilterConfig(min_volume_ratio=Decimal("0.8"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("1500000"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_volume_ratio_low(self) -> None:
        """Test low volume ratio."""
        config = TechnicalFilterConfig(min_volume_ratio=Decimal("0.8"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            volume_avg=Decimal("1000000"),
            volume_current=Decimal("500000"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Volume ratio" in " ".join(result.reasons)

    def test_evaluate_price_momentum_high(self) -> None:
        """Test high price momentum."""
        config = TechnicalFilterConfig(min_price_momentum=Decimal("0.01"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price_momentum=Decimal("0.02"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_price_momentum_low(self) -> None:
        """Test low price momentum."""
        config = TechnicalFilterConfig(min_price_momentum=Decimal("0.02"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price_momentum=Decimal("0.01"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "Momentum" in " ".join(result.reasons)

    def test_evaluate_atr_ratio_ok(self) -> None:
        """Test acceptable ATR ratio."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("100"),
            atr=Decimal("3.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is True

    def test_evaluate_atr_ratio_high(self) -> None:
        """Test high ATR ratio."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.03"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("100"),
            atr=Decimal("5.0"),
        )

        result = filter_obj.evaluate(metrics)
        assert result.passed is False
        assert "ATR ratio" in " ".join(result.reasons)

    def test_evaluate_none_optional_metrics(self) -> None:
        """Test evaluation with None values for optional metrics."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            rsi=Decimal("50"),
        )

        result = filter_obj.evaluate(metrics)
        # Should pass with only RSI
        assert result.passed is True

    def test_filter_batch(self, caplog) -> None:
        """Test batch filtering."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics_list = [
            TechnicalMetrics(
                symbol=f"STOCK{i}", rsi=Decimal("50") if i % 2 == 0 else Decimal("85")
            )
            for i in range(5)
        ]

        results = filter_obj.filter_batch(metrics_list)
        assert len(results) == 5
        passed_count = sum(1 for r in results if r.passed)
        assert passed_count == 3  # 0, 2, 4 pass
        assert "Technical filter: 3/5 passed" in caplog.text

    def test_get_passed(self) -> None:
        """Test getting passed instruments."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics_list = [
            TechnicalMetrics(
                symbol=f"STOCK{i}", rsi=Decimal("50") if i < 3 else Decimal("85")
            )
            for i in range(5)
        ]

        results = filter_obj.filter_batch(metrics_list)
        passed = filter_obj.get_passed(results)
        assert len(passed) == 3
        assert passed[0].symbol == "STOCK0"

    def test_rsi_scoring_middle(self) -> None:
        """Test RSI scoring in middle range."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            rsi=Decimal("50"),  # Ideal middle
        )

        result = filter_obj.evaluate(metrics)
        assert result.score > Decimal("0.8")

    def test_bollinger_zero_width(self) -> None:
        """Test Bollinger Bands with zero width."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("100"),
            bollinger_upper=Decimal("100"),
            bollinger_lower=Decimal("100"),
            bollinger_middle=Decimal("100"),
        )

        result = filter_obj.evaluate(metrics)
        # Should pass with neutral score
        assert result.passed is True
        assert result.score == Decimal("0.5")

    def test_volume_zero_avg(self) -> None:
        """Test volume with zero average."""
        config = TechnicalFilterConfig()
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            volume_avg=Decimal("0"),
            volume_current=Decimal("1000000"),
        )

        result = filter_obj.evaluate(metrics)
        # Should pass with neutral score
        assert result.passed is True

    def test_atr_zero_price(self) -> None:
        """Test ATR with zero price."""
        config = TechnicalFilterConfig(max_atr_ratio=Decimal("0.05"))
        filter_obj = TechnicalFilter(config)
        metrics = TechnicalMetrics(
            symbol="STOCK1",
            price=Decimal("0"),
            atr=Decimal("2.0"),
        )

        result = filter_obj.evaluate(metrics)
        # Should pass with neutral score
        assert result.passed is True
