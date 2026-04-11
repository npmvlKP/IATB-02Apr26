"""Tests for correlation_matrix.py module."""

import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.selection.correlation_matrix import compute_pairwise_correlations

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_compute_pairwise_correlations_basic() -> None:
    """Test compute_pairwise_correlations with basic inputs."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
        "B": [Decimal("20"), Decimal("22"), Decimal("24"), Decimal("26"), Decimal("28")],
    }

    result = compute_pairwise_correlations(price_series)

    assert len(result) == 1
    assert ("A", "B") in result
    # Both series are increasing, so correlation should be 1
    assert result[("A", "B")] == Decimal("1")


def test_compute_pairwise_correlations_three_series() -> None:
    """Test compute_pairwise_correlations with three series."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
        "B": [Decimal("20"), Decimal("22"), Decimal("24"), Decimal("26"), Decimal("28")],
        "C": [Decimal("100"), Decimal("95"), Decimal("105"), Decimal("90"), Decimal("110")],
    }

    result = compute_pairwise_correlations(price_series)

    # Should have 3 pairs: (A,B), (A,C), (B,C)
    assert len(result) == 3
    assert ("A", "B") in result
    assert ("A", "C") in result
    assert ("B", "C") in result

    # All correlations should be valid numbers
    for corr in result.values():
        assert Decimal("-1") <= corr <= Decimal("1")


def test_compute_pairwise_correlations_single_series() -> None:
    """Test compute_pairwise_correlations with single series returns empty."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
    }

    result = compute_pairwise_correlations(price_series)

    assert result == {}


def test_compute_pairwise_correlations_empty() -> None:
    """Test compute_pairwise_correlations with empty dict returns empty."""
    result = compute_pairwise_correlations({})
    assert result == {}


def test_compute_pairwise_correlations_zero_correlation() -> None:
    """Test compute_pairwise_correlations with uncorrelated series."""
    price_series = {
        "A": [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("50")],
        "B": [Decimal("10"), Decimal("30"), Decimal("20"), Decimal("40"), Decimal("30")],
    }

    result = compute_pairwise_correlations(price_series)

    assert len(result) == 1
    # Should return a valid correlation value
    assert Decimal("-1") <= result[("A", "B")] <= Decimal("1")


def test_compute_pairwise_correlations_with_zero_prices() -> None:
    """Test compute_pairwise_correlations handles zero prices."""
    price_series = {
        "A": [Decimal("0"), Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")],
        "B": [Decimal("0"), Decimal("20"), Decimal("40"), Decimal("60"), Decimal("80")],
    }

    result = compute_pairwise_correlations(price_series)

    # First return is 0/0 = 0, subsequent returns should correlate
    assert len(result) == 1
    assert ("A", "B") in result


def test_compute_pairwise_correlations_different_lengths() -> None:
    """Test compute_pairwise_correlations with different length series."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
        "B": [Decimal("20"), Decimal("22"), Decimal("24")],
    }

    result = compute_pairwise_correlations(price_series)

    # Should use the shorter length (3 price points = 2 returns)
    assert len(result) == 1
    assert ("A", "B") in result


def test_compute_pairwise_correlations_alphabetical_keys() -> None:
    """Test compute_pairwise_correlations keys are alphabetically ordered."""
    price_series = {
        "Z": [Decimal("10"), Decimal("11"), Decimal("12")],
        "A": [Decimal("20"), Decimal("22"), Decimal("24")],
    }

    result = compute_pairwise_correlations(price_series)

    # Keys should be alphabetically ordered
    assert ("A", "Z") in result
    assert ("Z", "A") not in result


def test_compute_pairwise_correlations_single_price_point() -> None:
    """Test compute_pairwise_correlations raises ConfigError for single price."""
    price_series = {
        "A": [Decimal("10")],
        "B": [Decimal("20")],
    }

    with pytest.raises(ConfigError, match="price series must have at least 2 points"):
        compute_pairwise_correlations(price_series)


def test_compute_pairwise_correlations_constant_prices() -> None:
    """Test compute_pairwise_correlations with constant prices (zero variance)."""
    price_series = {
        "A": [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")],
        "B": [Decimal("20"), Decimal("20"), Decimal("20"), Decimal("20"), Decimal("20")],
    }

    result = compute_pairwise_correlations(price_series)

    # With zero variance, correlation should be 0
    assert len(result) == 1
    assert result[("A", "B")] == Decimal("0")


def test_compute_pairwise_correlations_partial_constant() -> None:
    """Test compute_pairwise_correlations with one constant series."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
        "B": [Decimal("20"), Decimal("20"), Decimal("20"), Decimal("20"), Decimal("20")],
    }

    result = compute_pairwise_correlations(price_series)

    # With zero variance in B, correlation should be 0
    assert len(result) == 1
    assert result[("A", "B")] == Decimal("0")


def test_compute_pairwise_correlations_clamping() -> None:
    """Test compute_pairwise_correlations clamps to [-1, 1]."""
    price_series = {
        "A": [Decimal("10"), Decimal("11"), Decimal("12"), Decimal("13"), Decimal("14")],
        "B": [Decimal("20"), Decimal("22"), Decimal("24"), Decimal("26"), Decimal("28")],
    }

    result = compute_pairwise_correlations(price_series)

    # Result should be within bounds
    corr = result[("A", "B")]
    assert Decimal("-1") <= corr <= Decimal("1")


def test_compute_pairwise_correlations_minimal_valid_input() -> None:
    """Test compute_pairwise_correlations with minimal valid input (2 series, 2 points)."""
    price_series = {
        "A": [Decimal("10"), Decimal("11")],
        "B": [Decimal("20"), Decimal("22")],
    }

    result = compute_pairwise_correlations(price_series)

    assert len(result) == 1
    assert ("A", "B") in result


def test_compute_pairwise_correlations_large_series() -> None:
    """Test compute_pairwise_correlations with larger series."""
    prices_a = [Decimal(str(10 + i)) for i in range(100)]
    prices_b = [Decimal(str(20 + 2 * i)) for i in range(100)]

    price_series = {
        "A": prices_a,
        "B": prices_b,
    }

    result = compute_pairwise_correlations(price_series)

    assert len(result) == 1
    # Should be very close to 1
    assert result[("A", "B")] > Decimal("0.99")

    # Iterate through values to avoid B007
    for value in result.values():
        assert Decimal("-1") <= value <= Decimal("1")
