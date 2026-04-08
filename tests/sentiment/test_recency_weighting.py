"""Tests for recency_weighting.py module."""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.sentiment.recency_weighting import recency_weighted_score

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_recency_weighted_score_basic() -> None:
    """Test recency_weighted_score with basic inputs."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.8"), now - timedelta(minutes=10)),
        (Decimal("0.6"), now - timedelta(minutes=30)),
        (Decimal("0.4"), now - timedelta(hours=1)),
    ]

    result = recency_weighted_score(article_scores, now)

    assert Decimal("0") <= result <= Decimal("1")
    # Recent article should have more weight, so result should be > simple average
    simple_avg = (Decimal("0.8") + Decimal("0.6") + Decimal("0.4")) / Decimal("3")
    assert result > simple_avg


def test_recency_weighted_score_all_recent() -> None:
    """Test recency_weighted_score with all recent articles."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.9"), now - timedelta(minutes=5)),
        (Decimal("0.7"), now - timedelta(minutes=15)),
        (Decimal("0.8"), now - timedelta(minutes=20)),
    ]

    result = recency_weighted_score(article_scores, now)

    # All recent, should be close to simple average
    assert Decimal("0.75") <= result <= Decimal("0.85")


def test_recency_weighted_score_all_old() -> None:
    """Test recency_weighted_score with all old articles."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.9"), now - timedelta(hours=5)),
        (Decimal("0.1"), now - timedelta(hours=6)),
        (Decimal("0.5"), now - timedelta(hours=10)),
    ]

    result = recency_weighted_score(article_scores, now)

    # All old, should be close to simple average (low weights)
    assert Decimal("0.4") <= result <= Decimal("0.6")


def test_recency_weighted_score_mixed_ages() -> None:
    """Test recency_weighted_score with mixed article ages."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.9"), now - timedelta(minutes=5)),  # Recent, high score
        (Decimal("0.1"), now - timedelta(hours=5)),  # Old, low score
    ]

    result = recency_weighted_score(article_scores, now)

    # Recent high score should dominate
    assert result > Decimal("0.5")


def test_recency_weighted_score_rejects_empty_list() -> None:
    """Test recency_weighted_score raises ConfigError for empty list."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = []

    with pytest.raises(ConfigError, match="article_scores cannot be empty"):
        recency_weighted_score(article_scores, now)


def test_recency_weighted_score_requires_utc_current_time() -> None:
    """Test recency_weighted_score raises ConfigError for non-UTC current time."""
    now_naive = datetime(2026, 4, 7, 8, 0, 0)  # noqa: DTZ001
    article_scores = [(Decimal("0.5"), datetime(2026, 4, 7, 7, 0, 0, tzinfo=UTC))]

    with pytest.raises(ConfigError, match="current_utc must be UTC"):
        recency_weighted_score(article_scores, now_naive)


def test_recency_weighted_score_requires_utc_article_time() -> None:
    """Test recency_weighted_score raises ConfigError for non-UTC article time."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.5"), datetime(2026, 4, 7, 7, 0, 0)),  # noqa: DTZ001
    ]

    with pytest.raises(ConfigError, match="article timestamp must be UTC"):
        recency_weighted_score(article_scores, now)


def test_recency_weighted_score_future_article() -> None:
    """Test recency_weighted_score handles future article timestamps."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.8"), now - timedelta(minutes=10)),
        (Decimal("0.5"), now + timedelta(hours=1)),  # Future
    ]

    result = recency_weighted_score(article_scores, now)

    # Future article should have 0 weight
    assert result == Decimal("0.8")


def test_recency_weighted_score_identical_timestamps() -> None:
    """Test recency_weighted_score with identical timestamps."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    timestamp = now - timedelta(minutes=10)
    article_scores = [
        (Decimal("0.2"), timestamp),
        (Decimal("0.4"), timestamp),
        (Decimal("0.6"), timestamp),
    ]

    result = recency_weighted_score(article_scores, now)

    # Should be simple average when all timestamps are equal
    assert result == Decimal("0.4")


def test_recency_weighted_score_very_old_articles() -> None:
    """Test recency_weighted_score with very old articles."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    # Very old articles (weights will be very small but not zero)
    article_scores = [
        (Decimal("0.9"), now - timedelta(days=100)),
        (Decimal("0.1"), now - timedelta(days=200)),
    ]

    result = recency_weighted_score(article_scores, now)

    # Should return a value between the scores (weighted average)
    assert Decimal("0.0") <= result <= Decimal("1.0")


def test_recency_weighted_score_extreme_values() -> None:
    """Test recency_weighted_score with extreme score values."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("1.0"), now - timedelta(minutes=5)),
        (Decimal("0.0"), now - timedelta(minutes=10)),
    ]

    result = recency_weighted_score(article_scores, now)

    # Should handle extreme values correctly
    assert Decimal("0") <= result <= Decimal("1")


def test_recency_weighted_score_single_article() -> None:
    """Test recency_weighted_score with single article."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [(Decimal("0.75"), now - timedelta(minutes=30))]

    result = recency_weighted_score(article_scores, now)

    # Single article should return its score
    assert result == Decimal("0.75")


def test_recency_weighted_score_weight_decay() -> None:
    """Test that recency_weighted_score properly decays weights over time."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.8"), now - timedelta(minutes=10)),
        (Decimal("0.8"), now - timedelta(hours=1)),
        (Decimal("0.8"), now - timedelta(hours=3)),
    ]

    result = recency_weighted_score(article_scores, now)

    # With same scores, result should be 0.8 regardless of weighting
    assert result == Decimal("0.8")


def test_recency_weighted_score_all_future_returns_zero() -> None:
    """Test that all future articles return zero (line 35 weight_sum == 0)."""
    now = datetime(2026, 4, 7, 8, 0, 0, tzinfo=UTC)
    article_scores = [
        (Decimal("0.9"), now + timedelta(hours=1)),  # Future
        (Decimal("0.8"), now + timedelta(hours=2)),  # Future
    ]

    result = recency_weighted_score(article_scores, now)

    # All future articles have 0 weight, so should return 0
    assert result == Decimal("0")
