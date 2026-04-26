"""Tests for selection.composite_score module."""

from __future__ import annotations

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.selection.composite_score import (
    CompositeResult,
    RegimeWeights,
    SignalScores,
    _gated,
    _validate_signals,
    _weights_for_regime,
    compute_composite_score,
)


class TestRegimeWeights:
    def test_valid(self) -> None:
        w = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )
        assert w is not None

    def test_not_summing_to_one(self) -> None:
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            RegimeWeights(
                sentiment=Decimal("0.6"),
                strength=Decimal("0.5"),
                volume_profile=Decimal("0"),
                drl=Decimal("0"),
            )

    def test_negative(self) -> None:
        with pytest.raises(ConfigError, match="cannot be negative"):
            RegimeWeights(
                sentiment=Decimal("-0.25"),
                strength=Decimal("0.75"),
                volume_profile=Decimal("0.25"),
                drl=Decimal("0.25"),
            )

    def test_slightly_off_one(self) -> None:
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            RegimeWeights(
                sentiment=Decimal("0.26"),
                strength=Decimal("0.25"),
                volume_profile=Decimal("0.25"),
                drl=Decimal("0.25"),
            )

    def test_frozen(self) -> None:
        w = RegimeWeights(
            sentiment=Decimal("0.25"),
            strength=Decimal("0.25"),
            volume_profile=Decimal("0.25"),
            drl=Decimal("0.25"),
        )
        with pytest.raises(AttributeError):
            w.sentiment = Decimal("0.5")


class TestValidateSignals:
    def test_out_of_range_high(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("1.5"),
            sentiment_confidence=Decimal("0.5"),
            strength_score=Decimal("0.5"),
            strength_confidence=Decimal("0.5"),
            volume_profile_score=Decimal("0.5"),
            volume_profile_confidence=Decimal("0.5"),
            drl_score=Decimal("0.5"),
            drl_confidence=Decimal("0.5"),
        )
        with pytest.raises(ConfigError, match="must be in"):
            _validate_signals(signals)

    def test_out_of_range_negative(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("-0.1"),
            sentiment_confidence=Decimal("0.5"),
            strength_score=Decimal("0.5"),
            strength_confidence=Decimal("0.5"),
            volume_profile_score=Decimal("0.5"),
            volume_profile_confidence=Decimal("0.5"),
            drl_score=Decimal("0.5"),
            drl_confidence=Decimal("0.5"),
        )
        with pytest.raises(ConfigError, match="must be in"):
            _validate_signals(signals)

    def test_confidence_out_of_range(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("0.5"),
            sentiment_confidence=Decimal("1.5"),
            strength_score=Decimal("0.5"),
            strength_confidence=Decimal("0.5"),
            volume_profile_score=Decimal("0.5"),
            volume_profile_confidence=Decimal("0.5"),
            drl_score=Decimal("0.5"),
            drl_confidence=Decimal("0.5"),
        )
        with pytest.raises(ConfigError, match="must be in"):
            _validate_signals(signals)

    def test_valid_signals(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("0.5"),
            sentiment_confidence=Decimal("0.5"),
            strength_score=Decimal("0.5"),
            strength_confidence=Decimal("0.5"),
            volume_profile_score=Decimal("0.5"),
            volume_profile_confidence=Decimal("0.5"),
            drl_score=Decimal("0.5"),
            drl_confidence=Decimal("0.5"),
        )
        _validate_signals(signals)

    def test_boundary_0(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("0"),
            sentiment_confidence=Decimal("0"),
            strength_score=Decimal("0"),
            strength_confidence=Decimal("0"),
            volume_profile_score=Decimal("0"),
            volume_profile_confidence=Decimal("0"),
            drl_score=Decimal("0"),
            drl_confidence=Decimal("0"),
        )
        _validate_signals(signals)

    def test_boundary_1(self) -> None:
        signals = SignalScores(
            sentiment_score=Decimal("1"),
            sentiment_confidence=Decimal("1"),
            strength_score=Decimal("1"),
            strength_confidence=Decimal("1"),
            volume_profile_score=Decimal("1"),
            volume_profile_confidence=Decimal("1"),
            drl_score=Decimal("1"),
            drl_confidence=Decimal("1"),
        )
        _validate_signals(signals)


