"""
Tests for multi_factor_scorer module.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.multi_factor_scorer import (
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


class TestFactorWeights:
    """Test FactorWeights dataclass."""

    def test_default_weights_sum_to_one(self) -> None:
        """Test that default weights sum to 1.0."""
        weights = FactorWeights()
        total = weights.fundamental + weights.technical + weights.sentiment + weights.strength
        assert total == Decimal("1")

    def test_custom_weights_sum_to_one(self) -> None:
        """Test that custom weights sum to 1.0."""
        weights = FactorWeights(
            fundamental=Decimal("0.3"),
            technical=Decimal("0.3"),
            sentiment=Decimal("0.2"),
            strength=Decimal("0.2"),
        )
        total = weights.fundamental + weights.technical + weights.sentiment + weights.strength
        assert total == Decimal("1")

    def test_weights_sum_not_one_raises_error(self) -> None:
        """Test that weights not summing to 1.0 raises ConfigError."""
        with pytest.raises(ConfigError, match="factor weights must sum to 1.0, got 1.2"):
            FactorWeights(
                fundamental=Decimal("0.3"),
                technical=Decimal("0.3"),
                sentiment=Decimal("0.3"),
                strength=Decimal("0.3"),
            )

    def test_negative_weight_raises_error(self) -> None:
        """Test that negative weight raises ConfigError."""
        with pytest.raises(ConfigError, match="must be in \\[0, 1\\]"):
            FactorWeights(
                fundamental=Decimal("-0.1"),
                technical=Decimal("0.4"),
                sentiment=Decimal("0.4"),
                strength=Decimal("0.3"),
            )

    def test_weight_greater_than_one_raises_error(self) -> None:
        """Test that weight > 1.0 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be in \\[0, 1\\]"):
            FactorWeights(
                fundamental=Decimal("1.5"),
                technical=Decimal("-0.2"),
                sentiment=Decimal("-0.2"),
                strength=Decimal("-0.1"),
            )


class TestRankPercentile:
    """Test _rank_percentile function."""

    def test_empty_list(self) -> None:
        """Test with empty list."""
        result = _rank_percentile([])
        assert result == []

    def test_single_value(self) -> None:
        """Test with single value."""
        result = _rank_percentile([Decimal("0.5")])
        assert result == [Decimal("0.5")]

    def test_multiple_values(self) -> None:
        """Test with multiple values."""
        values = [Decimal("0.1"), Decimal("0.5"), Decimal("0.9"), Decimal("0.3")]
        result = _rank_percentile(values)
        assert len(result) == 4
        assert all(Decimal("0") <= v <= Decimal("1") for v in result)

    def test_identical_values(self) -> None:
        """Test with identical values."""
        values = [Decimal("0.5"), Decimal("0.5"), Decimal("0.5")]
        result = _rank_percentile(values)
        assert len(result) == 3
        assert result == [Decimal("0.0"), Decimal("0.5"), Decimal("1.0")]

    def test_ascending_order(self) -> None:
        """Test with values in ascending order."""
        values = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.4")]
        result = _rank_percentile(values)
        # Check that values are in ascending order and in range [0, 1]
        assert len(result) == 4
        assert result[0] == Decimal("0")
        assert result[-1] == Decimal("1")
        assert all(Decimal("0") <= v <= Decimal("1") for v in result)


