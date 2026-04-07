"""
Breakout and breakdown ranking helpers for dashboard scanners.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from iatb.core.exceptions import ConfigError


class HealthStatus(StrEnum):
    """Health status for factor evaluation."""

    HEALTHY = "HEALTHY"
    NOT_HEALTHY = "NOT_HEALTHY"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class BreakoutCandidate:
    symbol: str
    breakout_probability: Decimal
    distance_to_breakout_pct: Decimal
    direction: str

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            msg = "symbol cannot be empty"
            raise ConfigError(msg)
        if self.breakout_probability < Decimal("0") or self.breakout_probability > Decimal("1"):
            msg = "breakout_probability must be between 0 and 1"
            raise ConfigError(msg)
        if self.distance_to_breakout_pct < Decimal("0"):
            msg = "distance_to_breakout_pct cannot be negative"
            raise ConfigError(msg)
        normalized = self.direction.strip().lower()
        if normalized not in {"breakout", "breakdown"}:
            msg = "direction must be either 'breakout' or 'breakdown'"
            raise ConfigError(msg)
        object.__setattr__(self, "direction", normalized)


@dataclass(frozen=True)
class FactorHealth:
    """Health status for a single factor."""

    factor_name: str
    status: HealthStatus
    score: Decimal
    details: str

    def __post_init__(self) -> None:
        if not self.factor_name.strip():
            msg = "factor_name cannot be empty"
            raise ConfigError(msg)
        if self.score < Decimal("0") or self.score > Decimal("1"):
            msg = "score must be between 0 and 1"
            raise ConfigError(msg)


@dataclass(frozen=True)
class InstrumentHealthMatrix:
    """Per-factor health matrix for a single instrument."""

    symbol: str
    sentiment_health: FactorHealth
    market_strength_health: FactorHealth
    volume_analysis_health: FactorHealth
    drl_backtest_health: FactorHealth
    safe_exit_probability: Decimal
    overall_health: HealthStatus
    is_approved: bool
    timestamp_utc: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            msg = "symbol cannot be empty"
            raise ConfigError(msg)
        if self.safe_exit_probability < Decimal("0") or self.safe_exit_probability > Decimal("1"):
            msg = "safe_exit_probability must be between 0 and 1"
            raise ConfigError(msg)
        if self.timestamp_utc.tzinfo != UTC:
            msg = "timestamp_utc must be UTC"
            raise ConfigError(msg)


@dataclass(frozen=True)
class ScannerHealthResult:
    """Result of health matrix scan for all instruments."""

    instruments: list[InstrumentHealthMatrix]
    approved_count: int
    total_scanned: int
    scan_timestamp_utc: datetime


def rank_breakout_candidates(
    candidates: list[BreakoutCandidate],
    top_n: int = 10,
    direction: str = "breakout",
) -> list[BreakoutCandidate]:
    if top_n <= 0:
        msg = "top_n must be positive"
        raise ConfigError(msg)
    normalized = direction.strip().lower()
    if normalized not in {"breakout", "breakdown"}:
        msg = "direction must be either 'breakout' or 'breakdown'"
        raise ConfigError(msg)
    filtered = [item for item in candidates if item.direction == normalized]
    ordered = sorted(
        filtered,
        key=lambda item: (item.breakout_probability, -item.distance_to_breakout_pct),
        reverse=True,
    )
    return ordered[:top_n]


def evaluate_factor_health(
    factor_name: str,
    score: Decimal,
    healthy_threshold: Decimal = Decimal("0.6"),
    unhealthy_threshold: Decimal = Decimal("0.4"),
) -> FactorHealth:
    """Evaluate health status for a single factor based on score."""
    if healthy_threshold <= unhealthy_threshold:
        msg = "healthy_threshold must be greater than unhealthy_threshold"
        raise ConfigError(msg)
    if score >= healthy_threshold:
        status = HealthStatus.HEALTHY
        details = f"Score {float(score):.2f} >= {float(healthy_threshold):.2f} threshold"
    elif score <= unhealthy_threshold:
        status = HealthStatus.NOT_HEALTHY
        details = f"Score {float(score):.2f} <= {float(unhealthy_threshold):.2f} threshold"
    else:
        status = HealthStatus.NEUTRAL
        details = f"Score {float(score):.2f} in neutral range"
    return FactorHealth(
        factor_name=factor_name,
        status=status,
        score=score,
        details=details,
    )


def compute_overall_health(
    sentiment: FactorHealth,
    market_strength: FactorHealth,
    volume: FactorHealth,
    drl: FactorHealth,
    exit_prob: Decimal,
    min_healthy_factors: int = 3,
    min_exit_probability: Decimal = Decimal("0.5"),
) -> HealthStatus:
    """Compute overall health status from all factors."""
    factors = [sentiment, market_strength, volume, drl]
    healthy_count = sum(1 for f in factors if f.status == HealthStatus.HEALTHY)
    unhealthy_count = sum(1 for f in factors if f.status == HealthStatus.NOT_HEALTHY)

    if unhealthy_count > 1:
        return HealthStatus.NOT_HEALTHY
    if healthy_count >= min_healthy_factors and exit_prob >= min_exit_probability:
        return HealthStatus.HEALTHY
    if healthy_count >= 2 and exit_prob >= min_exit_probability:
        return HealthStatus.NEUTRAL
    return HealthStatus.NOT_HEALTHY


def build_instrument_health_matrix(
    symbol: str,
    sentiment_score: Decimal,
    market_strength_score: Decimal,
    volume_score: Decimal,
    drl_backtest_score: Decimal,
    safe_exit_probability: Decimal,
    timestamp_utc: datetime | None = None,
    sentiment_threshold: Decimal = Decimal("0.6"),
    strength_threshold: Decimal = Decimal("0.6"),
    volume_threshold: Decimal = Decimal("0.6"),
    drl_threshold: Decimal = Decimal("0.6"),
) -> InstrumentHealthMatrix:
    """Build complete health matrix for an instrument."""
    ts = timestamp_utc or datetime.now(UTC)
    if ts.tzinfo != UTC:
        msg = "timestamp_utc must be UTC"
        raise ConfigError(msg)

    sentiment_health = evaluate_factor_health("Sentiment", sentiment_score, sentiment_threshold)
    market_strength_health = evaluate_factor_health(
        "Market Strength", market_strength_score, strength_threshold
    )
    volume_health = evaluate_factor_health("Volume Analysis", volume_score, volume_threshold)
    drl_health = evaluate_factor_health("DRL/Backtest", drl_backtest_score, drl_threshold)

    overall = compute_overall_health(
        sentiment_health,
        market_strength_health,
        volume_health,
        drl_health,
        safe_exit_probability,
    )

    is_approved = overall == HealthStatus.HEALTHY

    return InstrumentHealthMatrix(
        symbol=symbol,
        sentiment_health=sentiment_health,
        market_strength_health=market_strength_health,
        volume_analysis_health=volume_health,
        drl_backtest_health=drl_health,
        safe_exit_probability=safe_exit_probability,
        overall_health=overall,
        is_approved=is_approved,
        timestamp_utc=ts,
    )


def build_scanner_health_result(
    instruments: list[InstrumentHealthMatrix],
) -> ScannerHealthResult:
    """Build scanner health result from list of instrument matrices."""
    approved = [i for i in instruments if i.is_approved]
    return ScannerHealthResult(
        instruments=instruments,
        approved_count=len(approved),
        total_scanned=len(instruments),
        scan_timestamp_utc=datetime.now(UTC),
    )


def health_status_to_color(status: HealthStatus) -> str:
    """Convert health status to color for visualization."""
    colors = {
        HealthStatus.HEALTHY: "green",
        HealthStatus.NOT_HEALTHY: "red",
        HealthStatus.NEUTRAL: "gray",
    }
    return colors.get(status, "gray")


def health_status_to_badge(status: HealthStatus) -> str:
    """Convert health status to badge emoji for visualization."""
    badges = {
        HealthStatus.HEALTHY: "✅",
        HealthStatus.NOT_HEALTHY: "❌",
        HealthStatus.NEUTRAL: "⚪",
    }
    return badges.get(status, "⚪")
