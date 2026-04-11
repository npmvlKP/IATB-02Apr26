"""
FinBERT sentiment analyzer (ProsusAI/finbert).
"""

from collections.abc import Callable, Mapping
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score
from iatb.sentiment.helpers import parse_finbert_label_score, resolve_finbert_predictor

PredictFn = Callable[[str], list[Mapping[str, object]]]


class FinbertAnalyzer(SentimentAnalyzer):
    """ProsusAI/finbert wrapper with normalized score output."""

    weight = Decimal("0.5")

    def __init__(
        self,
        predictor: PredictFn | None = None,
        model_id: str = "ProsusAI/finbert",
    ) -> None:
        self._predict = predictor or resolve_finbert_predictor(model_id)

    def analyze(self, text: str) -> SentimentScore:
        normalized_text = text.strip()
        if not normalized_text:
            msg = "text cannot be empty"
            raise ConfigError(msg)
        label, confidence = parse_finbert_label_score(self._predict(normalized_text))
        if label.startswith("POS"):
            score = confidence
        elif label.startswith("NEG"):
            score = -confidence
        else:
            score = Decimal("0")
        return SentimentScore(
            source="finbert",
            score=score,
            confidence=confidence,
            label=sentiment_label_from_score(score),
            text_excerpt=normalized_text[:140],
        )
