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
        enable_graceful_fallback=False,
    )
    composite, _ = aggregator.analyze(headline)
    # Aggregator returns simple average: (0.9 + 0.8 + 0.7) / 3 = 0.8
    assert composite.score == Decimal("0.83")
    assert composite.label == "POSITIVE"


def test_aggregator_enforces_very_strong_and_volume_gate() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.95"), Decimal("0.95")),
        aion=_StubAnalyzer("aion", Decimal("0.90"), Decimal("0.90")),
        vader=_StubAnalyzer("vader", Decimal("0.85"), Decimal("0.85")),
        enable_graceful_fallback=False,
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
        enable_graceful_fallback=False,
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
            enable_graceful_fallback=False,
        )


def test_aggregator_rejects_threshold_greater_than_one() -> None:
    with pytest.raises(ConfigError, match="must be in"):
        SentimentAggregator(
            finbert=_StubAnalyzer("finbert", Decimal("0.10"), Decimal("0.10")),
            aion=_StubAnalyzer("aion", Decimal("0.10"), Decimal("0.10")),
            vader=_StubAnalyzer("vader", Decimal("0.10"), Decimal("0.10")),
            very_strong_threshold=Decimal("1.5"),
            enable_graceful_fallback=False,
        )


def test_aggregator_rejects_threshold_negative() -> None:
    with pytest.raises(ConfigError, match="must be in"):
        SentimentAggregator(
            finbert=_StubAnalyzer("finbert", Decimal("0.10"), Decimal("0.10")),
            aion=_StubAnalyzer("aion", Decimal("0.10"), Decimal("0.10")),
            vader=_StubAnalyzer("vader", Decimal("0.10"), Decimal("0.10")),
            very_strong_threshold=Decimal("-0.1"),
            enable_graceful_fallback=False,
        )


def test_aggregator_allows_valid_threshold_boundary() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.10"), Decimal("0.10")),
        aion=_StubAnalyzer("aion", Decimal("0.10"), Decimal("0.10")),
        vader=_StubAnalyzer("vader", Decimal("0.10"), Decimal("0.10")),
        very_strong_threshold=Decimal("1.0"),
        enable_graceful_fallback=False,
    )
    assert aggregator._very_strong_threshold == Decimal("1.0")


def test_aggregator_allows_valid_threshold_intermediate() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.10"), Decimal("0.10")),
        aion=_StubAnalyzer("aion", Decimal("0.10"), Decimal("0.10")),
        vader=_StubAnalyzer("vader", Decimal("0.10"), Decimal("0.10")),
        very_strong_threshold=Decimal("0.75"),
        enable_graceful_fallback=False,
    )
    assert aggregator._very_strong_threshold == Decimal("0.75")


def test_aggregator_initializes_with_default_analyzers() -> None:
    aggregator = SentimentAggregator()
    assert "finbert" in aggregator._analyzers
    assert "aion" in aggregator._analyzers
    assert "vader" in aggregator._analyzers


def test_aggregator_returns_component_scores() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.80"), Decimal("0.80")),
        vader=_StubAnalyzer("vader", Decimal("0.70"), Decimal("0.70")),
        enable_graceful_fallback=False,
    )
    composite, components = aggregator.analyze("Test headline")
    assert "finbert" in components
    assert "aion" in components
    assert "vader" in components
    assert components["finbert"].score == Decimal("0.90")
    assert components["aion"].score == Decimal("0.80")
    assert components["vader"].score == Decimal("0.70")


def test_aggregator_mixed_sentiment_scores() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.50"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("-0.20"), Decimal("0.80")),
        vader=_StubAnalyzer("vader", Decimal("0.30"), Decimal("0.70")),
        enable_graceful_fallback=False,
    )
    composite, components = aggregator.analyze("Mixed signals from RBI policy")
    assert -Decimal("1") <= composite.score <= Decimal("1")
    assert components["finbert"].score == Decimal("0.50")
    assert components["aion"].score == Decimal("-0.20")
    assert components["vader"].score == Decimal("0.30")


def test_aggregator_negative_sentiment() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("-0.85"), Decimal("0.95")),
        aion=_StubAnalyzer("aion", Decimal("-0.90"), Decimal("0.90")),
        vader=_StubAnalyzer("vader", Decimal("-0.80"), Decimal("0.85")),
        enable_graceful_fallback=False,
    )
    composite, _ = aggregator.analyze("Market crash fears intensify")
    assert composite.score < 0
    assert composite.label == "NEGATIVE"


def test_aggregator_very_strong_negative_sentiment() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("-0.95"), Decimal("0.95")),
        aion=_StubAnalyzer("aion", Decimal("-0.90"), Decimal("0.90")),
        vader=_StubAnalyzer("vader", Decimal("-0.85"), Decimal("0.85")),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Global recession fears deepen", Decimal("2.0"))
    assert result.very_strong
    assert result.volume_confirmed
    assert result.tradable


