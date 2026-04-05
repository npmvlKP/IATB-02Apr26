"""
Central orchestrator for multi-factor instrument auto-selection.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection._util import rank_percentile
from iatb.selection.composite_score import (
    CompositeResult,
    RegimeWeights,
    SignalScores,
    compute_composite_score,
)
from iatb.selection.drl_signal import DRLSignalOutput
from iatb.selection.ranking import (
    RankingConfig,
    SelectionResult,
    rank_and_select,
)
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstrumentSignals:
    """Pre-computed signals for a single instrument."""

    symbol: str
    exchange: Exchange
    sentiment: SentimentSignalOutput
    strength: StrengthSignalOutput
    volume_profile: VolumeProfileSignalOutput
    drl: DRLSignalOutput
    strength_inputs: StrengthInputs | None = None


@dataclass(frozen=True)
class ScoredInstrument:
    symbol: str
    exchange: Exchange
    composite: CompositeResult
    signals: InstrumentSignals


class InstrumentScorer:
    """Fuses four signal sources into ranked instrument selection."""

    def __init__(
        self,
        ranking_config: RankingConfig | None = None,
        custom_weights: dict[MarketRegime, RegimeWeights] | None = None,
    ) -> None:
        self._ranking_config = ranking_config or RankingConfig()
        self._custom_weights = custom_weights or {}

    def score_instruments(
        self,
        instrument_signals: list[InstrumentSignals],
        regime: MarketRegime,
    ) -> list[ScoredInstrument]:
        """Score each instrument via regime-aware composite fusion."""
        normalized = _normalize_signals_across(instrument_signals)
        scored: list[ScoredInstrument] = []
        for signals, norm in zip(instrument_signals, normalized, strict=True):
            composite = self._compute_composite(norm, regime)
            scored.append(
                ScoredInstrument(
                    symbol=signals.symbol,
                    exchange=signals.exchange,
                    composite=composite,
                    signals=signals,
                ),
            )
        logger.info("Scored %d instruments under %s regime", len(scored), regime.value)
        return scored

    def select_top(
        self,
        scored: list[ScoredInstrument],
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> SelectionResult:
        """Rank, filter, and select top-N instruments."""
        candidates = [
            (s.symbol, s.exchange, s.composite.composite_score, _build_metadata(s)) for s in scored
        ]
        return rank_and_select(candidates, self._ranking_config, correlations)

    def score_and_select(
        self,
        instrument_signals: list[InstrumentSignals],
        regime: MarketRegime,
        correlations: dict[tuple[str, str], Decimal] | None = None,
    ) -> SelectionResult:
        """One-call convenience: score all instruments and select top-N."""
        scored = self.score_instruments(instrument_signals, regime)
        return self.select_top(scored, correlations)

    def _compute_composite(
        self,
        norm_scores: SignalScores,
        regime: MarketRegime,
    ) -> CompositeResult:
        custom = self._custom_weights.get(regime)
        return compute_composite_score(norm_scores, regime, custom)


def _normalize_signals_across(
    signals_list: list[InstrumentSignals],
) -> list[SignalScores]:
    """Rank-percentile normalize each channel across the instrument universe."""
    if not signals_list:
        return []
    sent_scores = rank_percentile([s.sentiment.score for s in signals_list])
    str_scores = rank_percentile([s.strength.score for s in signals_list])
    vp_scores = rank_percentile([s.volume_profile.score for s in signals_list])
    drl_scores = rank_percentile([s.drl.score for s in signals_list])
    return [
        SignalScores(
            sentiment_score=sent_scores[i],
            sentiment_confidence=signals_list[i].sentiment.confidence,
            strength_score=str_scores[i],
            strength_confidence=signals_list[i].strength.confidence,
            volume_profile_score=vp_scores[i],
            volume_profile_confidence=signals_list[i].volume_profile.confidence,
            drl_score=drl_scores[i],
            drl_confidence=signals_list[i].drl.confidence,
        )
        for i in range(len(signals_list))
    ]


def _build_metadata(scored: ScoredInstrument) -> dict[str, str]:
    contributions = scored.composite.component_contributions
    return {
        "regime": scored.composite.regime.value,
        "raw_sentiment": str(scored.signals.sentiment.score),
        "raw_strength": str(scored.signals.strength.score),
        "raw_vp": str(scored.signals.volume_profile.score),
        "raw_drl": str(scored.signals.drl.score),
        "contrib_sentiment": str(contributions.get("sentiment", Decimal("0"))),
        "contrib_strength": str(contributions.get("strength", Decimal("0"))),
        "contrib_vp": str(contributions.get("volume_profile", Decimal("0"))),
        "contrib_drl": str(contributions.get("drl", Decimal("0"))),
    }
