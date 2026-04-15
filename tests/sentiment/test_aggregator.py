import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.sentiment.aggregator import SentimentAggregator
from iatb.sentiment.base import SentimentScore

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class _StubAnalyzer:
    def __init__(self, source: str, score: Decimal, confidence: Decimal) -> None:
        self._source = source
        self._score = score
        self._confidence = confidence

    def analyze(self, text: str) -> SentimentScore:
        return SentimentScore(
            source=self._source,
            score=self._score,
            confidence=self._confidence,
            label="POSITIVE" if self._score > 0 else "NEGATIVE",
            text_excerpt=text[:120],
        )


def test_aggregator_weighted_score_for_indian_headline() -> None:
    headline = "Reliance and HDFC Bank lead Nifty gains after strong quarterly earnings."
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.80"), Decimal("0.80")),
        vader=_StubAnalyzer("vader", Decimal("0.70"), Decimal("0.70")),
    )
    composite, _ = aggregator.analyze(headline)
    # Weighted average: (0.9*0.45 + 0.8*0.35 + 0.7*0.20) / (0.45+0.35+0.20) = 0.811...
    assert composite.score == Decimal("0.8111111111111111111111111111")
    assert composite.label == "POSITIVE"


def test_aggregator_enforces_very_strong_and_volume_gate() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.95"), Decimal("0.95")),
        aion=_StubAnalyzer("aion", Decimal("0.90"), Decimal("0.90")),
        vader=_StubAnalyzer("vader", Decimal("0.85"), Decimal("0.85")),
    )
    result = aggregator.evaluate_instrument("NSE PSU stocks rally on capex push.", Decimal("1.7"))
    assert result.very_strong
    assert result.volume_confirmed
    assert result.tradable


def test_aggregator_blocks_without_volume_confirmation() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.85"), Decimal("0.85")),
        vader=_StubAnalyzer("vader", Decimal("0.80"), Decimal("0.80")),
    )
    result = aggregator.evaluate_instrument(
        "Auto sector optimism fades after weak sales.",
        Decimal("1.2"),
    )
    assert result.very_strong
    assert not result.volume_confirmed
    assert not result.tradable


def test_aggregator_rejects_invalid_threshold() -> None:
    with pytest.raises(ConfigError, match="must be in"):
        SentimentAggregator(
            finbert=_StubAnalyzer("finbert", Decimal("0.10"), Decimal("0.10")),
            aion=_StubAnalyzer("aion", Decimal("0.10"), Decimal("0.10")),
            vader=_StubAnalyzer("vader", Decimal("0.10"), Decimal("0.10")),
            very_strong_threshold=Decimal("0"),
        )
