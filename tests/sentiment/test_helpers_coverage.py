"""Comprehensive coverage tests for sentiment helper functions to achieve 100% coverage."""

from decimal import Decimal, InvalidOperation
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentScore
from iatb.sentiment.helpers import (
    compute_weighted_ensemble,
    parse_finbert_label_score,
    resolve_aion_predictor,
    resolve_finbert_predictor,
    validate_and_parse_aion_prediction,
)

# =============================================================================
# resolve_aion_predictor Tests
# =============================================================================


class TestResolveAionPredictor:
    """Test cases for resolve_aion_predictor function."""

    def test_resolve_aion_predictor_with_predict_function(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test resolve_aion_predictor with module exposing predict function."""
        mock_predict = MagicMock(return_value={"label": "POSITIVE", "score": "0.85"})
        mock_module = MagicMock()
        mock_module.predict = mock_predict
        monkeypatch.setattr("iatb.sentiment.helpers.importlib.import_module", lambda _: mock_module)
        predictor = resolve_aion_predictor()
        assert predictor is mock_predict
        assert predictor("test") == {"label": "POSITIVE", "score": "0.85"}

    def test_resolve_aion_predictor_with_aion_sentiment_class(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test resolve_aion_predictor with AionSentiment class."""
        mock_analyze = MagicMock(return_value={"label": "NEGATIVE", "score": "0.75"})
        mock_model = MagicMock()
        mock_model.predict = None  # Ensure predict is not found on model
        mock_model.analyze = mock_analyze
        mock_module = MagicMock()
        mock_module.AionSentiment = MagicMock(return_value=mock_model)
        # Ensure predict, analyze, analyze_sentiment are not found on module
        del mock_module.predict
        del mock_module.analyze
        del mock_module.analyze_sentiment
        monkeypatch.setattr("iatb.sentiment.helpers.importlib.import_module", lambda _: mock_module)
        predictor = resolve_aion_predictor()
        # The predictor should be the analyze method from the model instance
        result = predictor("test")
        assert result == {"label": "NEGATIVE", "score": "0.75"}

    def test_resolve_aion_predictor_with_analyze_function(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test resolve_aion_predictor with module exposing analyze function."""
        mock_analyze = MagicMock(return_value={"sentiment": "NEUTRAL", "confidence": "0.60"})
        mock_module = MagicMock()
        mock_module.analyze = mock_analyze
        mock_module.predict = None  # Ensure predict is not found
        mock_module.analyze_sentiment = None  # Ensure analyze_sentiment is not found
        monkeypatch.setattr("iatb.sentiment.helpers.importlib.import_module", lambda _: mock_module)
        predictor = resolve_aion_predictor()
        assert predictor is mock_analyze

    def test_resolve_aion_predictor_missing_dependency_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing aion-sentiment dependency raises ConfigError."""
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="aion-sentiment dependency is required"):
            resolve_aion_predictor()

    def test_resolve_aion_predictor_no_usable_interface_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that module installed but no usable interface raises ConfigError."""
        mock_module = MagicMock(spec_set=[])  # Empty module
        monkeypatch.setattr("iatb.sentiment.helpers.importlib.import_module", lambda _: mock_module)
        with pytest.raises(ConfigError, match="does not expose a usable prediction interface"):
            resolve_aion_predictor()


# =============================================================================
# validate_and_parse_aion_prediction Tests
# =============================================================================


class TestValidateAndParseAionPrediction:
    """Test cases for validate_and_parse_aion_prediction function."""

    def test_validate_and_parse_aion_prediction_dict_label_score(self) -> None:
        """Test parsing AION prediction from dict with label and score keys."""
        prediction = {"label": "POSITIVE", "score": 0.85}
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "POSITIVE"
        assert confidence == Decimal("0.85")

    def test_validate_and_parse_aion_prediction_dict_sentiment_confidence(self) -> None:
        """Test parsing AION prediction from dict with sentiment and confidence keys."""
        prediction = {"sentiment": "NEGATIVE", "confidence": 0.78}
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "NEGATIVE"
        assert confidence == Decimal("0.78")

    def test_validate_and_parse_aion_prediction_tuple(self) -> None:
        """Test parsing AION prediction from tuple."""
        prediction = ("BULLISH", "0.88")
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "BULLISH"
        assert confidence == Decimal("0.88")

    def test_validate_and_parse_aion_prediction_string(self) -> None:
        """Test parsing AION prediction from string - defaults confidence to 0.70."""
        prediction = "BEARISH"
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "BEARISH"
        assert confidence == Decimal("0.70")

    def test_validate_and_parse_aion_prediction_dict_only_label_key(self) -> None:
        """Edge: AION dict with only 'label' key - defaults confidence to 0.70."""
        prediction = {"label": "POSITIVE"}
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "POSITIVE"
        assert confidence == Decimal("0.70")

    def test_validate_and_parse_aion_prediction_dict_only_sentiment_key(self) -> None:
        """Edge: AION dict with only 'sentiment' key - defaults confidence to 0.70."""
        prediction = {"sentiment": "NEUTRAL"}
        label, confidence = validate_and_parse_aion_prediction(prediction)
        assert label == "NEUTRAL"
        assert confidence == Decimal("0.70")

    def test_validate_and_parse_aion_prediction_negative_confidence_raises(self) -> None:
        """Test that negative confidence raises ConfigError."""
        prediction = {"label": "POSITIVE", "score": -0.5}
        with pytest.raises(ConfigError, match="AION confidence cannot be negative"):
            validate_and_parse_aion_prediction(prediction)

    def test_validate_and_parse_aion_prediction_unsupported_format_raises(self) -> None:
        """Error: Unsupported AION prediction format raises ConfigError."""
        with pytest.raises(ConfigError, match="Unsupported AION prediction output format"):
            validate_and_parse_aion_prediction(123)

    def test_validate_and_parse_aion_prediction_tuple_single_element_raises(self) -> None:
        """Test that tuple with less than 2 elements falls through to unsupported format."""
        with pytest.raises(ConfigError, match="Unsupported AION prediction output format"):
            validate_and_parse_aion_prediction(("ONLY_ONE",))


# =============================================================================
# resolve_finbert_predictor Tests
# =============================================================================


class TestResolveFinbertPredictor:
    """Test cases for resolve_finbert_predictor function."""

    def test_resolve_finbert_predictor_with_valid_transformers_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test resolve_finbert_predictor with valid transformers mock."""
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = MagicMock(return_value=[{"label": "POSITIVE", "score": 0.95}])
        mock_transformers = MagicMock()
        mock_transformers.pipeline = mock_pipeline
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module", lambda _: mock_transformers
        )
        predictor = resolve_finbert_predictor("ProsusAI/finbert")
        assert callable(predictor)
        result = predictor("Test text")
        assert result == [{"label": "POSITIVE", "score": 0.95}]

    def test_resolve_finbert_predictor_missing_dependency_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing transformers dependency raises ConfigError."""
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module",
            lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
        )
        with pytest.raises(ConfigError, match="transformers dependency is required"):
            resolve_finbert_predictor("ProsusAI/finbert")

    def test_resolve_finbert_predictor_pipeline_unavailable_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that unavailable pipeline raises ConfigError."""
        mock_transformers = MagicMock(spec_set=["pipeline"])
        del mock_transformers.pipeline  # Remove pipeline attribute
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module", lambda _: mock_transformers
        )
        with pytest.raises(ConfigError, match="pipeline is unavailable"):
            resolve_finbert_predictor("ProsusAI/finbert")

    def test_resolve_finbert_predictor_oserror_dll_load_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test OSError during import (PyTorch DLL loading failure)."""
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module",
            lambda _: (_ for _ in ()).throw(OSError("DLL load failed")),
        )
        with pytest.raises(ConfigError, match="transformers/PyTorch dependency unavailable"):
            resolve_finbert_predictor("ProsusAI/finbert")

    def test_resolve_finbert_predictor_oserror_pipeline_creation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test OSError during pipeline creation (PyTorch DLL loading failure)."""
        mock_transformers = MagicMock()
        mock_transformers.pipeline.side_effect = OSError("DLL load failed during pipeline creation")
        monkeypatch.setattr(
            "iatb.sentiment.helpers.importlib.import_module", lambda _: mock_transformers
        )
        with pytest.raises(ConfigError, match="PyTorch unavailable"):
            resolve_finbert_predictor("ProsusAI/finbert")


