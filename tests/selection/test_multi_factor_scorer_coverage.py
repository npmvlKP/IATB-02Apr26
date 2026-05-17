"""Tests for selection/multi_factor_scorer.py — factor scoring."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.multi_factor_scorer import (
    FactorScores,
    FactorWeights,
    FundamentalFactor,
    MultiFactorInputs,
    MultiFactorResult,
    MultiFactorScorer,
    MultiFactorScorerConfig,
    SentimentFactor,
    StrengthFactor,
    TechnicalFactor,
    _rank_percentile,
)


def _default_inputs(symbol: str = "TEST") -> MultiFactorInputs:
    return MultiFactorInputs(
        symbol=symbol,
        fundamental=FundamentalFactor(pe_ratio=Decimal("20"), roe=Decimal("0.15")),
        technical=TechnicalFactor(rsi=Decimal("50"), macd_signal=Decimal("0.3")),
        sentiment=SentimentFactor(
            news_score=Decimal("0.5"), social_score=Decimal("0.5")
        ),
        strength=StrengthFactor(relative_strength=Decimal("0.6")),
    )


class TestFactorWeights:
    def test_valid_weights(self) -> None:
        w = FactorWeights()
        total = w.fundamental + w.technical + w.sentiment + w.strength
        assert total == Decimal("1")

    def test_weights_not_summing_to_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="must sum to 1.0"):
            FactorWeights(fundamental=Decimal("0.5"), technical=Decimal("0.5"))

    def test_negative_weight_raises(self) -> None:
        with pytest.raises(ConfigError, match="weight.*must be in"):
            FactorWeights(
                fundamental=Decimal("-0.1"),
                technical=Decimal("0.5"),
                sentiment=Decimal("0.3"),
                strength=Decimal("0.3"),
            )


class TestMultiFactorScorer:
    def test_single_instrument_score(self) -> None:
        scorer = MultiFactorScorer()
        result = scorer.score(_default_inputs())
        assert isinstance(result, MultiFactorResult)
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_composite_score_bounded(self) -> None:
        scorer = MultiFactorScorer()
        result = scorer.score(_default_inputs())
        assert result.composite_score >= Decimal("0")
        assert result.composite_score <= Decimal("1")

    def test_factor_scores_populated(self) -> None:
        scorer = MultiFactorScorer()
        result = scorer.score(_default_inputs())
        assert isinstance(result.factor_scores, FactorScores)
        assert result.factor_scores.fundamental_score >= Decimal("0")
        assert result.factor_scores.technical_score >= Decimal("0")

    def test_component_contributions(self) -> None:
        scorer = MultiFactorScorer()
        result = scorer.score(_default_inputs())
        assert "fundamental" in result.component_contributions
        assert "technical" in result.component_contributions

    def test_batch_scoring(self) -> None:
        scorer = MultiFactorScorer()
        inputs_list = [_default_inputs("A"), _default_inputs("B")]
        results = scorer.score_batch(inputs_list)
        assert len(results) == 2
        assert results[0].symbol == "A"
        assert results[1].symbol == "B"

    def test_empty_batch(self) -> None:
        scorer = MultiFactorScorer()
        assert scorer.score_batch([]) == []

    def test_none_fundamental_defaults(self) -> None:
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="NONE_F",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.composite_score >= Decimal("0")

    def test_rsi_oversold(self) -> None:
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="OS",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("20")),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.composite_score >= Decimal("0")

    def test_rsi_overbought(self) -> None:
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="OB",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("80")),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.composite_score >= Decimal("0")

    def test_custom_weights(self) -> None:
        weights = FactorWeights(
            fundamental=Decimal("0.5"),
            technical=Decimal("0.2"),
            sentiment=Decimal("0.2"),
            strength=Decimal("0.1"),
        )
        cfg = MultiFactorScorerConfig(weights=weights)
        scorer = MultiFactorScorer(cfg)
        result = scorer.score(_default_inputs())
        assert result.weights_used == weights


class TestRankPercentile:
    def test_simple_values(self) -> None:
        result = _rank_percentile([Decimal("1"), Decimal("3"), Decimal("5")])
        assert len(result) == 3
        assert result[2] == Decimal("1")

    def test_empty_list(self) -> None:
        assert _rank_percentile([]) == []

    def test_single_value(self) -> None:
        result = _rank_percentile([Decimal("5")])
        assert result == [Decimal("0.5")]

    def test_all_equal(self) -> None:
        result = _rank_percentile([Decimal("1"), Decimal("1"), Decimal("1")])
        assert len(result) == 3
