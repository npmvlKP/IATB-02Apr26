"""
Technical filter for instrument selection.

Filters instruments based on technical indicators like RSI, MACD,
moving averages, Bollinger Bands, volume analysis, and price momentum.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TechnicalMetrics:
    """Technical metrics for an instrument."""

    symbol: str
    rsi: Decimal | None = None
    macd: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None
    ma_short: Decimal | None = None
    ma_long: Decimal | None = None
    price: Decimal | None = None
    bollinger_upper: Decimal | None = None
    bollinger_lower: Decimal | None = None
    bollinger_middle: Decimal | None = None
    volume_avg: Decimal | None = None
    volume_current: Decimal | None = None
    price_momentum: Decimal | None = None
    atr: Decimal | None = None


@dataclass
class TechnicalFilterConfig:
    """Configuration for technical filtering criteria."""

    rsi_oversold: Decimal = Decimal("30")
    rsi_overbought: Decimal = Decimal("70")
    rsi_min: Decimal = Decimal("20")
    rsi_max: Decimal = Decimal("80")
    require_macd_bullish: bool = False
    require_ma_bullish: bool = False
    ma_period_short: int = 20
    ma_period_long: int = 50
    min_bollinger_position: Decimal = Decimal("0.2")
    max_bollinger_position: Decimal = Decimal("0.8")
    min_volume_ratio: Decimal = Decimal("0.8")
    min_price_momentum: Decimal | None = None
    max_atr_ratio: Decimal | None = None
    require_trend_alignment: bool = False

    def __post_init__(self) -> None:
        if self.rsi_min >= self.rsi_max:
            msg = "rsi_min must be less than rsi_max"
            raise ConfigError(msg)
        if self.rsi_oversold < self.rsi_min:
            msg = "rsi_oversold must be >= rsi_min"
            raise ConfigError(msg)
        if self.rsi_overbought > self.rsi_max:
            msg = "rsi_overbought must be <= rsi_max"
            raise ConfigError(msg)
        if self.min_bollinger_position < Decimal("0") or self.min_bollinger_position > Decimal("1"):
            msg = "min_bollinger_position must be in [0, 1]"
            raise ConfigError(msg)
        if self.max_bollinger_position < Decimal("0") or self.max_bollinger_position > Decimal("1"):
            msg = "max_bollinger_position must be in [0, 1]"
            raise ConfigError(msg)
        if self.min_bollinger_position > self.max_bollinger_position:
            msg = "min_bollinger_position cannot be greater than max_bollinger_position"
            raise ConfigError(msg)
        if self.min_volume_ratio < Decimal("0"):
            msg = "min_volume_ratio cannot be negative"
            raise ConfigError(msg)
        if self.ma_period_short >= self.ma_period_long:
            msg = "ma_period_short must be less than ma_period_long"
            raise ConfigError(msg)


@dataclass(frozen=True)
class FilterResult:
    """Result of filtering a single instrument."""

    symbol: str
    passed: bool
    score: Decimal
    reasons: list[str]
    metrics: TechnicalMetrics


class TechnicalFilter:
    """Filter instruments based on technical criteria."""

    def __init__(self, config: TechnicalFilterConfig | None = None) -> None:
        self._config = config or TechnicalFilterConfig()

    def evaluate(self, metrics: TechnicalMetrics) -> FilterResult:
        """Evaluate a single instrument based on technical criteria."""
        reasons: list[str] = []
        score = Decimal("0")
        total_checks = 0
        passed_checks = 0

        if metrics.rsi is not None:
            total_checks += 1
            rsi_result = self._check_rsi(metrics.rsi)
            if rsi_result[0]:
                passed_checks += 1
                score += rsi_result[1]
            else:
                reasons.append(rsi_result[2])

        if metrics.macd is not None and metrics.macd_signal is not None:
            total_checks += 1
            macd_result = self._check_macd(metrics.macd, metrics.macd_signal)
            if macd_result[0]:
                passed_checks += 1
                score += macd_result[1]
            else:
                reasons.append(macd_result[2])

        if metrics.ma_short is not None and metrics.ma_long is not None:
            total_checks += 1
            ma_result = self._check_ma_cross(metrics.ma_short, metrics.ma_long)
            if ma_result[0]:
                passed_checks += 1
                score += ma_result[1]
            else:
                reasons.append(ma_result[2])

        if (
            metrics.price is not None
            and metrics.bollinger_upper is not None
            and metrics.bollinger_lower is not None
            and metrics.bollinger_middle is not None
        ):
            total_checks += 1
            bb_result = self._check_bollinger(
                metrics.price,
                metrics.bollinger_upper,
                metrics.bollinger_lower,
                metrics.bollinger_middle,
            )
            if bb_result[0]:
                passed_checks += 1
                score += bb_result[1]
            else:
                reasons.append(bb_result[2])

        if metrics.volume_avg is not None and metrics.volume_current is not None:
            total_checks += 1
            vol_result = self._check_volume(metrics.volume_current, metrics.volume_avg)
            if vol_result[0]:
                passed_checks += 1
                score += vol_result[1]
            else:
                reasons.append(vol_result[2])

        if metrics.price_momentum is not None and self._config.min_price_momentum is not None:
            total_checks += 1
            mom_result = self._check_momentum(metrics.price_momentum)
            if mom_result[0]:
                passed_checks += 1
                score += mom_result[1]
            else:
                reasons.append(mom_result[2])

        if (
            metrics.atr is not None
            and metrics.price is not None
            and self._config.max_atr_ratio is not None
        ):
            total_checks += 1
            atr_result = self._check_atr(metrics.atr, metrics.price)
            if atr_result[0]:
                passed_checks += 1
                score += atr_result[1]
            else:
                reasons.append(atr_result[2])

        if self._config.require_trend_alignment:
            total_checks += 1
            trend_result = self._check_trend_alignment(metrics)
            if trend_result[0]:
                passed_checks += 1
                score += trend_result[1]
            else:
                reasons.append(trend_result[2])

        final_score = score / max(total_checks, 1)
        passed = passed_checks == total_checks

        if passed:
            logger.debug("%s passed technical filter: score=%.2f", metrics.symbol, final_score)
        else:
            logger.info("%s failed technical filter: %s", metrics.symbol, "; ".join(reasons))

        return FilterResult(
            symbol=metrics.symbol,
            passed=passed,
            score=final_score,
            reasons=reasons,
            metrics=metrics,
        )

    def filter_batch(self, metrics_list: list[TechnicalMetrics]) -> list[FilterResult]:
        """Filter multiple instruments."""
        results = [self.evaluate(m) for m in metrics_list]
        passed_count = sum(1 for r in results if r.passed)
        logger.info("Technical filter: %d/%d passed", passed_count, len(metrics_list))
        return results

    def get_passed(self, results: list[FilterResult]) -> list[TechnicalMetrics]:
        """Get metrics of instruments that passed the filter."""
        return [r.metrics for r in results if r.passed]

    def _check_rsi(self, rsi: Decimal) -> tuple[bool, Decimal, str]:
        """Check RSI indicator."""
        if rsi < self._config.rsi_min or rsi > self._config.rsi_max:
            msg = (
                f"RSI {rsi} outside acceptable range "
                f"[{self._config.rsi_min}, {self._config.rsi_max}]"
            )
            return (False, Decimal("0"), msg)
        if rsi <= self._config.rsi_oversold:
            score = Decimal("0.8")
        elif rsi >= self._config.rsi_overbought:
            score = Decimal("0.3")
        else:
            mid = (self._config.rsi_oversold + self._config.rsi_overbought) / Decimal("2")
            distance = abs(rsi - mid)
            max_dist = (self._config.rsi_overbought - self._config.rsi_oversold) / Decimal("2")
            score = max(Decimal("0"), Decimal("1") - (distance / max_dist))
        return True, score, ""

    def _check_macd(self, macd: Decimal, signal: Decimal) -> tuple[bool, Decimal, str]:
        """Check MACD indicator."""
        if self._config.require_macd_bullish and macd < signal:
            return False, Decimal("0"), f"MACD {macd} below signal {signal}"
        histogram = macd - signal
        if histogram < Decimal("0"):
            score = Decimal("0.4")
        else:
            score = min(Decimal("1"), histogram / Decimal("0.5") + Decimal("0.5"))
        return True, score, ""

    def _check_ma_cross(self, ma_short: Decimal, ma_long: Decimal) -> tuple[bool, Decimal, str]:
        """Check moving average cross."""
        if self._config.require_ma_bullish and ma_short < ma_long:
            return (
                False,
                Decimal("0"),
                f"Short MA {ma_short} below long MA {ma_long}",
            )
        if ma_short >= ma_long:
            score = Decimal("0.9")
        else:
            ratio = ma_short / ma_long
            score = max(Decimal("0"), ratio)
        return True, score, ""

    def _check_bollinger(
        self,
        price: Decimal,
        upper: Decimal,
        lower: Decimal,
        middle: Decimal,
    ) -> tuple[bool, Decimal, str]:
        """Check Bollinger Band position."""
        band_width = upper - lower
        if band_width == Decimal("0"):
            return True, Decimal("0.5"), ""
        position = (price - lower) / band_width
        if position < self._config.min_bollinger_position:
            return (
                False,
                Decimal("0"),
                f"Price {price} below Bollinger lower band",
            )
        if position > self._config.max_bollinger_position:
            return (
                False,
                Decimal("0"),
                f"Price {price} above Bollinger upper band",
            )
        ideal = Decimal("0.5")
        distance = abs(position - ideal)
        max_dist = Decimal("0.5")
        score = max(Decimal("0"), Decimal("1") - (distance / max_dist))
        return True, score, ""

    def _check_volume(
        self, volume_current: Decimal, volume_avg: Decimal
    ) -> tuple[bool, Decimal, str]:
        """Check volume ratio."""
        if volume_avg == Decimal("0"):
            return True, Decimal("0.5"), ""
        ratio = volume_current / volume_avg
        if ratio < self._config.min_volume_ratio:
            return (
                False,
                Decimal("0"),
                f"Volume ratio {ratio} below minimum {self._config.min_volume_ratio}",
            )
        score = min(Decimal("1"), ratio)
        return True, score, ""

    def _check_momentum(self, momentum: Decimal) -> tuple[bool, Decimal, str]:
        """Check price momentum."""
        if self._config.min_price_momentum is None:
            msg = "min_price_momentum must be set"
            raise ValueError(msg)
        min_momentum = self._config.min_price_momentum
        if momentum < min_momentum:
            return (
                False,
                Decimal("0"),
                f"Momentum {momentum} below minimum {min_momentum}",
            )
        score = min(Decimal("1"), momentum / min_momentum)
        return True, score, ""

    def _check_atr(self, atr: Decimal, price: Decimal) -> tuple[bool, Decimal, str]:
        """Check ATR ratio."""
        if self._config.max_atr_ratio is None:
            msg = "max_atr_ratio must be set"
            raise ValueError(msg)
        max_ratio = self._config.max_atr_ratio
        if price == Decimal("0"):
            return True, Decimal("0.5"), ""
        atr_ratio = atr / price
        if atr_ratio > max_ratio:
            return (
                False,
                Decimal("0"),
                f"ATR ratio {atr_ratio} above maximum {max_ratio}",
            )
        score = max(Decimal("0"), Decimal("1") - (atr_ratio / max_ratio))
        return True, score, ""

    def _check_trend_alignment(self, metrics: TechnicalMetrics) -> tuple[bool, Decimal, str]:
        """Check trend alignment across indicators."""
        bullish_signals = 0
        total_signals = 0

        if metrics.rsi is not None:
            total_signals += 1
            if metrics.rsi > Decimal("50"):
                bullish_signals += 1

        if metrics.ma_short is not None and metrics.ma_long is not None:
            total_signals += 1
            if metrics.ma_short > metrics.ma_long:
                bullish_signals += 1

        if metrics.macd is not None and metrics.macd_signal is not None:
            total_signals += 1
            if metrics.macd > metrics.macd_signal:
                bullish_signals += 1

        if metrics.price is not None and metrics.bollinger_middle is not None:
            total_signals += 1
            if metrics.price > metrics.bollinger_middle:
                bullish_signals += 1

        if total_signals == 0:
            return True, Decimal("0.5"), ""

        alignment = Decimal(bullish_signals) / Decimal(total_signals)
        if alignment < Decimal("0.5"):
            return False, Decimal("0"), "Technical trend not aligned (bearish)"
        score = min(Decimal("1"), alignment)
        return True, score, ""