# =============================================================================
# parse_finbert_label_score Tests
# =============================================================================


class TestParseFinbertLabelScore:
    """Test cases for parse_finbert_label_score function."""

    def test_parse_finbert_label_score_with_valid_prediction_list(self) -> None:
        """Test parse_finbert_label_score with valid prediction list."""
        predictions = [{"label": "POSITIVE", "score": 0.92}]
        label, confidence = parse_finbert_label_score(predictions)
        assert label == "POSITIVE"
        assert confidence == Decimal("0.92")

    def test_parse_finbert_label_score_negative_label(self) -> None:
        """Test parsing negative FinBERT prediction."""
        predictions = [{"label": "negative", "score": 0.81}]
        label, confidence = parse_finbert_label_score(predictions)
        assert label == "NEGATIVE"
        assert confidence == Decimal("0.81")

    def test_parse_finbert_label_score_neutral_label(self) -> None:
        """Test parsing neutral FinBERT prediction."""
        predictions = [{"label": "NEUTRAL", "score": 0.6}]
        label, confidence = parse_finbert_label_score(predictions)
        assert label == "NEUTRAL"
        assert confidence == Decimal("0.6")

    def test_parse_finbert_label_score_missing_label_defaults(self) -> None:
        """Test that missing label defaults to NEUTRAL."""
        predictions = [{"score": 0.5}]
        label, confidence = parse_finbert_label_score(predictions)
        assert label == "NEUTRAL"
        assert confidence == Decimal("0.5")

    def test_parse_finbert_label_score_missing_score_defaults(self) -> None:
        """Test that missing score defaults to 0."""
        predictions = [{"label": "POSITIVE"}]
        label, confidence = parse_finbert_label_score(predictions)
        assert label == "POSITIVE"
        assert confidence == Decimal("0")

    def test_parse_finbert_label_score_empty_predictions_raises(self) -> None:
        """Edge: Empty predictions list raises ConfigError."""
        with pytest.raises(ConfigError, match="at least one mapping prediction"):
            parse_finbert_label_score([])


