"""Tests for sector_strength.py module."""

import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.selection.sector_strength import (
    apply_sector_adjustment,
    sector_relative_score,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_sector_relative_score_basic() -> None:
    """Test sector_relative_score with basic inputs."""
    instrument_score = Decimal("0.7")
    sector_scores = [Decimal("0.5"), Decimal("0.6"), Decimal("0.8")]
    result = sector_relative_score(instrument_score, sector_scores)

    # Sector mean = 0.63, relative = 0.7 - 0.63 + 0.5 = 0.57
    assert Decimal("0.5") <= result <= Decimal("1.0")


def test_sector_relative_score_with_above_average() -> None:
    """Test sector_relative_score when instrument is above average."""
    instrument_score = Decimal("0.9")
    sector_scores = [Decimal("0.5"), Decimal("0.6"), Decimal("0.7")]
    result = sector_relative_score(instrument_score, sector_scores)

    # Should be higher than 0.5 since instrument is above sector average
    assert result > Decimal("0.5")


def test_sector_relative_score_with_below_average() -> None:
    """Test sector_relative_score when instrument is below average."""
    instrument_score = Decimal("0.4")
    sector_scores = [Decimal("0.6"), Decimal("0.7"), Decimal("0.8")]
    result = sector_relative_score(instrument_score, sector_scores)

    # Should be lower than 0.5 since instrument is below sector average
    assert result < Decimal("0.5")


def test_sector_relative_score_at_average() -> None:
    """Test sector_relative_score when instrument equals sector average."""
    instrument_score = Decimal("0.6")
    sector_scores = [Decimal("0.5"), Decimal("0.6"), Decimal("0.7")]
    result = sector_relative_score(instrument_score, sector_scores)

    # Should be exactly 0.5 when instrument equals sector average
    assert result == Decimal("0.5")


def test_sector_relative_score_clamps_at_zero() -> None:
    """Test sector_relative_score clamps at 0.0 for very low scores."""
    instrument_score = Decimal("0.0")
    sector_scores = [Decimal("0.9"), Decimal("0.95"), Decimal("1.0")]
    result = sector_relative_score(instrument_score, sector_scores)

    assert result == Decimal("0.0")


def test_sector_relative_score_clamps_at_one() -> None:
    """Test sector_relative_score clamps at 1.0 for very high scores."""
    instrument_score = Decimal("1.0")
    sector_scores = [Decimal("0.0"), Decimal("0.05"), Decimal("0.1")]
    result = sector_relative_score(instrument_score, sector_scores)

    assert result == Decimal("1.0")


def test_sector_relative_score_rejects_empty_sector_scores() -> None:
    """Test sector_relative_score raises ConfigError for empty sector_scores."""
    with pytest.raises(ConfigError, match="sector_scores cannot be empty"):
        sector_relative_score(Decimal("0.5"), [])


def test_sector_relative_score_with_single_sector_score() -> None:
    """Test sector_relative_score with single sector score."""
    instrument_score = Decimal("0.7")
    sector_scores = [Decimal("0.5")]
    result = sector_relative_score(instrument_score, sector_scores)

    # Should return 0.7 since mean is 0.5 and adjustment is 0
    assert result == Decimal("0.7")


def test_apply_sector_adjustment_basic() -> None:
    """Test apply_sector_adjustment with basic inputs."""
    scores_by_symbol = {
        "RELIANCE": Decimal("0.8"),
        "TCS": Decimal("0.7"),
        "INFY": Decimal("0.6"),
        "HDFC": Decimal("0.9"),
    }
    sector_map = {
        "RELIANCE": "OIL&GAS",
        "TCS": "IT",
        "INFY": "IT",
        "HDFC": "BANKING",
    }

    result = apply_sector_adjustment(scores_by_symbol, sector_map)

    # All symbols should be in result
    assert set(result.keys()) == set(scores_by_symbol.keys())

    # TCS and INFY should be adjusted relative to each other
    # TCS is above IT mean (0.65), so should be > 0.5
    assert result["TCS"] > Decimal("0.5")
    # INFY is below IT mean (0.65), so should be < 0.5
    assert result["INFY"] < Decimal("0.5")


def test_apply_sector_adjustment_with_unknown_sector() -> None:
    """Test apply_sector_adjustment handles unknown sector."""
    scores_by_symbol = {
        "STOCK1": Decimal("0.7"),
        "STOCK2": Decimal("0.5"),
    }
    sector_map = {
        "STOCK1": "TECH",
        # STOCK2 not in map
    }

    result = apply_sector_adjustment(scores_by_symbol, sector_map)

    # STOCK2 should be treated as unknown sector with single score
    # So it should return the same score
    assert result["STOCK2"] == Decimal("0.5")


def test_apply_sector_adjustment_all_same_sector() -> None:
    """Test apply_sector_adjustment when all symbols in same sector."""
    scores_by_symbol = {
        "A": Decimal("0.4"),
        "B": Decimal("0.5"),
        "C": Decimal("0.6"),
    }
    sector_map = {
        "A": "SECTOR1",
        "B": "SECTOR1",
        "C": "SECTOR1",
    }

    result = apply_sector_adjustment(scores_by_symbol, sector_map)

    # Mean is 0.5, so:
    # A should be below 0.5
    assert result["A"] < Decimal("0.5")
    # B should be exactly 0.5
    assert result["B"] == Decimal("0.5")
    # C should be above 0.5
    assert result["C"] > Decimal("0.5")


def test_apply_sector_adjustment_single_symbol() -> None:
    """Test apply_sector_adjustment with single symbol."""
    scores_by_symbol = {"SOLO": Decimal("0.8")}
    sector_map = {"SOLO": "ALONE"}

    result = apply_sector_adjustment(scores_by_symbol, sector_map)

    # Should return same score when single symbol in sector
    assert result["SOLO"] == Decimal("0.5")


def test_apply_sector_adjustment_preserves_order() -> None:
    """Test apply_sector_adjustment preserves relative ranking within sector."""
    scores_by_symbol = {
        "LOW": Decimal("0.3"),
        "MID": Decimal("0.5"),
        "HIGH": Decimal("0.9"),
    }
    sector_map = {
        "LOW": "SAME",
        "MID": "SAME",
        "HIGH": "SAME",
    }

    result = apply_sector_adjustment(scores_by_symbol, sector_map)

    # Ranking should be preserved
    assert result["LOW"] < result["MID"] < result["HIGH"]
