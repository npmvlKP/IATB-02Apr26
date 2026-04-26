"""Tests for selection.instrument_scorer module."""

from __future__ import annotations

from decimal import Decimal

from iatb.core.enums import Exchange
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection.composite_score import (
    CompositeResult,
    RegimeWeights,
)
from iatb.selection.drl_signal import DRLSignalOutput
from iatb.selection.instrument_scorer import (
    InstrumentScorer,
    InstrumentSignals,
    ScoredInstrument,
    _build_metadata,
    _normalize_signals_across,
)
from iatb.selection.sentiment_signal import SentimentSignalOutput
from iatb.selection.strength_signal import StrengthSignalOutput
from iatb.selection.volume_profile_signal import VolumeProfileSignalOutput


def _make_sentiment(**kw: object) -> SentimentSignalOutput:
    defaults: dict[str, object] = {
        "score": Decimal("0.8"),
        "confidence": Decimal("0.9"),
        "directional_bias": "BULLISH",
        "metadata": {},
    }
    defaults.update(kw)
    return SentimentSignalOutput(**defaults)


def _make_strength(**kw: object) -> StrengthSignalOutput:
    defaults: dict[str, object] = {
        "score": Decimal("0.7"),
        "confidence": Decimal("0.8"),
        "regime": MarketRegime.BULL,
        "tradable": True,
        "metadata": {},
    }
    defaults.update(kw)
    return StrengthSignalOutput(**defaults)


def _make_vp(**kw: object) -> VolumeProfileSignalOutput:
    defaults: dict[str, object] = {
        "score": Decimal("0.6"),
        "confidence": Decimal("0.7"),
        "shape": "D",
        "poc_distance_pct": Decimal("1"),
        "va_width_pct": Decimal("5"),
        "metadata": {},
    }
    defaults.update(kw)
    return VolumeProfileSignalOutput(**defaults)


def _make_drl(**kw: object) -> DRLSignalOutput:
    defaults: dict[str, object] = {
        "score": Decimal("0.5"),
        "confidence": Decimal("0.6"),
        "robust": True,
        "metadata": {},
    }
    defaults.update(kw)
    return DRLSignalOutput(**defaults)


def _make_signals(
    symbol: str = "TEST",
    exchange: Exchange = Exchange.NSE,
    **overrides: object,
) -> InstrumentSignals:
    defaults: dict[str, object] = {
        "sentiment": _make_sentiment(),
        "strength": _make_strength(),
        "volume_profile": _make_vp(),
        "drl": _make_drl(),
    }
    defaults.update(overrides)
    return InstrumentSignals(symbol=symbol, exchange=exchange, **defaults)


def _make_strength_inputs() -> StrengthInputs:
    return StrengthInputs(
        breadth_ratio=Decimal("1.0"),
        regime=MarketRegime.SIDEWAYS,
        adx=Decimal("20"),
        volume_ratio=Decimal("1.0"),
        volatility_atr_pct=Decimal("0.03"),
    )


class TestInstrumentScorerInit:
    def test_default_init(self) -> None:
        scorer = InstrumentScorer()
        assert scorer is not None

    def test_custom_ranking_config(self) -> None:
        from iatb.selection.ranking import RankingConfig

        cfg = RankingConfig(top_n=10)
        scorer = InstrumentScorer(ranking_config=cfg)
        assert scorer is not None


class TestScoreInstruments:
    def test_empty_list(self) -> None:
        scorer = InstrumentScorer()
        result = scorer.score_instruments([], MarketRegime.BULL)
        assert result == []

    def test_single_instrument(self) -> None:
        scorer = InstrumentScorer()
        signals = [_make_signals()]
        result = scorer.score_instruments(signals, MarketRegime.BULL)
        assert len(result) == 1
        assert isinstance(result[0], ScoredInstrument)
        assert result[0].symbol == "TEST"

    def test_multiple_instruments(self) -> None:
        scorer = InstrumentScorer()
        signals = [_make_signals("A"), _make_signals("B")]
        result = scorer.score_instruments(signals, MarketRegime.BULL)
        assert len(result) == 2

    def test_composite_score_in_range(self) -> None:
        scorer = InstrumentScorer()
        signals = [_make_signals()]
        result = scorer.score_instruments(signals, MarketRegime.BULL)
        assert Decimal("0") <= result[0].composite.composite_score <= Decimal("1")

    def test_different_regimes(self) -> None:
        scorer = InstrumentScorer()
        signals = [_make_signals()]
        for regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]:
            result = scorer.score_instruments(signals, regime)
            assert len(result) == 1


