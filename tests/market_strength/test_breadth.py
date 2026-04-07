from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.breadth import (
    _ema,
    advance_decline_ratio,
    mcclellan_oscillator,
    up_down_volume_ratio,
)


def test_advance_decline_ratio_happy_path() -> None:
    assert advance_decline_ratio(120, 80) == Decimal("1.5")


def test_advance_decline_ratio_zero_decliners_fails() -> None:
    with pytest.raises(ConfigError, match="decliners cannot be zero"):
        advance_decline_ratio(10, 0)


def test_up_down_volume_ratio_happy_path() -> None:
    ratio = up_down_volume_ratio(Decimal("150000"), Decimal("100000"))
    assert ratio == Decimal("1.5")


def test_mcclellan_oscillator_deterministic_output() -> None:
    advances = [100, 110, 90, 120, 130, 105]
    declines = [80, 90, 95, 100, 110, 95]
    result = mcclellan_oscillator(advances, declines)
    assert result == mcclellan_oscillator(advances, declines)


@pytest.mark.parametrize(
    ("advancers", "decliners"),
    [(-1, 1), (1, -1)],
)
def test_advance_decline_ratio_negative_inputs_fail(advancers: int, decliners: int) -> None:
    with pytest.raises(ConfigError, match="cannot be negative"):
        advance_decline_ratio(advancers, decliners)


def test_up_down_volume_ratio_invalid_inputs_fail() -> None:
    with pytest.raises(ConfigError, match="cannot be negative"):
        up_down_volume_ratio(Decimal("-1"), Decimal("1"))
    with pytest.raises(ConfigError, match="cannot be zero"):
        up_down_volume_ratio(Decimal("1"), Decimal("0"))


def test_up_down_volume_ratio_zero_up_volume() -> None:
    """Test up_down_volume_ratio when up_volume is zero."""
    result = up_down_volume_ratio(Decimal("0"), Decimal("100"))
    assert result == Decimal("0")


@pytest.mark.parametrize(
    ("advances", "declines", "message"),
    [
        ([], [], "cannot be empty"),
        ([1], [1, 2], "equal length"),
        ([1], [1], "short_period < long_period"),
    ],
)
def test_mcclellan_oscillator_validation_failures(
    advances: list[int],
    declines: list[int],
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        mcclellan_oscillator(advances, declines, short_period=39, long_period=19)


def test_ema_empty_values_raises() -> None:
    """Test _ema raises ConfigError for empty values (lines 56-57)."""
    with pytest.raises(ConfigError, match="values cannot be empty"):
        _ema([], period=5)
