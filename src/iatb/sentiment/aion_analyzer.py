"""
AION sentiment analyzer wrapper for Indian financial headlines.
"""

from collections.abc import Callable
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.helpers import resolve_aion_predictor, validate_and_parse_aion_prediction

PredictFn = Callable[[str], object]


class AionAnalyzer(SentimentAnalyzer):
    """AION-Sentiment-IN-v3 wrapper."""

    weight = Decimal("0.3")

    def __init__(self, predict_fn: PredictFn | None = None) -> None:
        self._predict = predict_fn or resolve_aion_predictor()

    def analyze(self, text: str) -> SentimentScore:
        normalized_text = text.strip()
        if not normalized_text:
            msg = "text cannot be empty"
            raise ConfigError(msg)
        label, confidence = validate_and_parse_aion_prediction(self._predict(normalized_text))
        bounded_confidence = min(Decimal("1"), max(Decimal("0"), confidence))
        normalized_label = label.upper()
        if "POS" in normalized_label or "BULL" in normalized_label:
            score = bounded_confidence
        elif "NEG" in normalized_label or "BEAR" in normalized_label:
            score = -bounded_confidence
        else:
            score = Decimal("0")
        return SentimentScore(
            source="aion",
            score=score,
            confidence=bounded_confidence,
            label=sentiment_label_from_score(score),
            text_excerpt=normalized_text[:140],
        )
