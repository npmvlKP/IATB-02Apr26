"""
Extract continuous market strength score for instrument selection.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.selection._util import clamp_01
from iatb.selection.decay import temporal_decay


@dataclass(frozen=True)
class StrengthSignalInput:
    exchange: Exchange
    strength_inputs: StrengthInputs
    regime_confidence: Decimal
    instrument_symbol: str
    timestamp_utc: datetime


@dataclass(frozen=True)
class StrengthSignalOutput:
    score: Decimal
    confidence: Decimal
    regime: MarketRegime
    tradable: bool
    metadata: dict[str, str]


def compute_strength_signal(
    scorer: StrengthScorer,
    inputs: StrengthSignalInput,
    current_utc: datetime,
) -> StrengthSignalOutput:
    """Produce a [0, 1] strength score weighted by regime confidence."""
    _validate_input(inputs, current_utc)
    raw_score = scorer.score(inputs.exchange, inputs.strength_inputs)
    tradable = scorer.is_tradable(inputs.exchange, inputs.strength_inputs)
    decay = temporal_decay(inputs.timestamp_utc, current_utc, "strength")
    confidence = clamp_01(inputs.regime_confidence * decay)
    decayed_score = clamp_01(raw_score * decay)
    return StrengthSignalOutput(
        score=decayed_score,
        confidence=confidence,
        regime=inputs.strength_inputs.regime,
        tradable=tradable,
        metadata={
            "raw_score": str(raw_score),
            "adx": str(inputs.strength_inputs.adx),
            "breadth_ratio": str(inputs.strength_inputs.breadth_ratio),
            "volume_ratio": str(inputs.strength_inputs.volume_ratio),
            "volatility_atr_pct": str(inputs.strength_inputs.volatility_atr_pct),
        },
    )


def _validate_input(inputs: StrengthSignalInput, current: datetime) -> None:
    if inputs.timestamp_utc.tzinfo != UTC:
        msg = "timestamp_utc must be UTC"
        raise ConfigError(msg)
    if current.tzinfo != UTC:
        msg = "current_utc must be UTC"
        raise ConfigError(msg)
    if not inputs.instrument_symbol.strip():
        msg = "instrument_symbol cannot be empty"
        raise ConfigError(msg)
    if inputs.regime_confidence < Decimal("0") or inputs.regime_confidence > Decimal("1"):
        msg = "regime_confidence must be in [0, 1]"
        raise ConfigError(msg)
