"""
Fundamental filter for instrument selection.

Filters instruments based on fundamental criteria like P/E, P/B, ROE,
debt-to-equity, dividend yield, and earnings growth.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FundamentalMetrics:
    """Fundamental metrics for an instrument."""

    symbol: str
    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    roe: Decimal | None = None
    debt_to_equity: Decimal | None = None
    current_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    earnings_growth: Decimal | None = None
    market_cap: Decimal | None = None
    revenue_growth: Decimal | None = None


@dataclass
class FundamentalFilterConfig:
    """Configuration for fundamental filtering criteria."""

    min_pe: Decimal | None = None
    max_pe: Decimal | None = None
    min_pb: Decimal | None = None
    max_pb: Decimal | None = None
    min_roe: Decimal = Decimal("0.05")
    max_debt_to_equity: Decimal = Decimal("2.0")
    min_current_ratio: Decimal = Decimal("1.0")
    min_dividend_yield: Decimal | None = None
    min_earnings_growth: Decimal | None = None
    min_market_cap: Decimal | None = None
    max_market_cap: Decimal | None = None
    min_revenue_growth: Decimal | None = None
    require_profitability: bool = True

    def __post_init__(self) -> None:
        if self.min_pe is not None and self.max_pe is not None:
            if self.min_pe > self.max_pe:
                msg = "min_pe cannot be greater than max_pe"
                raise ConfigError(msg)
        if self.min_pb is not None and self.max_pb is not None:
            if self.min_pb > self.max_pb:
                msg = "min_pb cannot be greater than max_pb"
                raise ConfigError(msg)
        if self.min_market_cap is not None and self.max_market_cap is not None:
            if self.min_market_cap > self.max_market_cap:
                msg = "min_market_cap cannot be greater than max_market_cap"
                raise ConfigError(msg)
        if self.min_roe < Decimal("0"):
            msg = "min_roe cannot be negative"
            raise ConfigError(msg)
        if self.max_debt_to_equity < Decimal("0"):
            msg = "max_debt_to_equity cannot be negative"
            raise ConfigError(msg)
        if self.min_current_ratio < Decimal("0"):
            msg = "min_current_ratio cannot be negative"
            raise ConfigError(msg)


@dataclass(frozen=True)
class FilterResult:
    """Result of filtering a single instrument."""

    symbol: str
    passed: bool
    score: Decimal
    reasons: list[str]
    metrics: FundamentalMetrics


class FundamentalFilter:
    """Filter instruments based on fundamental criteria."""

    def __init__(self, config: FundamentalFilterConfig | None = None) -> None:
        self._config = config or FundamentalFilterConfig()

    def evaluate(self, metrics: FundamentalMetrics) -> FilterResult:
        """Evaluate a single instrument based on fundamental criteria."""
        reasons: list[str] = []
        score = Decimal("0")
        total_checks = 0
        passed_checks = 0

        if metrics.pe_ratio is not None:
            total_checks += 1
            pe_result = self._check_pe_ratio(metrics.pe_ratio)
            if pe_result[0]:
                passed_checks += 1
                score += pe_result[1]
            else:
                reasons.append(pe_result[2])

        if metrics.pb_ratio is not None:
            total_checks += 1
            pb_result = self._check_pb_ratio(metrics.pb_ratio)
            if pb_result[0]:
                passed_checks += 1
                score += pb_result[1]
            else:
                reasons.append(pb_result[2])

        if metrics.roe is not None:
            total_checks += 1
            roe_result = self._check_roe(metrics.roe)
            if roe_result[0]:
                passed_checks += 1
                score += roe_result[1]
            else:
                reasons.append(roe_result[2])

        if metrics.debt_to_equity is not None:
            total_checks += 1
            de_result = self._check_debt_to_equity(metrics.debt_to_equity)
            if de_result[0]:
                passed_checks += 1
                score += de_result[1]
            else:
                reasons.append(de_result[2])

        if metrics.current_ratio is not None:
            total_checks += 1
            cr_result = self._check_current_ratio(metrics.current_ratio)
            if cr_result[0]:
                passed_checks += 1
                score += cr_result[1]
            else:
                reasons.append(cr_result[2])

        if metrics.dividend_yield is not None and self._config.min_dividend_yield is not None:
            total_checks += 1
            div_result = self._check_dividend_yield(metrics.dividend_yield)
            if div_result[0]:
                passed_checks += 1
                score += div_result[1]
            else:
                reasons.append(div_result[2])

        if metrics.earnings_growth is not None and self._config.min_earnings_growth is not None:
            total_checks += 1
            eg_result = self._check_earnings_growth(metrics.earnings_growth)
            if eg_result[0]:
                passed_checks += 1
                score += eg_result[1]
            else:
                reasons.append(eg_result[2])

        if metrics.market_cap is not None:
            total_checks += 1
            mc_result = self._check_market_cap(metrics.market_cap)
            if mc_result[0]:
                passed_checks += 1
                score += mc_result[1]
            else:
                reasons.append(mc_result[2])

        if metrics.revenue_growth is not None and self._config.min_revenue_growth is not None:
            total_checks += 1
            rg_result = self._check_revenue_growth(metrics.revenue_growth)
            if rg_result[0]:
                passed_checks += 1
                score += rg_result[1]
            else:
                reasons.append(rg_result[2])

        if self._config.require_profitability:
            total_checks += 1
            prof_result = self._check_profitability(metrics)
            if prof_result[0]:
                passed_checks += 1
                score += prof_result[1]
            else:
                reasons.append(prof_result[2])

        final_score = score / max(total_checks, 1)
        passed = passed_checks == total_checks

        if passed:
            logger.debug("%s passed fundamental filter: score=%.2f", metrics.symbol, final_score)
        else:
            logger.info("%s failed fundamental filter: %s", metrics.symbol, "; ".join(reasons))

        return FilterResult(
            symbol=metrics.symbol,
            passed=passed,
            score=final_score,
            reasons=reasons,
            metrics=metrics,
        )

    def filter_batch(self, metrics_list: list[FundamentalMetrics]) -> list[FilterResult]:
        """Filter multiple instruments."""
        results = [self.evaluate(m) for m in metrics_list]
        passed_count = sum(1 for r in results if r.passed)
        logger.info("Fundamental filter: %d/%d passed", passed_count, len(metrics_list))
        return results

    def get_passed(self, results: list[FilterResult]) -> list[FundamentalMetrics]:
        """Get metrics of instruments that passed the filter."""
        return [r.metrics for r in results if r.passed]

    def _check_pe_ratio(self, pe: Decimal) -> tuple[bool, Decimal, str]:
        """Check P/E ratio."""
        if self._config.min_pe is not None and pe < self._config.min_pe:
            return (
                False,
                Decimal("0"),
                f"P/E ratio {pe} below minimum {self._config.min_pe}",
            )
        if self._config.max_pe is not None and pe > self._config.max_pe:
            return (
                False,
                Decimal("0"),
                f"P/E ratio {pe} above maximum {self._config.max_pe}",
            )
        ideal = self._config.min_pe or Decimal("15")
        if self._config.max_pe is not None:
            if self._config.min_pe is None:
                msg = "min_pe must be set when max_pe is set"
                raise ValueError(msg)
            ideal = (self._config.min_pe + self._config.max_pe) / Decimal("2")
        distance = abs(pe - ideal)
        max_dist = (
            (self._config.max_pe - self._config.min_pe) / Decimal("2")
            if self._config.max_pe is not None and self._config.min_pe is not None
            else ideal
        )
        score = max(Decimal("0"), Decimal("1") - (distance / max_dist))
        return True, score, ""

    def _check_pb_ratio(self, pb: Decimal) -> tuple[bool, Decimal, str]:
        """Check P/B ratio."""
        if self._config.min_pb is not None and pb < self._config.min_pb:
            return (
                False,
                Decimal("0"),
                f"P/B ratio {pb} below minimum {self._config.min_pb}",
            )
        if self._config.max_pb is not None and pb > self._config.max_pb:
            return (
                False,
                Decimal("0"),
                f"P/B ratio {pb} above maximum {self._config.max_pb}",
            )
        ideal = self._config.min_pb or Decimal("2.0")
        if self._config.max_pb is not None:
            if self._config.min_pb is None:
                msg = "min_pb must be set when max_pb is set"
                raise ValueError(msg)
            ideal = self._config.min_pb + (self._config.max_pb - self._config.min_pb) / Decimal("3")
        distance = abs(pb - ideal)
        max_dist = (
            self._config.max_pb - self._config.min_pb
            if self._config.max_pb is not None and self._config.min_pb is not None
            else ideal
        )
        score = max(Decimal("0"), Decimal("1") - (distance / max_dist))
        return True, score, ""

    def _check_roe(self, roe: Decimal) -> tuple[bool, Decimal, str]:
        """Check ROE."""
        if roe < self._config.min_roe:
            return False, Decimal("0"), f"ROE {roe} below minimum {self._config.min_roe}"
        score = min(Decimal("1"), roe / (self._config.min_roe * Decimal("2")))
        return True, score, ""

    def _check_debt_to_equity(self, de: Decimal) -> tuple[bool, Decimal, str]:
        """Check debt-to-equity ratio."""
        if de > self._config.max_debt_to_equity:
            return (
                False,
                Decimal("0"),
                f"Debt-to-equity {de} above maximum {self._config.max_debt_to_equity}",
            )
        score = max(
            Decimal("0"),
            Decimal("1") - (de / (self._config.max_debt_to_equity * Decimal("1.5"))),
        )
        return True, score, ""

    def _check_current_ratio(self, cr: Decimal) -> tuple[bool, Decimal, str]:
        """Check current ratio."""
        if cr < self._config.min_current_ratio:
            return (
                False,
                Decimal("0"),
                f"Current ratio {cr} below minimum {self._config.min_current_ratio}",
            )
        score = min(Decimal("1"), cr / (self._config.min_current_ratio * Decimal("2")))
        return True, score, ""

    def _check_dividend_yield(self, dy: Decimal) -> tuple[bool, Decimal, str]:
        """Check dividend yield."""
        if self._config.min_dividend_yield is None:
            msg = "min_dividend_yield must be set"
            raise ValueError(msg)
        min_dy = self._config.min_dividend_yield
        if dy < min_dy:
            return (
                False,
                Decimal("0"),
                f"Dividend yield {dy} below minimum {min_dy}",
            )
        score = min(Decimal("1"), dy / (min_dy * Decimal("2")))
        return True, score, ""

    def _check_earnings_growth(self, eg: Decimal) -> tuple[bool, Decimal, str]:
        """Check earnings growth."""
        if self._config.min_earnings_growth is None:
            msg = "min_earnings_growth must be set"
            raise ValueError(msg)
        min_eg = self._config.min_earnings_growth
        if eg < min_eg:
            return (
                False,
                Decimal("0"),
                f"Earnings growth {eg} below minimum {min_eg}",
            )
        score = min(Decimal("1"), eg / (min_eg * Decimal("2")))
        return True, score, ""

    def _check_market_cap(self, mc: Decimal) -> tuple[bool, Decimal, str]:
        """Check market cap."""
        if self._config.min_market_cap is not None and mc < self._config.min_market_cap:
            return (
                False,
                Decimal("0"),
                f"Market cap {mc} below minimum {self._config.min_market_cap}",
            )
        if self._config.max_market_cap is not None and mc > self._config.max_market_cap:
            return (
                False,
                Decimal("0"),
                f"Market cap {mc} above maximum {self._config.max_market_cap}",
            )
        ideal = self._config.min_market_cap or mc
        if self._config.max_market_cap is not None and self._config.min_market_cap is not None:
            ideal = self._config.min_market_cap + (
                self._config.max_market_cap - self._config.min_market_cap
            ) / Decimal("2")
        distance = abs(mc - ideal)
        max_dist = (
            (self._config.max_market_cap - self._config.min_market_cap) / Decimal("2")
            if self._config.max_market_cap is not None and self._config.min_market_cap is not None
            else ideal
        )
        score = max(Decimal("0"), Decimal("1") - (distance / max_dist))
        return True, score, ""

    def _check_revenue_growth(self, rg: Decimal) -> tuple[bool, Decimal, str]:
        """Check revenue growth."""
        if self._config.min_revenue_growth is None:
            msg = "min_revenue_growth must be set"
            raise ValueError(msg)
        min_rg = self._config.min_revenue_growth
        if rg < min_rg:
            return (
                False,
                Decimal("0"),
                f"Revenue growth {rg} below minimum {min_rg}",
            )
        score = min(Decimal("1"), rg / (min_rg * Decimal("2")))
        return True, score, ""

    def _check_profitability(self, metrics: FundamentalMetrics) -> tuple[bool, Decimal, str]:
        """Check basic profitability."""
        if metrics.roe is None:
            return True, Decimal("1"), ""
        if metrics.roe < Decimal("0"):
            return False, Decimal("0"), "Negative ROE indicates unprofitability"
        score = Decimal("1")
        return True, score, ""