class TestSelectTop:
    def test_basic_selection(self) -> None:
        scorer = InstrumentScorer()
        scored = scorer.score_instruments(
            [_make_signals("A"), _make_signals("B")],
            MarketRegime.BULL,
        )
        result = scorer.select_top(scored)
        assert result.total_candidates == 2

    def test_empty_scored(self) -> None:
        scorer = InstrumentScorer()
        result = scorer.select_top([])
        assert result.selected == []

    def test_with_correlations(self) -> None:
        scorer = InstrumentScorer()
        scored = scorer.score_instruments(
            [_make_signals("A"), _make_signals("B")],
            MarketRegime.BULL,
        )
        correlations = {("A", "B"): Decimal("0.9")}
        result = scorer.select_top(scored, correlations)
        assert result.total_candidates == 2


class TestScoreAndSelect:
    def test_convenience_method(self) -> None:
        scorer = InstrumentScorer()
        signals = [_make_signals("A")]
        result = scorer.score_and_select(signals, MarketRegime.BULL)
        assert result.total_candidates == 1


class TestNormalizeSignalsAcross:
    def test_empty(self) -> None:
        assert _normalize_signals_across([]) == []

    def test_single(self) -> None:
        signals = [_make_signals()]
        result = _normalize_signals_across(signals)
        assert len(result) == 1

    def test_scores_in_01(self) -> None:
        signals = [_make_signals("A"), _make_signals("B")]
        result = _normalize_signals_across(signals)
        for norm in result:
            assert Decimal("0") <= norm.sentiment_score <= Decimal("1")
            assert Decimal("0") <= norm.strength_score <= Decimal("1")
            assert Decimal("0") <= norm.volume_profile_score <= Decimal("1")
            assert Decimal("0") <= norm.drl_score <= Decimal("1")


class TestBuildMetadata:
    def test_metadata_keys(self) -> None:
        composite = CompositeResult(
            composite_score=Decimal("0.7"),
            regime=MarketRegime.BULL,
            weights_used=RegimeWeights(
                sentiment=Decimal("0.25"),
                strength=Decimal("0.25"),
                volume_profile=Decimal("0.25"),
                drl=Decimal("0.25"),
            ),
            component_contributions={
                "sentiment": Decimal("0.2"),
                "strength": Decimal("0.2"),
                "volume_profile": Decimal("0.15"),
                "drl": Decimal("0.15"),
            },
        )
        signals = _make_signals()
        scored = ScoredInstrument(
            symbol="TEST",
            exchange=Exchange.NSE,
            composite=composite,
            signals=signals,
        )
        metadata = _build_metadata(scored)
        assert "regime" in metadata
        assert "raw_sentiment" in metadata
        assert "raw_strength" in metadata
        assert "raw_vp" in metadata
        assert "raw_drl" in metadata
        assert "contrib_sentiment" in metadata

    def test_metadata_values(self) -> None:
        composite = CompositeResult(
            composite_score=Decimal("0.7"),
            regime=MarketRegime.BULL,
            weights_used=RegimeWeights(
                sentiment=Decimal("0.25"),
                strength=Decimal("0.25"),
                volume_profile=Decimal("0.25"),
                drl=Decimal("0.25"),
            ),
            component_contributions={},
        )
        signals = _make_signals()
        scored = ScoredInstrument(
            symbol="TEST",
            exchange=Exchange.NSE,
            composite=composite,
            signals=signals,
        )
        metadata = _build_metadata(scored)
        assert metadata["regime"] == "BULL"


class TestCustomWeights:
    def test_custom_weights_used(self) -> None:
        custom = {
            MarketRegime.BULL: RegimeWeights(
                sentiment=Decimal("1"),
                strength=Decimal("0"),
                volume_profile=Decimal("0"),
                drl=Decimal("0"),
            ),
        }
        scorer = InstrumentScorer(custom_weights=custom)
        signals = [_make_signals()]
        result = scorer.score_instruments(signals, MarketRegime.BULL)
        assert len(result) == 1


class TestInstrumentSignals:
    def test_with_strength_inputs(self) -> None:
        signals = _make_signals(strength_inputs=_make_strength_inputs())
        assert signals.strength_inputs is not None

    def test_without_strength_inputs(self) -> None:
        signals = _make_signals()
        assert signals.strength_inputs is None