def test_aggregator_neutral_sentiment() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.05"), Decimal("0.80")),
        aion=_StubAnalyzer("aion", Decimal("-0.05"), Decimal("0.80")),
        vader=_StubAnalyzer("vader", Decimal("0.00"), Decimal("0.80")),
        enable_graceful_fallback=False,
    )
    composite, _ = aggregator.analyze("Market awaits RBI decision")
    assert -Decimal("0.2") < composite.score < Decimal("0.2")
    assert composite.label in ["NEUTRAL", "POSITIVE", "NEGATIVE"]


def test_aggregator_custom_very_strong_threshold() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.70"), Decimal("0.70")),
        aion=_StubAnalyzer("aion", Decimal("0.65"), Decimal("0.65")),
        vader=_StubAnalyzer("vader", Decimal("0.60"), Decimal("0.60")),
        very_strong_threshold=Decimal("0.65"),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Moderate positive news", Decimal("1.8"))
    assert result.very_strong
    assert result.volume_confirmed
    assert result.tradable


def test_aggregator_not_very_strong_below_threshold() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.70"), Decimal("0.70")),
        aion=_StubAnalyzer("aion", Decimal("0.65"), Decimal("0.65")),
        vader=_StubAnalyzer("vader", Decimal("0.60"), Decimal("0.60")),
        very_strong_threshold=Decimal("0.80"),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Moderate positive news", Decimal("1.8"))
    assert not result.very_strong
    assert result.volume_confirmed
    assert not result.tradable


def test_aggregator_volume_confirmation_edge_case() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.85"), Decimal("0.85")),
        vader=_StubAnalyzer("vader", Decimal("0.80"), Decimal("0.80")),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Strong positive news", Decimal("1.5"))
    assert result.very_strong
    assert result.volume_confirmed
    assert result.tradable


def test_aggregator_no_volume_confirmation_below_threshold() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.85"), Decimal("0.85")),
        vader=_StubAnalyzer("vader", Decimal("0.80"), Decimal("0.80")),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Strong positive news", Decimal("1.3"))
    assert result.very_strong
    assert not result.volume_confirmed
    assert not result.tradable


def test_aggregator_text_excerpt_truncation() -> None:
    long_text = (
        "This is a very long news headline that should be truncated "
        "when stored in the sentiment score text excerpt field for display purposes"
    )
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.50"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.50"), Decimal("0.90")),
        vader=_StubAnalyzer("vader", Decimal("0.50"), Decimal("0.90")),
        enable_graceful_fallback=False,
    )
    composite, _ = aggregator.analyze(long_text)
    assert len(composite.text_excerpt) <= 140


def test_aggregator_empty_text() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.00"), Decimal("0.50")),
        aion=_StubAnalyzer("aion", Decimal("0.00"), Decimal("0.50")),
        vader=_StubAnalyzer("vader", Decimal("0.00"), Decimal("0.50")),
        enable_graceful_fallback=False,
    )
    composite, components = aggregator.analyze("")
    assert composite.source == "ensemble"
    assert len(components) == 3


def test_aggregator_whitespace_only_text() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.00"), Decimal("0.50")),
        aion=_StubAnalyzer("aion", Decimal("0.00"), Decimal("0.50")),
        vader=_StubAnalyzer("vader", Decimal("0.00"), Decimal("0.50")),
        enable_graceful_fallback=False,
    )
    composite, _ = aggregator.analyze("   ")
    assert composite.source == "ensemble"


def test_aggregator_graceful_fallback_disabled() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.80"), Decimal("0.80")),
        aion=_StubAnalyzer("aion", Decimal("0.70"), Decimal("0.70")),
        vader=_StubAnalyzer("vader", Decimal("0.60"), Decimal("0.60")),
        enable_graceful_fallback=False,
    )
    assert "finbert" in aggregator._analyzers
    assert "aion" in aggregator._analyzers
    assert "vader" in aggregator._analyzers


def test_aggregator_result_structure() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.85"), Decimal("0.85")),
        vader=_StubAnalyzer("vader", Decimal("0.80"), Decimal("0.80")),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Test news", Decimal("1.8"))
    assert hasattr(result, "composite")
    assert hasattr(result, "very_strong")
    assert hasattr(result, "volume_confirmed")
    assert hasattr(result, "tradable")
    assert hasattr(result, "component_scores")
    assert isinstance(result.component_scores, dict)
    assert len(result.component_scores) == 3


def test_aggregator_component_scores_are_decimals() -> None:
    aggregator = SentimentAggregator(
        finbert=_StubAnalyzer("finbert", Decimal("0.90"), Decimal("0.90")),
        aion=_StubAnalyzer("aion", Decimal("0.80"), Decimal("0.80")),
        vader=_StubAnalyzer("vader", Decimal("0.70"), Decimal("0.70")),
        enable_graceful_fallback=False,
    )
    result = aggregator.evaluate_instrument("Test news", Decimal("1.8"))
    for score in result.component_scores.values():
        assert isinstance(score, Decimal)
