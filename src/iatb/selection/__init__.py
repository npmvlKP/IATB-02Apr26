"""
Instrument auto-selection via multi-factor scoring.

Fuses sentiment, market strength, volume profile, and DRL backtest
conclusions into regime-aware composite scores for ranked selection.
"""

from iatb.selection.composite_score import (
    CompositeResult,
    RegimeWeights,
    SignalScores,
    compute_composite_score,
)
from iatb.selection.drl_signal import (
    BacktestConclusion,
    DRLSignalOutput,
    compute_drl_signal,
    compute_drl_signal_from_agent,
)
from iatb.selection.instrument_scorer import (
    FilterConfig,
    InstrumentScorer,
    InstrumentSignals,
    ScoredInstrument,
)
from iatb.selection.ranking import (
    RankedInstrument,
    RankingConfig,
    SelectionResult,
    rank_and_select,
)
from iatb.selection.sentiment_signal import (
    SentimentSignalInput,
    SentimentSignalOutput,
    compute_sentiment_signal,
)
from iatb.selection.strength_signal import (
    StrengthSignalInput,
    StrengthSignalOutput,
    compute_strength_signal,
)
from iatb.selection.volume_profile_signal import (
    ProfileShape,
    VolumeProfileSignalInput,
    VolumeProfileSignalOutput,
    classify_profile_shape,
    compute_volume_profile_signal,
)

__all__ = [
    # composite_score
    "CompositeResult",
    "RegimeWeights",
    "SignalScores",
    "compute_composite_score",
    # drl_signal
    "BacktestConclusion",
    "DRLSignalOutput",
    "compute_drl_signal",
    "compute_drl_signal_from_agent",
    # instrument_scorer
    "FilterConfig",
    "InstrumentScorer",
    "InstrumentSignals",
    "ScoredInstrument",
    # ranking
    "RankedInstrument",
    "RankingConfig",
    "SelectionResult",
    "rank_and_select",
    # sentiment_signal
    "SentimentSignalInput",
    "SentimentSignalOutput",
    "compute_sentiment_signal",
    # strength_signal
    "StrengthSignalInput",
    "StrengthSignalOutput",
    "compute_strength_signal",
    # volume_profile_signal
    "ProfileShape",
    "VolumeProfileSignalInput",
    "VolumeProfileSignalOutput",
    "classify_profile_shape",
    "compute_volume_profile_signal",
]