class TestComputeCompositeScore:
    def _make_signals(
        self,
        score: Decimal = Decimal("0.5"),
        confidence: Decimal = Decimal("0.5"),
    ) -> SignalScores:
        return SignalScores(
            sentiment_score=score,
            sentiment_confidence=confidence,
            strength_score=score,
            strength_confidence=confidence,
            volume_profile_score=score,
            volume_profile_confidence=confidence,
            drl_score=score,
            drl_confidence=confidence,
        )

    def test_bull_regime(self) -> None:
        signals = self._make_signals(Decimal("0.8"), Decimal("0.9"))
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert isinstance(result, CompositeResult)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_bear_regime(self) -> None:
        signals = self._make_signals()
        result = compute_composite_score(signals, MarketRegime.BEAR)
        assert isinstance(result, CompositeResult)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_sideways_regime(self) -> None:
        signals = self._make_signals()
        result = compute_composite_score(signals, MarketRegime.SIDEWAYS)
        assert isinstance(result, CompositeResult)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_custom_weights(self) -> None:
        signals = self._make_signals()
        custom = RegimeWeights(
            sentiment=Decimal("1"),
            strength=Decimal("0"),
            volume_profile=Decimal("0"),
            drl=Decimal("0"),
        )
        result = compute_composite_score(signals, MarketRegime.BULL, custom_weights=custom)
        assert result.composite_score >= Decimal("0")
        assert result.weights_used is custom

    def test_zero_confidence_gates(self) -> None:
        signals = self._make_signals(confidence=Decimal("0"))
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert result.composite_score == Decimal("0")

    def test_high_confidence(self) -> None:
        signals = self._make_signals(Decimal("0.9"), Decimal("0.9"))
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert result.composite_score > Decimal("0")

    def test_component_contributions(self) -> None:
        signals = self._make_signals()
        result = compute_composite_score(signals, MarketRegime.BULL)
        expected_keys = {"sentiment", "strength", "volume_profile", "drl"}
        assert expected_keys.issubset(result.component_contributions.keys())

    def test_regime_in_result(self) -> None:
        signals = self._make_signals()
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert result.regime == MarketRegime.BULL

    def test_all_zero_signals(self) -> None:
        signals = self._make_signals(Decimal("0"), Decimal("0"))
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert result.composite_score == Decimal("0")

    def test_all_max_signals(self) -> None:
        signals = self._make_signals(Decimal("1"), Decimal("1"))
        result = compute_composite_score(signals, MarketRegime.BULL)
        assert result.composite_score == Decimal("1")


class TestGated:
    def test_basic(self) -> None:
        result = _gated(Decimal("0.5"), Decimal("0.8"), Decimal("0.9"))
        assert isinstance(result, Decimal)

    def test_zero_weight(self) -> None:
        result = _gated(Decimal("0"), Decimal("0.8"), Decimal("0.9"))
        assert result == Decimal("0")

    def test_zero_confidence(self) -> None:
        result = _gated(Decimal("0.5"), Decimal("0.8"), Decimal("0"))
        assert result == Decimal("0")

    def test_zero_score(self) -> None:
        result = _gated(Decimal("0.5"), Decimal("0"), Decimal("0.9"))
        assert result == Decimal("0")


class TestWeightsForRegime:
    def test_unknown_raises(self) -> None:
        with pytest.raises(ConfigError, match="no weight preset"):
            _weights_for_regime("UNKNOWN_REGIME")

    def test_bull_weights(self) -> None:
        w = _weights_for_regime(MarketRegime.BULL)
        assert w.drl > w.sentiment

    def test_sideways_weights(self) -> None:
        w = _weights_for_regime(MarketRegime.SIDEWAYS)
        assert w.volume_profile > w.sentiment

    def test_bear_weights(self) -> None:
        w = _weights_for_regime(MarketRegime.BEAR)
        assert w.sentiment == w.strength
