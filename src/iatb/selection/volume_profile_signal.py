"""
Derive volume profile selection signal from POC, VAH, VAL structure.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.volume_profile import VolumeProfile
from iatb.selection._util import DirectionalIntent, clamp_01
from iatb.selection.decay import temporal_decay


class ProfileShape(StrEnum):
    P_BULLISH = "P"
    D_BALANCED = "D"
    B_BEARISH = "b"


_SHAPE_SCORES_LONG: dict[ProfileShape, Decimal] = {
    ProfileShape.P_BULLISH: Decimal("0.80"),
    ProfileShape.D_BALANCED: Decimal("0.50"),
    ProfileShape.B_BEARISH: Decimal("0.20"),
}

_SHAPE_SCORES_SHORT: dict[ProfileShape, Decimal] = {
    ProfileShape.P_BULLISH: Decimal("0.20"),
    ProfileShape.D_BALANCED: Decimal("0.50"),
    ProfileShape.B_BEARISH: Decimal("0.80"),
}

_W_POC_PROXIMITY = Decimal("0.40")
_W_VA_WIDTH = Decimal("0.35")
_W_SHAPE = Decimal("0.25")


@dataclass(frozen=True)
class VolumeProfileSignalInput:
    profile: VolumeProfile
    current_price: Decimal
    instrument_symbol: str
    timestamp_utc: datetime


@dataclass(frozen=True)
class VolumeProfileSignalOutput:
    score: Decimal
    confidence: Decimal
    shape: ProfileShape
    poc_distance_pct: Decimal
    va_width_pct: Decimal
    metadata: dict[str, str]


def compute_volume_profile_signal(
    inputs: VolumeProfileSignalInput,
    current_utc: datetime,
    intent: DirectionalIntent = DirectionalIntent.NEUTRAL,
    regime: MarketRegime = MarketRegime.SIDEWAYS,
) -> VolumeProfileSignalOutput:
    """Produce a [0, 1] volume profile score."""
    _validate_input(inputs, current_utc)
    profile = inputs.profile
    shape = classify_profile_shape(profile)
    raw_poc = _poc_proximity(inputs.current_price, profile)
    poc_prox = _regime_adjusted_poc(raw_poc, regime)
    va_width = _va_width_ratio(inputs.current_price, profile)
    shape_score = _shape_score_for_intent(shape, intent)
    raw_score = (_W_POC_PROXIMITY * poc_prox) + (_W_VA_WIDTH * va_width) + (_W_SHAPE * shape_score)
    decay = temporal_decay(inputs.timestamp_utc, current_utc, "volume_profile")
    decayed_score = clamp_01(raw_score * decay)
    poc_dist_pct = _poc_distance_pct(inputs.current_price, profile)
    va_w_pct = _va_width_pct(inputs.current_price, profile)
    return VolumeProfileSignalOutput(
        score=decayed_score,
        confidence=clamp_01(decay),
        shape=shape,
        poc_distance_pct=poc_dist_pct,
        va_width_pct=va_w_pct,
        metadata={
            "poc": str(profile.poc),
            "vah": str(profile.vah),
            "val": str(profile.val),
            "shape": shape.value,
            "total_volume": str(profile.total_volume),
            "intent": intent.value,
        },
    )


def classify_profile_shape(profile: VolumeProfile) -> ProfileShape:
    """Classify as P (bullish), b (bearish), or D (balanced)."""
    va_range = profile.vah - profile.val
    if va_range == Decimal("0"):
        return ProfileShape.D_BALANCED
    poc_position = (profile.poc - profile.val) / va_range
    if poc_position >= Decimal("0.65"):
        return ProfileShape.P_BULLISH
    if poc_position <= Decimal("0.35"):
        return ProfileShape.B_BEARISH
    return ProfileShape.D_BALANCED


def _regime_adjusted_poc(raw_proximity: Decimal, regime: MarketRegime) -> Decimal:
    """In trending regimes, invert so far-from-POC scores high."""
    if regime in (MarketRegime.BULL, MarketRegime.BEAR):
        return clamp_01(Decimal("1") - raw_proximity)
    return raw_proximity


def _shape_score_for_intent(
    shape: ProfileShape,
    intent: DirectionalIntent,
) -> Decimal:
    """Shape score adjusted for trade direction."""
    if intent == DirectionalIntent.SHORT:
        return _SHAPE_SCORES_SHORT[shape]
    return _SHAPE_SCORES_LONG[shape]


def _poc_proximity(price: Decimal, profile: VolumeProfile) -> Decimal:
    """1 when price equals POC, 0 when far away."""
    va_range = profile.vah - profile.val
    if va_range == Decimal("0"):
        return Decimal("1") if price == profile.poc else Decimal("0")
    distance = abs(price - profile.poc)
    ratio = distance / va_range
    return clamp_01(Decimal("1") - ratio)


def _va_width_ratio(price: Decimal, profile: VolumeProfile) -> Decimal:
    """Narrower value area = stronger trend signal."""
    if price <= Decimal("0"):
        return Decimal("0")
    width_pct = (profile.vah - profile.val) / price
    return clamp_01(Decimal("1") - width_pct)


def _poc_distance_pct(price: Decimal, profile: VolumeProfile) -> Decimal:
    """Percentage distance from current price to POC."""
    if price <= Decimal("0"):
        return Decimal("0")
    return abs(price - profile.poc) / price * Decimal("100")


def _va_width_pct(price: Decimal, profile: VolumeProfile) -> Decimal:
    """Value area width as percentage of price."""
    if price <= Decimal("0"):
        return Decimal("0")
    return (profile.vah - profile.val) / price * Decimal("100")


def _validate_input(inputs: VolumeProfileSignalInput, current: datetime) -> None:
    if inputs.timestamp_utc.tzinfo != UTC:
        msg = "timestamp_utc must be UTC"
        raise ConfigError(msg)
    if current.tzinfo != UTC:
        msg = "current_utc must be UTC"
        raise ConfigError(msg)
    if not inputs.instrument_symbol.strip():
        msg = "instrument_symbol cannot be empty"
        raise ConfigError(msg)
    if inputs.current_price <= Decimal("0"):
        msg = "current_price must be positive"
        raise ConfigError(msg)
