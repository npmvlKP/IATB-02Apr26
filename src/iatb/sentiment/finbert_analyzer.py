"""
FinBERT sentiment analyzer (ProsusAI/finbert).
"""

import importlib
from collections.abc import Callable, Mapping
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score

PredictFn = Callable[[str], list[Mapping[str, object]]]


def _require_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        msg = "text cannot be empty"
        raise ConfigError(msg)
    return normalized


def _score_from_label(label: str, confidence: Decimal) -> Decimal:
    if label.startswith("POS"):
        return confidence
    if label.startswith("NEG"):
        return -confidence
    return Decimal("0")


def _default_predictor(model_id: str) -> PredictFn:
    try:
        transformers = importlib.import_module("transformers")
    except ModuleNotFoundError as exc:
        msg = "transformers dependency is required for FinbertAnalyzer"
        raise ConfigError(msg) from exc
    if not hasattr(transformers, "pipeline"):
        msg = "transformers.pipeline is unavailable"
        raise ConfigError(msg)
    pipeline_fn = transformers.pipeline("sentiment-analysis", model=model_id, tokenizer=model_id)
    return lambda text: pipeline_fn(text, truncation=True)


class FinbertAnalyzer(SentimentAnalyzer):
    """ProsusAI/finbert wrapper with normalized score output."""

    weight = Decimal("0.5")

    def __init__(
        self,
        predictor: PredictFn | None = None,
        model_id: str = "ProsusAI/finbert",
    ) -> None:
        self._predict = predictor or _default_predictor(model_id)

    def analyze(self, text: str) -> SentimentScore:
        normalized_text = _require_text(text)
        predictions = self._predict(normalized_text)
        if not predictions or not isinstance(predictions[0], Mapping):
            msg = "FinBERT response must contain at least one mapping prediction"
            raise ConfigError(msg)
        label = str(predictions[0].get("label", "NEUTRAL")).upper()
        confidence = Decimal(str(predictions[0].get("score", "0")))
        score = _score_from_label(label, confidence)
        return SentimentScore(
            source="finbert",
            score=score,
            confidence=confidence,
            label=sentiment_label_from_score(score),
            text_excerpt=normalized_text[:140],
        )
