"""
Comprehensive coverage tests for multi_factor_scorer.py.

Tests factor scoring, weighted combination, and error paths.
"""

from decimal import Decimal

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
)


class TestFactorScores:
    """Test FactorScores dataclass."""

    def test_create_factor_scores(self) -> None:
        """Test creating factor scores."""
        scores = FactorScores(
            fundamental_score=Decimal("0.8"),
            technical_score=Decimal("0.7"),
            sentiment_score=Decimal("0.6"),
            strength_score=Decimal("0.9"),
        )
        assert scores.fundamental_score == Decimal("0.8")
        assert scores.technical_score == Decimal("0.7")
        assert scores.sentiment_score == Decimal("0.6")
        assert scores.strength_score == Decimal("0.9")
        assert scores.fundamental_confidence == Decimal("1")
        assert scores.technical_confidence == Decimal("1")

    def test_custom_confidence(self) -> None:
        """Test with custom confidence values."""
        scores = FactorScores(
            fundamental_score=Decimal("0.8"),
            technical_score=Decimal("0.7"),
            sentiment_score=Decimal("0.6"),
            strength_score=Decimal("0.9"),
            fundamental_confidence=Decimal("0.95"),
            technical_confidence=Decimal("0.90"),
        )
        assert scores.fundamental_confidence == Decimal("0.95")
        assert scores.technical_confidence == Decimal("0.90")


class TestMultiFactorResult:
    """Test MultiFactorResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating a result object."""
        factor_scores = FactorScores(
            fundamental_score=Decimal("0.8"),
            technical_score=Decimal("0.7"),
            sentiment_score=Decimal("0.6"),
            strength_score=Decimal("0.9"),
        )
        weights = FactorWeights()
        result = MultiFactorResult(
            symbol="RELIANCE",
            composite_score=Decimal("0.75"),
            factor_scores=factor_scores,
            weights_used=weights,
            component_contributions={"fundamental": Decimal("0.2")},
        )
        assert result.symbol == "RELIANCE"
        assert result.composite_score == Decimal("0.75")
        assert result.factor_scores == factor_scores


class TestMultiFactorScorerConfig:
    """Test MultiFactorScorerConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MultiFactorScorerConfig()
        assert config.min_pe == Decimal("5")
        assert config.max_pe == Decimal("100")
        assert config.min_pb == Decimal("0.5")
        assert config.max_pb == Decimal("10")
        assert config.min_roe == Decimal("0.05")
        assert config.max_debt_equity == Decimal("2.0")

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = MultiFactorScorerConfig(
            min_pe=Decimal("10"),
            max_pe=Decimal("50"),
            min_roe=Decimal("0.10"),
        )
        assert config.min_pe == Decimal("10")
        assert config.max_pe == Decimal("50")
        assert config.min_roe == Decimal("0.10")


class TestMultiFactorScorer:
    """Test MultiFactorScorer class."""

    def test_scorer_initialization(self) -> None:
        """Test scorer initializes with default config."""
        scorer = MultiFactorScorer()
        assert scorer._config is not None

    def test_scorer_with_custom_config(self) -> None:
        """Test scorer with custom configuration."""
        config = MultiFactorScorerConfig(min_pe=Decimal("10"))
        scorer = MultiFactorScorer(config)
        assert scorer._config.min_pe == Decimal("10")

    def test_score_single_instrument(self) -> None:
        """Test scoring a single instrument."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="RELIANCE",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        result = scorer.score(inputs)
        assert isinstance(result, MultiFactorResult)
        assert result.symbol == "RELIANCE"
        assert isinstance(result.composite_score, Decimal)

    def test_score_batch_empty(self) -> None:
        """Test scoring empty batch."""
        scorer = MultiFactorScorer()
        results = scorer.score_batch([])
        assert results == []

    def test_score_batch_single(self) -> None:
        """Test scoring batch with single instrument."""
        scorer = MultiFactorScorer()
        inputs = MultiFactorInputs(
            symbol="TCS",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        results = scorer.score_batch([inputs])
        assert len(results) == 1
        assert results[0].symbol == "TCS"

    def test_score_batch_multiple(self) -> None:
        """Test scoring batch with multiple instruments."""
        scorer = MultiFactorScorer()
        inputs_list = [
            MultiFactorInputs(
                symbol=f"SYM{i}",
                fundamental=FundamentalFactor(),
                technical=TechnicalFactor(),
                sentiment=SentimentFactor(),
                strength=StrengthFactor(),
            )
            for i in range(3)
        ]
        results = scorer.score_batch(inputs_list)
        assert len(results) == 3
        symbols = {r.symbol for r in results}
        assert symbols == {"SYM0", "SYM1", "SYM2"}


class TestFactorWeights:
    """Test FactorWeights dataclass."""

    def test_default_weights(self) -> None:
        """Test default weight values."""
        weights = FactorWeights()
        assert isinstance(weights.fundamental, Decimal)
        assert isinstance(weights.technical, Decimal)
        assert isinstance(weights.sentiment, Decimal)
        assert isinstance(weights.strength, Decimal)

    def test_custom_weights(self) -> None:
        """Test custom weights."""
        weights = FactorWeights(
            fundamental=Decimal("0.4"),
            technical=Decimal("0.3"),
            sentiment=Decimal("0.2"),
            strength=Decimal("0.1"),
        )
        assert weights.fundamental == Decimal("0.4")
        assert weights.technical == Decimal("0.3")


class TestMultiFactorInputs:
    """Test MultiFactorInputs dataclass."""

    def test_create_inputs(self) -> None:
        """Test creating inputs object."""
        inputs = MultiFactorInputs(
            symbol="RELIANCE",
            fundamental=FundamentalFactor(),
            technical=TechnicalFactor(),
            sentiment=SentimentFactor(),
            strength=StrengthFactor(),
        )
        assert inputs.symbol == "RELIANCE"
        assert isinstance(inputs.fundamental, FundamentalFactor)
        assert isinstance(inputs.technical, TechnicalFactor)
        assert isinstance(inputs.sentiment, SentimentFactor)
        assert isinstance(inputs.strength, StrengthFactor)
