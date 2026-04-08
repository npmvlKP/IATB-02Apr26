"""Tests for sentiment helper functions."""

from decimal import Decimal

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


def test_parse_finbert_label_score_positive() -> None:
    """Test parsing positive FinBERT prediction."""
    predictions = [{"label": "POSITIVE", "score": 0.92}]
    label, confidence = parse_finbert_label_score(predictions)
    assert label == "POSITIVE"
    assert confidence == Decimal("0.92")


def test_parse_finbert_label_score_negative() -> None:
    """Test parsing negative FinBERT prediction."""
    predictions = [{"label": "NEGATIVE", "score": 0.81}]
    label, confidence = parse_finbert_label_score(predictions)
    assert label == "NEGATIVE"
    assert confidence == Decimal("0.81")


def test_parse_finbert_label_score_neutral() -> None:
    """Test parsing neutral FinBERT prediction."""
    predictions = [{"label": "NEUTRAL", "score": 0.6}]
    label, confidence = parse_finbert_label_score(predictions)
    assert label == "NEUTRAL"
    assert confidence == Decimal("0.6")


def test_parse_finbert_label_score_empty_predictions_raises() -> None:
    """Test that empty predictions list raises ConfigError."""
    with pytest.raises(ConfigError, match="at least one mapping prediction"):
        parse_finbert_label_score([])


def test_parse_finbert_label_score_missing_label_defaults() -> None:
    """Test that missing label defaults to NEUTRAL."""
    predictions = [{"score": 0.5}]
    label, confidence = parse_finbert_label_score(predictions)
    assert label == "NEUTRAL"
    assert confidence == Decimal("0.5")


def test_parse_finbert_label_score_missing_score_defaults() -> None:
    """Test that missing score defaults to 0."""
    predictions = [{"label": "POSITIVE"}]
    label, confidence = parse_finbert_label_score(predictions)
    assert label == "POSITIVE"
    assert confidence == Decimal("0")


def test_validate_and_parse_aion_prediction_mapping() -> None:
    """Test parsing AION prediction from mapping."""
    prediction = {"label": "POSITIVE", "score": 0.85}
    label, confidence = validate_and_parse_aion_prediction(prediction)
    assert label == "POSITIVE"
    assert confidence == Decimal("0.85")


def test_validate_and_parse_aion_prediction_mapping_with_sentiment() -> None:
    """Test parsing AION prediction with sentiment key."""
    prediction = {"sentiment": "NEGATIVE", "confidence": 0.78}
    label, confidence = validate_and_parse_aion_prediction(prediction)
    assert label == "NEGATIVE"
    assert confidence == Decimal("0.78")


def test_validate_and_parse_aion_prediction_tuple() -> None:
    """Test parsing AION prediction from tuple."""
    prediction = ("BULLISH", "0.88")
    label, confidence = validate_and_parse_aion_prediction(prediction)
    assert label == "BULLISH"
    assert confidence == Decimal("0.88")


def test_validate_and_parse_aion_prediction_string() -> None:
    """Test parsing AION prediction from string."""
    prediction = "BEARISH"
    label, confidence = validate_and_parse_aion_prediction(prediction)
    assert label == "BEARISH"
    assert confidence == Decimal("0.70")


def test_validate_and_parse_aion_prediction_invalid_type_raises() -> None:
    """Test that invalid prediction type raises ConfigError."""
    with pytest.raises(ConfigError, match="Unsupported AION prediction output format"):
        validate_and_parse_aion_prediction(123)


def test_compute_weighted_ensemble_equal_weights() -> None:
    """Test weighted ensemble with equal weights."""
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


def test_compute_weighted_ensemble_unequal_weights() -> None:
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


def test_compute_weighted_ensemble_confidence_capped() -> None:
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


def test_compute_weighted_ensemble_negative_scores() -> None:
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


def test_resolve_finbert_predictor_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing transformers dependency raises ConfigError."""
    monkeypatch.setattr(
        "iatb.sentiment.helpers.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="transformers dependency"):
        resolve_finbert_predictor("ProsusAI/finbert")


def test_resolve_finbert_predictor_pipeline_unavailable_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that unavailable pipeline raises ConfigError."""
    monkeypatch.setattr(
        "iatb.sentiment.helpers.importlib.import_module",
        lambda _: type("obj", (), {})(),
    )
    with pytest.raises(ConfigError, match="pipeline is unavailable"):
        resolve_finbert_predictor("ProsusAI/finbert")


def test_resolve_aion_predictor_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing aion-sentiment dependency raises ConfigError."""
    monkeypatch.setattr(
        "iatb.sentiment.helpers.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="aion-sentiment dependency"):
        resolve_aion_predictor()


def test_resolve_aion_predictor_no_usable_interface_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing usable prediction interface raises ConfigError."""
    monkeypatch.setattr(
        "iatb.sentiment.helpers.importlib.import_module",
        lambda _: type("obj", (), {})(),
    )
    with pytest.raises(ConfigError, match="does not expose a usable prediction interface"):
        resolve_aion_predictor()


def test_resolve_aion_predictor_finds_predict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that resolve_aion_predictor finds predict function."""

    def mock_predict(self, text: str) -> dict[str, str]:  # type: ignore[misc]
        _ = self
        return {"label": "POSITIVE", "score": "0.85"}

    mock_module = type("obj", (), {"predict": mock_predict})()
    monkeypatch.setattr("iatb.sentiment.helpers.importlib.import_module", lambda _: mock_module)
    predictor = resolve_aion_predictor()
    assert predictor is not None
    assert predictor("test") == {"label": "POSITIVE", "score": "0.85"}


def test_compute_weighted_ensemble_precision_handling() -> None:
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


def test_compute_weighted_ensemble_single_component() -> None:
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
