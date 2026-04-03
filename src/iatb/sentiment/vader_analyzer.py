"""
VADER sentiment analyzer wrapper.
"""

import importlib
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Protocol, cast

from iatb.core.exceptions import ConfigError
from iatb.sentiment.base import SentimentAnalyzer, SentimentScore, sentiment_label_from_score


class VaderLike(Protocol):
    def polarity_scores(self, text: str) -> object:
        ...


VaderFactory = Callable[[], VaderLike]


def _default_factory() -> VaderLike:
    try:
        module = importlib.import_module("vaderSentiment.vaderSentiment")
    except ModuleNotFoundError as exc:
        msg = "vadersentiment dependency is required for VaderAnalyzer"
        raise ConfigError(msg) from exc
    analyzer_cls = getattr(module, "SentimentIntensityAnalyzer", None)
    if not callable(analyzer_cls):
        msg = "SentimentIntensityAnalyzer not found"
        raise ConfigError(msg)
    return cast(VaderLike, analyzer_cls())


class VaderAnalyzer(SentimentAnalyzer):
    """Fast fallback analyzer using VADER compound score."""

    weight = Decimal("0.2")

    def __init__(self, analyzer_factory: VaderFactory | None = None) -> None:
        factory = analyzer_factory or _default_factory
        self._analyzer = factory()

    def analyze(self, text: str) -> SentimentScore:
        normalized = text.strip()
        if not normalized:
            msg = "text cannot be empty"
            raise ConfigError(msg)
        payload = self._analyzer.polarity_scores(normalized)
        if not isinstance(payload, Mapping):
            msg = "VADER polarity_scores must return mapping"
            raise ConfigError(msg)
        compound = Decimal(str(payload.get("compound", "0")))
        bounded = max(Decimal("-1"), min(Decimal("1"), compound))
        confidence = min(Decimal("1"), abs(bounded) + Decimal("0.10"))
        return SentimentScore(
            source="vader",
            score=bounded,
            confidence=confidence,
            label=sentiment_label_from_score(bounded),
            text_excerpt=normalized[:140],
        )
