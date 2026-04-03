"""
AION sentiment analyzer wrapper for Indian financial headlines.
"""

import importlib
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import cast

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score

PredictFn = Callable[[str], object]


def _require_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        msg = "text cannot be empty"
        raise ConfigError(msg)
    return normalized


def _label_to_score(label: str, confidence: Decimal) -> Decimal:
    normalized = label.upper()
    if "POS" in normalized or "BULL" in normalized:
        return confidence
    if "NEG" in normalized or "BEAR" in normalized:
        return -confidence
    return Decimal("0")


def _resolve_predict_fn() -> PredictFn:
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


def _parse_prediction(raw_prediction: object) -> tuple[str, Decimal]:
    if isinstance(raw_prediction, Mapping):
        label = str(raw_prediction.get("label", raw_prediction.get("sentiment", "NEUTRAL")))
        value = raw_prediction.get("score", raw_prediction.get("confidence", "0.70"))
        return label, Decimal(str(value))
    if isinstance(raw_prediction, tuple) and len(raw_prediction) >= 2:
        return str(raw_prediction[0]), Decimal(str(raw_prediction[1]))
    if isinstance(raw_prediction, str):
        return raw_prediction, Decimal("0.70")
    msg = "Unsupported AION prediction output format"
    raise ConfigError(msg)


class AionAnalyzer(SentimentAnalyzer):
    """AION-Sentiment-IN-v3 wrapper."""

    weight = Decimal("0.3")

    def __init__(self, predict_fn: PredictFn | None = None) -> None:
        self._predict = predict_fn or _resolve_predict_fn()

    def analyze(self, text: str) -> SentimentScore:
        normalized_text = _require_text(text)
        label, confidence = _parse_prediction(self._predict(normalized_text))
        if confidence < Decimal("0"):
            msg = "AION confidence cannot be negative"
            raise ConfigError(msg)
        bounded_confidence = min(Decimal("1"), confidence)
        score = _label_to_score(label, bounded_confidence)
        return SentimentScore(
            source="aion",
            score=score,
            confidence=bounded_confidence,
            label=sentiment_label_from_score(score),
            text_excerpt=normalized_text[:140],
        )