# =============================================================================
# compute_weighted_ensemble Tests
# =============================================================================


class TestComputeWeightedEnsemble:
    """Test cases for compute_weighted_ensemble function."""

    def test_compute_weighted_ensemble_with_multiple_components(self) -> None:
        """Test compute_weighted_ensemble with multiple components."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.8"),
                confidence=Decimal("0.9"),
                label="POSITIVE",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("0.6"),
                confidence=Decimal("0.8"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.5"), "aion": Decimal("0.5")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.70")
        assert composite_confidence == Decimal("0.85")

    def test_compute_weighted_ensemble_unequal_weights(self) -> None:
        """Test weighted ensemble with unequal weights."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.9"),
                confidence=Decimal("0.95"),
                label="POSITIVE",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("0.3"),
                confidence=Decimal("0.7"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.7"), "aion": Decimal("0.3")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.72")
        assert composite_confidence == Decimal("0.875")

    def test_compute_weighted_ensemble_confidence_capped(self) -> None:
        """Test that composite confidence is capped at 1.0."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.9"),
                confidence=Decimal("0.95"),
                label="POSITIVE",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("0.8"),
                confidence=Decimal("0.9"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.6"), "aion": Decimal("0.5")}  # Total > 1
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_confidence <= Decimal("1")

    def test_compute_weighted_ensemble_zero_total_weight_raises(self) -> None:
        """Edge: Zero total_weight (division by zero) raises error."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.8"),
                confidence=Decimal("0.9"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0")}  # Zero weight
        with pytest.raises(InvalidOperation):
            compute_weighted_ensemble(component_scores, weights)

    def test_compute_weighted_ensemble_single_component(self) -> None:
        """Test ensemble with single component."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.85"),
                confidence=Decimal("0.9"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("1.0")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.85")
        assert composite_confidence == Decimal("0.9")

    def test_compute_weighted_ensemble_negative_scores(self) -> None:
        """Test weighted ensemble with negative scores."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("-0.7"),
                confidence=Decimal("0.9"),
                label="NEGATIVE",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("-0.5"),
                confidence=Decimal("0.8"),
                label="NEGATIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.5"), "aion": Decimal("0.5")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("-0.60")
        assert composite_confidence == Decimal("0.85")

    def test_compute_weighted_ensemble_precision_handling(self) -> None:
        """Test that ensemble handles Decimal precision correctly."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.333333"),
                confidence=Decimal("0.666666"),
                label="POSITIVE",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("0.666666"),
                confidence=Decimal("0.333333"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.5"), "aion": Decimal("0.5")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.4999995")
        assert composite_confidence == Decimal("0.4999995")

    def test_compute_weighted_ensemble_boundary_confidence_zero(self) -> None:
        """Test boundary: confidence at 0."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.5"),
                confidence=Decimal("0"),
                label="NEUTRAL",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("1.0")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.5")
        assert composite_confidence == Decimal("0")

    def test_compute_weighted_ensemble_boundary_confidence_one(self) -> None:
        """Test boundary: confidence at 1."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("1.0"),
                confidence=Decimal("1.0"),
                label="POSITIVE",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("1.0")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("1.0")
        assert composite_confidence == Decimal("1.0")

    def test_compute_weighted_ensemble_boundary_risk_fraction_half(self) -> None:
        """Test boundary: weight at 0.5."""
        component_scores = {
            "finbert": SentimentScore(
                source="finbert",
                score=Decimal("0.5"),
                confidence=Decimal("0.5"),
                label="NEUTRAL",
                text_excerpt="test",
            ),
            "aion": SentimentScore(
                source="aion",
                score=Decimal("0.5"),
                confidence=Decimal("0.5"),
                label="NEUTRAL",
                text_excerpt="test",
            ),
        }
        weights = {"finbert": Decimal("0.5"), "aion": Decimal("0.5")}
        composite_score, composite_confidence = compute_weighted_ensemble(component_scores, weights)
        assert composite_score == Decimal("0.5")
        assert composite_confidence == Decimal("0.5")
