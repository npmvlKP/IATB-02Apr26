"""Tests for selection.ranking module."""

from __future__ import annotations

from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.selection.ranking import (
    RankingConfig,
    _apply_threshold,
    _assign_ranks,
    _is_too_correlated,
    _ordered_pair,
    rank_and_select,
)


def test_ranking_config_defaults() -> None:
    cfg = RankingConfig()
    assert cfg.min_score == Decimal("0.20")
    assert cfg.top_n == 5


def test_ranking_config_invalid_min_score() -> None:
    with pytest.raises(ConfigError, match="min_score must be in"):
        RankingConfig(min_score=Decimal("1.5"))


def test_ranking_config_invalid_top_n() -> None:
    with pytest.raises(ConfigError, match="top_n must be positive"):
        RankingConfig(top_n=0)


def test_ranking_config_invalid_correlation_limit() -> None:
    with pytest.raises(ConfigError, match="correlation_limit must be in"):
        RankingConfig(correlation_limit=Decimal("1.5"))


def test_rank_and_select_empty() -> None:
    result = rank_and_select([])
    assert result.selected == []
    assert result.total_candidates == 0


def test_rank_and_select_threshold_filter() -> None:
    candidates = [
        ("A", Exchange.NSE, Decimal("0.1"), {}),
        ("B", Exchange.NSE, Decimal("0.5"), {}),
    ]
    result = rank_and_select(candidates, config=RankingConfig(min_score=Decimal("0.3")))
    assert len(result.selected) == 1
    assert result.selected[0].symbol == "B"


def test_rank_and_select_top_n() -> None:
    candidates = [
        ("A", Exchange.NSE, Decimal("0.9"), {}),
        ("B", Exchange.NSE, Decimal("0.8"), {}),
        ("C", Exchange.NSE, Decimal("0.7"), {}),
    ]
    result = rank_and_select(candidates, config=RankingConfig(top_n=2))
    assert len(result.selected) == 2
    assert result.selected[0].rank == 1


def test_rank_and_select_correlation_filter() -> None:
    candidates = [
        ("A", Exchange.NSE, Decimal("0.9"), {}),
        ("B", Exchange.NSE, Decimal("0.8"), {}),
    ]
    correlations = {("A", "B"): Decimal("0.95")}
    result = rank_and_select(
        candidates,
        config=RankingConfig(correlation_limit=Decimal("0.80")),
        correlations=correlations,
    )
    assert len(result.selected) == 1


def test_apply_threshold() -> None:
    candidates = [
        ("A", Exchange.NSE, Decimal("0.1"), {}),
        ("B", Exchange.NSE, Decimal("0.5"), {}),
    ]
    result = _apply_threshold(candidates, Decimal("0.3"))
    assert len(result) == 1


def test_is_too_correlated() -> None:
    selected = [("A", Exchange.NSE, Decimal("0.9"), {})]
    correlations = {("A", "B"): Decimal("0.95")}
    assert _is_too_correlated("B", selected, correlations, Decimal("0.80")) is True


def test_is_too_correlated_not_found() -> None:
    selected = [("A", Exchange.NSE, Decimal("0.9"), {})]
    correlations = {}
    assert _is_too_correlated("B", selected, correlations, Decimal("0.80")) is False


def test_ordered_pair() -> None:
    assert _ordered_pair("B", "A") == ("A", "B")
    assert _ordered_pair("A", "B") == ("A", "B")


def test_assign_ranks() -> None:
    candidates = [
        ("A", Exchange.NSE, Decimal("0.9"), {}),
        ("B", Exchange.NSE, Decimal("0.8"), {}),
    ]
    result = _assign_ranks(candidates)
    assert result[0].rank == 1
    assert result[1].rank == 2
