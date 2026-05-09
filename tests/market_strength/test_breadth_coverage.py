"""Comprehensive coverage tests for breadth.py market-strength indicators."""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.breadth import (
    _ema,
    advance_decline_ratio,
    mcclellan_oscillator,
    up_down_volume_ratio,
)

# ---------------------------------------------------------------------------
# advance_decline_ratio
# ---------------------------------------------------------------------------


def test_advance_decline_ratio_normal() -> None:
    """Happy path: advancers=3, decliners=2 → 1.5"""
    result = advance_decline_ratio(3, 2)
    assert result == Decimal("1.5")


def test_advance_decline_ratio_zero_advancers() -> None:
    """Edge: advancers=0 → returns 0."""
    result = advance_decline_ratio(0, 5)
    assert result == Decimal("0")


def test_advance_decline_ratio_negative_advancers_fails() -> None:
    """Error: negative advancers → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be negative"):
        advance_decline_ratio(-1, 5)


def test_advance_decline_ratio_decliners_zero_fails() -> None:
    """Error: decliners=0 → ConfigError."""
    with pytest.raises(ConfigError, match="decliners cannot be zero"):
        advance_decline_ratio(3, 0)


def test_advance_decline_ratio_negative_decliners_fails() -> None:
    """Error: negative decliners → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be negative"):
        advance_decline_ratio(3, -1)


# ---------------------------------------------------------------------------
# up_down_volume_ratio
# ---------------------------------------------------------------------------


def test_up_down_volume_ratio_normal() -> None:
    """Happy path: up=100, down=50 → 2."""
    result = up_down_volume_ratio(Decimal("100"), Decimal("50"))
    assert result == Decimal("2")


def test_up_down_volume_ratio_zero_up_volume() -> None:
    """Edge: up_volume=0 → returns 0."""
    result = up_down_volume_ratio(Decimal("0"), Decimal("100"))
    assert result == Decimal("0")


def test_up_down_volume_ratio_down_volume_zero_fails() -> None:
    """Error: down_volume=0 → ConfigError."""
    with pytest.raises(ConfigError, match="down_volume cannot be zero"):
        up_down_volume_ratio(Decimal("100"), Decimal("0"))


def test_up_down_volume_ratio_negative_down_volume_fails() -> None:
    """Error: negative down_volume → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be negative"):
        up_down_volume_ratio(Decimal("100"), Decimal("-1"))


def test_up_down_volume_ratio_negative_up_volume_fails() -> None:
    """Error: negative up_volume → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be negative"):
        up_down_volume_ratio(Decimal("-1"), Decimal("50"))


# ---------------------------------------------------------------------------
# _ema
# ---------------------------------------------------------------------------


def test_ema_known_values() -> None:
    """Happy path: _ema on known values."""
    values = [Decimal("10"), Decimal("12"), Decimal("14")]
    result = _ema(values, period=2)
    assert isinstance(result, Decimal)


def test_ema_single_element() -> None:
    """Edge: single-element series → returns that element."""
    values = [Decimal("42")]
    result = _ema(values, period=5)
    assert result == Decimal("42")


def test_ema_empty_values_fails() -> None:
    """Error: empty values → ConfigError."""
    with pytest.raises(ConfigError, match="values cannot be empty"):
        _ema([], period=5)


# ---------------------------------------------------------------------------
# mcclellan_oscillator
# ---------------------------------------------------------------------------


def test_mcclellan_oscillator_normal() -> None:
    """Happy path: typical advance/decline sequences."""
    advances = [100, 110, 90, 120, 130, 105]
    declines = [80, 90, 95, 100, 110, 95]
    result = mcclellan_oscillator(advances, declines)
    assert isinstance(result, Decimal)


def test_mcclellan_oscillator_short_series() -> None:
    """Edge: very short series (single element)."""
    advances = [50]
    declines = [30]
    result = mcclellan_oscillator(advances, declines)
    assert isinstance(result, Decimal)


def test_mcclellan_oscillator_empty_advances_fails() -> None:
    """Error: empty advances → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be empty"):
        mcclellan_oscillator([], [1, 2, 3])


def test_mcclellan_oscillator_empty_declines_fails() -> None:
    """Error: empty declines → ConfigError."""
    with pytest.raises(ConfigError, match="cannot be empty"):
        mcclellan_oscillator([1, 2, 3], [])


def test_mcclellan_oscillator_unequal_lengths_fails() -> None:
    """Error: unequal lengths → ConfigError."""
    with pytest.raises(ConfigError, match="equal length"):
        mcclellan_oscillator([1, 2, 3], [1, 2])


def test_mcclellan_oscillator_short_period_zero_fails() -> None:
    """Error: short_period=0 → ConfigError."""
    with pytest.raises(ConfigError, match="short_period < long_period"):
        mcclellan_oscillator([1, 2, 3], [1, 2, 3], short_period=0, long_period=5)


def test_mcclellan_oscillator_short_period_negative_fails() -> None:
    """Error: short_period<0 → ConfigError."""
    with pytest.raises(ConfigError, match="short_period < long_period"):
        mcclellan_oscillator([1, 2, 3], [1, 2, 3], short_period=-1, long_period=5)


def test_mcclellan_oscillator_short_period_gte_long_period_fails() -> None:
    """Error: short_period >= long_period → ConfigError."""
    with pytest.raises(ConfigError, match="short_period < long_period"):
        mcclellan_oscillator([1, 2, 3], [1, 2, 3], short_period=5, long_period=5)


def test_mcclellan_oscillator_long_period_zero_fails() -> None:
    """Error: long_period=0 → ConfigError."""
    with pytest.raises(ConfigError, match="short_period < long_period"):
        mcclellan_oscillator([1, 2, 3], [1, 2, 3], short_period=-1, long_period=0)
