"""
Comprehensive coverage tests for multi_factor_scorer.py.

Tests multi-factor scoring engine for instrument selection.
"""

from decimal import Decimal

import pytest
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
)


class TestFundamentalFactor:
    """Test fundamental factor dataclass."""

    def test_create_factor(self):
        """Test creating fundamental factor."""
        factor = FundamentalFactor(
            pe_ratio=Decimal("15"),
            pb_ratio=Decimal("2"),
            roe=Decimal("0.15"),
        )

        assert factor.pe_ratio == Decimal("15")
        assert factor.roe == Decimal("0.15")


class TestTechnicalFactor:
    """Test technical factor dataclass."""

    def test_create_factor(self):
        """Test creating technical factor."""
        factor = TechnicalFactor(
            rsi=Decimal("50"),
            macd_signal=Decimal("0.1"),
            bollinger_position=Decimal("0.5"),
        )

        assert factor.rsi == Decimal("50")


class TestSentimentFactor:
    """Test sentiment factor dataclass."""

    def test_create_factor(self):
        """Test creating sentiment factor."""
        factor = SentimentFactor(
            news_score=Decimal("0.6"),
            social_score=Decimal("0.4"),
            analyst_rating=Decimal("0.5"),
        )

        assert factor.news_score == Decimal("0.6")


class TestStrengthFactor:
    """Test strength factor dataclass."""

    def test_create_factor(self):
        """Test creating strength factor."""
        factor = StrengthFactor(
            relative_strength=Decimal("0.7"),
            sector_strength=Decimal("0.6"),
            volume_confirmation=Decimal("0.8"),
        )

        assert factor.relative_strength == Decimal("0.7")


class TestMultiFactorInputs:
    """Test multi-factor inputs dataclass."""

    def test_create_inputs(self):
        """Test creating multi-factor inputs."""
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )

        assert inputs.symbol == "TEST"


class TestFactorWeights:
    """Test factor weights dataclass."""

    def test_default_weights(self):
        """Test default weights sum to 1.0."""
        weights = FactorWeights()
        total = (
            weights.fundamental
            + weights.technical
            + weights.sentiment
            + weights.strength
        )
        assert total == Decimal("1")

    def test_custom_weights_sum_to_one(self):
        """Test custom weights that sum to 1.0."""
        weights = FactorWeights(
            fundamental=Decimal("0.4"),
            technical=Decimal("0.3"),
            sentiment=Decimal("0.2"),
            strength=Decimal("0.1"),
        )

        total = (
            weights.fundamental
            + weights.technical
            + weights.sentiment
            + weights.strength
        )
        assert total == Decimal("1")

    def test_invalid_weights_raise_error(self):
        """Test that weights not summing to 1.0 raise ConfigError."""
        with pytest.raises(Exception):  # ConfigError
            FactorWeights(
                fundamental=Decimal("0.5"),
                technical=Decimal("0.3"),
                sentiment=Decimal("0.3"),
                strength=Decimal("0.1"),
            )


class TestMultiFactorScorerConfig:
    """Test multi-factor scorer configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MultiFactorScorerConfig()
        assert config.min_pe == Decimal("5")
        assert config.max_pe == Decimal("100")
        assert config.min_roe == Decimal("0.05")


class TestMultiFactorScorer:
    """Test multi-factor scoring engine."""

    def test_score_single_instrument(self):
        """Test scoring a single instrument."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("20"), roe=Decimal("0.10")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )

        result = scorer.score(inputs)

        assert isinstance(result, MultiFactorResult)
        assert result.symbol == "TEST"
        assert Decimal("0") <= result.composite_score <= Decimal("1")

    def test_score_batch_instruments(self):
        """Test scoring multiple instruments."""
        scorer = MultiFactorScorer()
        inputs_list = [
            MultiFactorInputs(
                symbol="TEST1",
                fundamental=FundamentalFactor(
                    pe_ratio=Decimal("20"), roe=Decimal("0.10")
                ),
                technical=TechnicalFactor(rsi=Decimal("50")),
                sentiment=SentimentFactor(news_score=Decimal("0.5")),
                strength=StrengthFactor(relative_strength=Decimal("0.5")),
            ),
            MultiFactorInputs(
                symbol="TEST2",
                fundamental=FundamentalFactor(
                    pe_ratio=Decimal("25"), roe=Decimal("0.08")
                ),
                technical=TechnicalFactor(rsi=Decimal("60")),
                sentiment=SentimentFactor(news_score=Decimal("0.6")),
                strength=StrengthFactor(relative_strength=Decimal("0.6")),
            ),
        ]

        results = scorer.score_batch(inputs_list)

        assert len(results) == 2
        assert all(isinstance(r, MultiFactorResult) for r in results)

    def test_score_empty_batch_returns_empty(self):
        """Test that empty batch returns empty list."""
        scorer = MultiFactorScorer()
        results = scorer.score_batch([])
        assert results == []

    def test_score_with_custom_config(self):
        """Test scoring with custom configuration."""
        config = MultiFactorScorerConfig(min_roe=Decimal("0.15"))
        scorer = MultiFactorScorer(config)
        inputs = MultiFactorInputs(
            symbol="TEST",
            fundamental=FundamentalFactor(pe_ratio=Decimal("20"), roe=Decimal("0.20")),
            technical=TechnicalFactor(rsi=Decimal("50")),
            sentiment=SentimentFactor(news_score=Decimal("0.5")),
            strength=StrengthFactor(relative_strength=Decimal("0.5")),
        )

        result = scorer.score(inputs)

        assert result.composite_score >= Decimal("0")