class TestMultiFactorScorerConfig:
    """Test MultiFactorScorerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = MultiFactorScorerConfig()
        assert config.min_pe == Decimal("5")
        assert config.max_pe == Decimal("100")
        assert config.rsi_oversold == Decimal("30")
        assert config.rsi_overbought == Decimal("70")

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = MultiFactorScorerConfig(
            min_pe=Decimal("10"),
            max_pe=Decimal("50"),
            min_roe=Decimal("0.1"),
        )
        assert config.min_pe == Decimal("10")
        assert config.max_pe == Decimal("50")
        assert config.min_roe == Decimal("0.1")


class TestMultiFactorScorer:
    """Test MultiFactorScorer class."""

    def test_score_with_complete_inputs(self) -> None:
        """Test scoring with complete inputs."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(
                pe_ratio=Decimal("15"),
                pb_ratio=Decimal("2"),
                roe=Decimal("0.15"),
                debt_to_equity=Decimal("0.5"),
                dividend_yield=Decimal("0.02"),
                earnings_growth=Decimal("0.1"),
            ),
            technical=TechnicalFactor(
                rsi=Decimal("50"),
                macd_signal=Decimal("0.1"),
                moving_average_cross=Decimal("0.8"),
                volume_trend=Decimal("1.2"),
                price_momentum=Decimal("0.05"),
            ),
            sentiment=SentimentFactor(
                news_score=Decimal("0.7"),
                social_score=Decimal("0.6"),
                analyst_rating=Decimal("0.8"),
            ),
            strength=StrengthFactor(
                relative_strength=Decimal("0.7"),
                sector_strength=Decimal("0.6"),
                volume_confirmation=Decimal("0.8"),
            ),
        )
        result = scorer.score(inputs)
        assert isinstance(result, MultiFactorResult)
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.composite_score <= Decimal("1")
        assert len(result.component_contributions) == 4

    def test_score_with_partial_inputs(self) -> None:
        """Test scoring with partial inputs."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("20")),
            technical=TechnicalFactor(rsi=Decimal("45")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        assert isinstance(result, MultiFactorResult)
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_score_with_no_fundamental_data(self) -> None:
        """Test scoring with no fundamental data returns default."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        assert result.factor_scores.fundamental_score == Decimal("0.5")

    def test_score_rsi_oversold(self) -> None:
        """Test scoring with oversold RSI."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("25")),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.factor_scores.technical_score > Decimal("0.7")

    def test_score_rsi_overbought(self) -> None:
        """Test scoring with overbought RSI."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(rsi=Decimal("80")),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.factor_scores.technical_score < Decimal("0.5")

    def test_score_batch_empty(self) -> None:
        """Test batch scoring with empty list."""
        scorer = MultiFactorScorer()
        results = scorer.score_batch([])
        assert results == []

    def test_score_batch_multiple_instruments(self) -> None:
        """Test batch scoring with multiple instruments."""
        scorer = MultiFactorScorer()
        inputs_list = [
            MultiFactorInputs(
                symbol=f"TEST{i}",
                fundamental=FundamentalFactor(pe_ratio=Decimal(str(10 + i))),
                technical=TechnicalFactor(rsi=Decimal(str(40 + i * 5))),
                sentiment=SentimentFactor(news_score=Decimal(str(0.5 + i * 0.1))),
                strength=StrengthFactor(relative_strength=Decimal(str(0.5 + i * 0.1))),
            )
            for i in range(3)
        ]
        results = scorer.score_batch(inputs_list)
        assert len(results) == 3
        assert all(isinstance(r, MultiFactorResult) for r in results)
        assert [r.symbol for r in results] == ["TEST0", "TEST1", "TEST2"]

    def test_score_batch_normalizes_scores(self) -> None:
        """Test that batch scoring normalizes across instruments."""
        scorer = MultiFactorScorer()
        inputs_list = [
            MultiFactorInputs(
                symbol=f"TEST{i}",
                fundamental=FundamentalFactor(pe_ratio=Decimal(str(10 + i * 10))),
                technical=TechnicalFactor(),
                sentiment=SentimentFactor(),
                strength=StrengthFactor(),
            )
            for i in range(3)
        ]
        results = scorer.score_batch(inputs_list)
        fundamental_scores = [r.factor_scores.fundamental_score for r in results]
        assert len(set(fundamental_scores)) > 1

    def test_custom_weights_affect_score(self) -> None:
        """Test that custom weights affect composite score."""
        config = MultiFactorScorerConfig(
            weights=FactorWeights(
                fundamental=Decimal("0.5"),
                technical=Decimal("0.3"),
                sentiment=Decimal("0.1"),
                strength=Decimal("0.1"),
            )
        )
        scorer = MultiFactorScorer(config)
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("15")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        assert result.weights_used.fundamental == Decimal("0.5")

    def test_component_contributions_sum_to_composite(self) -> None:
        """Test that component contributions sum to composite score."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("15")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        contributions_sum = sum(result.component_contributions.values())
        assert abs(contributions_sum - result.composite_score) < Decimal("0.01")

    def test_score_clamped_to_zero_one(self) -> None:
        """Test that scores are clamped to [0, 1]."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("15")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(
                news_score=Decimal("2.0"),
                social_score=Decimal("2.0"),
                analyst_rating=Decimal("2.0"),
            ),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_negative_sentiment_score(self) -> None:
        """Test scoring with negative sentiment."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("15")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(
                news_score=Decimal("-0.5"),
                social_score=Decimal("-0.5"),
                analyst_rating=Decimal("-0.5"),
            ),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )
        result = scorer.score(inputs)
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_extreme_fundamental_values(self) -> None:
        """Test scoring with extreme fundamental values."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(
                pe_ratio=Decimal("200"), pb_ratio=Decimal("50"), roe=Decimal("1.0")
            ),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert Decimal("0") <= result.factor_scores.fundamental_score <= Decimal("1")

    def test_zero_debt_equity(self) -> None:
        """Test scoring with zero debt-to-equity."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(debt_to_equity=Decimal("0")),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.factor_scores.fundamental_score > Decimal("0.8")

    def test_high_dividend_yield(self) -> None:
        """Test scoring with high dividend yield."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(dividend_yield=Decimal("0.1")),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert result.factor_scores.fundamental_score > Decimal("0.5")
