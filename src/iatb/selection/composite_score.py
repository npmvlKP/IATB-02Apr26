"""
Regime-aware weighted composite score from four selection signals.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection._util import confidence_ramp


@dataclass(frozen=True)
class RegimeWeights:
    sentiment: Decimal
    strength: Decimal
    volume_profile: Decimal
    drl: Decimal

    def __post_init__(self) -> None:
        total = self.sentiment + self.strength + self.volume_profile + self.drl
        if total != Decimal("1"):
            msg = f"regime weights must sum to 1.0, got {total}"
            raise ConfigError(msg)
        for name, value in self._fields():
            if value < Decimal("0"):
                msg = f"weight {name} cannot be negative"
                raise ConfigError(msg)

    def _fields(self) -> list[tuple[str, Decimal]]:
        return [
            ("sentiment", self.sentiment),
            ("strength", self.strength),
            ("volume_profile", self.volume_profile),
            ("drl", self.drl),
        ]


_REGIME_WEIGHT_PRESETS: dict[MarketRegime, RegimeWeights] = {
    MarketRegime.BULL: RegimeWeights(
        sentiment=Decimal("0.20"),
        strength=Decimal("0.25"),
        volume_profile=Decimal("0.15"),
        drl=Decimal("0.40"),
    ),
    MarketRegime.SIDEWAYS: RegimeWeights(
        sentiment=Decimal("0.15"),
        strength=Decimal("0.20"),
        volume_profile=Decimal("0.35"),
        drl=Decimal("0.30"),
    ),
    MarketRegime.BEAR: RegimeWeights(
        sentiment=Decimal("0.30"),
        strength=Decimal("0.30"),
        volume_profile=Decimal("0.10"),
        drl=Decimal("0.30"),
    ),
}


@dataclass(frozen=True)
class SignalScores:
    sentiment_score: Decimal
    sentiment_confidence: Decimal
    strength_score: Decimal
    strength_confidence: Decimal
    volume_profile_score: Decimal
    volume_profile_confidence: Decimal
    drl_score: Decimal
    drl_confidence: Decimal


@dataclass(frozen=True)
class CompositeResult:
    composite_score: Decimal
    regime: MarketRegime
    weights_used: RegimeWeights
    component_contributions: dict[str, Decimal]


def compute_composite_score(
    signals: SignalScores,
    regime: MarketRegime,
    custom_weights: RegimeWeights | None = None,
) -> CompositeResult:
    """Weighted fusion of four signals gated by market regime."""
    _validate_signals(signals)
    weights = custom_weights or _weights_for_regime(regime)
    contributions = _compute_contributions(signals, weights)
    total = sum(contributions.values(), Decimal("0"))
    composite = max(Decimal("0"), min(Decimal("1"), total))
    return CompositeResult(
        composite_score=composite,
        regime=regime,
        weights_used=weights,
        component_contributions=contributions,
    )


def _weights_for_regime(regime: MarketRegime) -> RegimeWeights:
    preset = _REGIME_WEIGHT_PRESETS.get(regime)
    if preset is None:
        msg = f"no weight preset for regime: {regime}"
        raise ConfigError(msg)
    return preset


def _compute_contributions(
    signals: SignalScores,
    weights: RegimeWeights,
) -> dict[str, Decimal]:
    sent = _gated(weights.sentiment, signals.sentiment_score, signals.sentiment_confidence)
    stren = _gated(weights.strength, signals.strength_score, signals.strength_confidence)
    vp_score = signals.volume_profile_score
    vp_conf = signals.volume_profile_confidence
    vp = _gated(weights.volume_profile, vp_score, vp_conf)
    drl = _gated(weights.drl, signals.drl_score, signals.drl_confidence)
    return {
        "sentiment": sent,
        "strength": stren,
        "volume_profile": vp,
        "drl": drl,
    }


def _gated(weight: Decimal, score: Decimal, confidence: Decimal) -> Decimal:
    """weight × score × soft_ramp(confidence)."""
    ramp = confidence_ramp(confidence)
    return weight * score * ramp


def _validate_signals(signals: SignalScores) -> None:
    fields = [
        ("sentiment_score", signals.sentiment_score),
        ("sentiment_confidence", signals.sentiment_confidence),
        ("strength_score", signals.strength_score),
        ("strength_confidence", signals.strength_confidence),
        ("volume_profile_score", signals.volume_profile_score),
        ("volume_profile_confidence", signals.volume_profile_confidence),
        ("drl_score", signals.drl_score),
        ("drl_confidence", signals.drl_confidence),
    ]
    for name, value in fields:
        if value < Decimal("0") or value > Decimal("1"):
            msg = f"{name} must be in [0, 1], got {value}"
            raise ConfigError(msg)
