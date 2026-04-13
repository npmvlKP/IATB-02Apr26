"""
Helper functions for sentiment analyzers to keep main classes under 50 LOC.
"""

import importlib
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from iatb.core.exceptions import ConfigError

if TYPE_CHECKING:
    from iatb.sentiment.base import SentimentScore

PredictFn = Callable[[str], object]


def resolve_aion_predictor() -> PredictFn:
    """Resolve AION-Sentiment-IN-v3 prediction function from dependency."""
    try:
        module = importlib.import_module("aion_sentiment")
    except ModuleNotFoundError as exc:
        msg = "aion-sentiment dependency is required for AionAnalyzer"
        raise ConfigError(msg) from exc
    for name in ("predict", "analyze", "analyze_sentiment"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            return cast(PredictFn, candidate)
    model_cls = getattr(module, "AionSentiment", None)
    if callable(model_cls):
        model = model_cls()
        for name in ("predict", "analyze"):
            candidate = getattr(model, name, None)
            if callable(candidate):
                return cast(PredictFn, candidate)
    msg = "aion-sentiment does not expose a usable prediction interface"
    raise ConfigError(msg)


def validate_and_parse_aion_prediction(raw_prediction: object) -> tuple[str, Decimal]:
    """Parse and validate AION prediction output."""
    if isinstance(raw_prediction, Mapping):
        label = str(raw_prediction.get("label", raw_prediction.get("sentiment", "NEUTRAL")))
        value = raw_prediction.get("score", raw_prediction.get("confidence", "0.70"))
        confidence = Decimal(str(value))
        if confidence < Decimal("0"):
            msg = "AION confidence cannot be negative"
            raise ConfigError(msg)
        return label, confidence
    if isinstance(raw_prediction, tuple) and len(raw_prediction) >= 2:
        return str(raw_prediction[0]), Decimal(str(raw_prediction[1]))
    if isinstance(raw_prediction, str):
        return raw_prediction, Decimal("0.70")
    msg = "Unsupported AION prediction output format"
    raise ConfigError(msg)


def resolve_finbert_predictor(model_id: str) -> Callable[[str], list[Mapping[str, object]]]:
    """Resolve FinBERT prediction function from transformers dependency."""
    try:
        transformers = importlib.import_module("transformers")
    except ModuleNotFoundError as exc:
        msg = "transformers dependency is required for FinbertAnalyzer"
        raise ConfigError(msg) from exc
    except OSError as exc:
        # Handle PyTorch DLL loading failures on Windows
        msg = "transformers/PyTorch dependency unavailable (DLL load failed)"
        raise ConfigError(msg) from exc

    if not hasattr(transformers, "pipeline"):
        msg = "transformers.pipeline is unavailable"
        raise ConfigError(msg)
    try:
        pipeline_fn = transformers.pipeline(
            "sentiment-analysis", model=model_id, tokenizer=model_id
        )
    except OSError as exc:
        # Handle PyTorch DLL loading failures during pipeline creation
        msg = "PyTorch unavailable (DLL load failed during pipeline creation)"
        raise ConfigError(msg) from exc

    return lambda text: pipeline_fn(text, truncation=True)


def parse_finbert_label_score(predictions: list[Mapping[str, object]]) -> tuple[str, Decimal]:
    """Parse FinBERT prediction output to label and confidence."""
    if not predictions:
        msg = "FinBERT response must contain at least one mapping prediction"
        raise ConfigError(msg)
    label = str(predictions[0].get("label", "NEUTRAL")).upper()
    confidence = Decimal(str(predictions[0].get("score", "0")))
    return label, confidence


def compute_weighted_ensemble(
    component_scores: dict[str, "SentimentScore"], weights: dict[str, Decimal]
) -> tuple[Decimal, Decimal]:
    """Compute weighted ensemble score and confidence from component scores."""

    total_weight = sum(weights.values(), Decimal("0"))
    weighted_score = sum(
        (score.score * weights[name] for name, score in component_scores.items()),
        Decimal("0"),
    )
    weighted_confidence = sum(
        (score.confidence * weights[name] for name, score in component_scores.items()),
        Decimal("0"),
    )
    composite_score = weighted_score / total_weight
    composite_confidence = min(Decimal("1"), weighted_confidence / total_weight)
    return composite_score, composite_confidence
