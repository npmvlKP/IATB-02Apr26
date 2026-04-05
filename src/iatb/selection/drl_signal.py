"""
DRL backtest conclusion signal for instrument selection.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from iatb.backtesting.event_driven import EventDrivenResult
from iatb.backtesting.monte_carlo import MonteCarloResult
from iatb.backtesting.walk_forward import WalkForwardResult
from iatb.core.exceptions import ConfigError
from iatb.selection._util import clamp_01
from iatb.selection.decay import temporal_decay


@dataclass(frozen=True)
class BacktestConclusion:
    """Aggregated verdict from backtest suite for one instrument."""

    instrument_symbol: str
    out_of_sample_sharpe: Decimal
    max_drawdown_pct: Decimal
    win_rate: Decimal
    total_trades: int
    monte_carlo_robust: bool
    walk_forward_overfit_detected: bool
    mean_overfit_ratio: Decimal
    timestamp_utc: datetime


@dataclass(frozen=True)
class DRLSignalOutput:
    score: Decimal
    confidence: Decimal
    robust: bool
    metadata: dict[str, str]


def compute_drl_signal(
    conclusion: BacktestConclusion,
    current_utc: datetime,
) -> DRLSignalOutput:
    """Produce a [0, 1] DRL score from backtest conclusion."""
    _validate_conclusion(conclusion, current_utc)
    sharpe_norm = _sigmoid_normalize(conclusion.out_of_sample_sharpe)
    robustness = Decimal("1.0") if conclusion.monte_carlo_robust else Decimal("0.3")
    overfit_penalty = _graduated_overfit_penalty(conclusion)
    drawdown_factor = _drawdown_factor(conclusion.max_drawdown_pct)
    raw_score = clamp_01(sharpe_norm * robustness * drawdown_factor + overfit_penalty)
    decay = temporal_decay(conclusion.timestamp_utc, current_utc, "drl")
    decayed_score = clamp_01(raw_score * decay)
    confidence = _derive_confidence(conclusion, decay)
    return DRLSignalOutput(
        score=decayed_score,
        confidence=confidence,
        robust=conclusion.monte_carlo_robust and not conclusion.walk_forward_overfit_detected,
        metadata={
            "oos_sharpe": str(conclusion.out_of_sample_sharpe),
            "max_drawdown_pct": str(conclusion.max_drawdown_pct),
            "win_rate": str(conclusion.win_rate),
            "total_trades": str(conclusion.total_trades),
            "mc_robust": "1" if conclusion.monte_carlo_robust else "0",
            "wf_overfit": "1" if conclusion.walk_forward_overfit_detected else "0",
        },
    )


_MAX_DRAWDOWN_CAP = Decimal("20")
_OVERFIT_THRESHOLD = Decimal("2")
_OVERFIT_SCALE = Decimal("0.1")
_OVERFIT_MAX_PENALTY = Decimal("-0.5")


def _graduated_overfit_penalty(conclusion: BacktestConclusion) -> Decimal:
    """Continuous penalty: mild at ratio 2.1, severe at ratio 7+."""
    if not conclusion.walk_forward_overfit_detected:
        return Decimal("0")
    excess = conclusion.mean_overfit_ratio - _OVERFIT_THRESHOLD
    raw = -_OVERFIT_SCALE * max(Decimal("0"), excess)
    return max(_OVERFIT_MAX_PENALTY, raw)


def _drawdown_factor(max_drawdown_pct: Decimal) -> Decimal:
    """Penalize high drawdown: 20%+ zeroes out the DRL signal."""
    return clamp_01(Decimal("1") - max_drawdown_pct / _MAX_DRAWDOWN_CAP)


def _sigmoid_normalize(sharpe: Decimal) -> Decimal:
    """Map Sharpe ratio to [0, 1] via sigmoid."""
    # math.exp at API boundary; result converted to Decimal.
    exponent = -float(sharpe)  # float required: math.exp API
    clamped = max(-500.0, min(500.0, exponent))
    raw = Decimal(str(1.0 / (1.0 + math.exp(clamped))))
    return clamp_01(raw)


def _derive_confidence(conclusion: BacktestConclusion, decay: Decimal) -> Decimal:
    """Confidence based on trade count and robustness signals."""
    trade_factor = clamp_01(Decimal(conclusion.total_trades) / Decimal("100"))
    robust = conclusion.monte_carlo_robust
    robustness_factor = Decimal("1.0") if robust else Decimal("0.5")
    overfit = conclusion.walk_forward_overfit_detected
    overfit_factor = Decimal("1.0") if not overfit else Decimal("0.5")
    raw = trade_factor * robustness_factor * overfit_factor * decay
    return clamp_01(raw)


def _validate_conclusion(conclusion: BacktestConclusion, current: datetime) -> None:
    if conclusion.timestamp_utc.tzinfo != UTC:
        msg = "timestamp_utc must be UTC"
        raise ConfigError(msg)
    if current.tzinfo != UTC:
        msg = "current_utc must be UTC"
        raise ConfigError(msg)
    if not conclusion.instrument_symbol.strip():
        msg = "instrument_symbol cannot be empty"
        raise ConfigError(msg)
    if conclusion.total_trades < 0:
        msg = "total_trades cannot be negative"
        raise ConfigError(msg)
    if conclusion.win_rate < Decimal("0") or conclusion.win_rate > Decimal("1"):
        msg = "win_rate must be in [0, 1]"
        raise ConfigError(msg)
    if conclusion.max_drawdown_pct < Decimal("0"):
        msg = "max_drawdown_pct cannot be negative"
        raise ConfigError(msg)
    if conclusion.mean_overfit_ratio < Decimal("0"):
        msg = "mean_overfit_ratio cannot be negative"
        raise ConfigError(msg)


def build_conclusion(
    symbol: str,
    walk_forward: WalkForwardResult,
    monte_carlo: MonteCarloResult,
    event_driven: EventDrivenResult,
    timestamp_utc: datetime,
) -> BacktestConclusion:
    """Construct BacktestConclusion from upstream backtest results."""
    if not symbol.strip():
        msg = "symbol cannot be empty"
        raise ConfigError(msg)
    oos_sharpes = [f.out_sample_sharpe for f in walk_forward.folds]
    mean_oos = _safe_mean(oos_sharpes)
    ratios = [f.overfit_ratio for f in walk_forward.folds]
    mean_ratio = _safe_mean(ratios)
    total_pnl = event_driven.total_pnl
    trades = event_driven.trades
    win_rate = _estimate_win_rate(total_pnl, trades)
    drawdown = _estimate_drawdown(event_driven)
    return BacktestConclusion(
        instrument_symbol=symbol,
        out_of_sample_sharpe=mean_oos,
        max_drawdown_pct=drawdown,
        win_rate=win_rate,
        total_trades=trades,
        monte_carlo_robust=monte_carlo.robust,
        walk_forward_overfit_detected=walk_forward.overfitting_detected,
        mean_overfit_ratio=mean_ratio,
        timestamp_utc=timestamp_utc,
    )


def _safe_mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _estimate_win_rate(total_pnl: Decimal, trades: int) -> Decimal:
    """Win-rate proxy from aggregate PnL direction and magnitude."""
    if trades <= 0:
        return Decimal("0")
    return clamp_01(Decimal("0.5") + total_pnl / (Decimal(trades) * Decimal("100")))


def _estimate_drawdown(result: EventDrivenResult) -> Decimal:
    """Max drawdown from equity curve as percentage."""
    curve = result.equity_curve
    if len(curve) < 2:
        return Decimal("0")
    peak = curve[0]
    max_dd = Decimal("0")
    for value in curve[1:]:
        if value > peak:
            peak = value
        dd = (peak - value) / peak * Decimal("100") if peak > Decimal("0") else Decimal("0")
        if dd > max_dd:
            max_dd = dd
    return max_dd
