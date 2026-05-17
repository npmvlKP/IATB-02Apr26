"""Tests for sentiment/recency_weighting.py — time decay."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.sentiment.recency_weighting import (
    _article_weight,
    recency_weighted_score,
)


class TestRecencyWeightedScore:
    def test_single_recent_article(self) -> None:
        now = datetime.now(UTC)
        score = recency_weighted_score(
            [(Decimal("0.8"), now - timedelta(minutes=5))],
            now,
        )
        assert isinstance(score, Decimal)
        assert score > Decimal("0.5")

    def test_empty_scores_raises(self) -> None:
        with pytest.raises(ConfigError, match="article_scores cannot be empty"):
            recency_weighted_score([], datetime.now(UTC))

    def test_non_utc_current_raises(self) -> None:
        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            recency_weighted_score(
                [(Decimal("0.5"), datetime.now(UTC))],
                datetime(2024, 1, 1),
            )

    def test_non_utc_article_raises(self) -> None:
        with pytest.raises(ConfigError, match="article timestamp must be UTC"):
            recency_weighted_score(
                [(Decimal("0.5"), datetime(2024, 1, 1))],
                datetime.now(UTC),
            )

    def test_mixed_ages(self) -> None:
        now = datetime.now(UTC)
        scores = [
            (Decimal("1.0"), now - timedelta(minutes=5)),
            (Decimal("0.0"), now - timedelta(hours=5)),
        ]
        result = recency_weighted_score(scores, now)
        assert result > Decimal("0.5")

    def test_future_article_weight_zero(self) -> None:
        now = datetime.now(UTC)
        weight = _article_weight(now + timedelta(hours=1), now)
        assert weight == Decimal("0")

    def test_recent_article_high_weight(self) -> None:
        now = datetime.now(UTC)
        weight = _article_weight(now - timedelta(minutes=10), now)
        assert weight > Decimal("0.5")

    def test_old_article_low_weight(self) -> None:
        now = datetime.now(UTC)
        weight = _article_weight(now - timedelta(hours=10), now)
        assert weight < Decimal("0.5")

    def test_all_same_scores(self) -> None:
        now = datetime.now(UTC)
        scores = [(Decimal("0.6"), now - timedelta(minutes=i * 5)) for i in range(5)]
        result = recency_weighted_score(scores, now)
        assert Decimal("0") <= result <= Decimal("1")

    def test_zero_weight_sum_returns_zero(self) -> None:
        now = datetime.now(UTC)
        scores = [(Decimal("0.5"), now + timedelta(hours=i + 1)) for i in range(3)]
        result = recency_weighted_score(scores, now)
        assert result == Decimal("0")
