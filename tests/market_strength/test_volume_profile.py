from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.volume_profile import _build_value_area, build_volume_profile


def test_build_volume_profile_returns_poc_vah_val() -> None:
    profile = build_volume_profile(
        prices=[Decimal("100"), Decimal("101"), Decimal("100"), Decimal("102")],
        volumes=[Decimal("10"), Decimal("30"), Decimal("40"), Decimal("20")],
    )
    assert profile.poc == Decimal("100")
    assert profile.vah >= profile.val
    assert profile.total_volume == Decimal("100")


def test_build_volume_profile_invalid_value_area_fails() -> None:
    with pytest.raises(ConfigError, match="value_area must be between 0 and 1"):
        build_volume_profile(
            prices=[Decimal("100")],
            volumes=[Decimal("10")],
            value_area=Decimal("1"),
        )


def test_build_volume_profile_negative_volume_fails() -> None:
    with pytest.raises(ConfigError, match="cannot include negative values"):
        build_volume_profile(
            prices=[Decimal("100")],
            volumes=[Decimal("-1")],
        )


def test_build_value_area_empty_bins_returns_empty_set() -> None:
    selected = _build_value_area([], Decimal("0"), Decimal("0.7"))
    assert selected == set()


def test_build_volume_profile_empty_prices_raises() -> None:
    """Test that empty prices raises ConfigError."""
    with pytest.raises(ConfigError, match="cannot be empty"):
        build_volume_profile(
            prices=[],
            volumes=[Decimal("10")],
        )


def test_build_volume_profile_unequal_length_raises() -> None:
    """Test that unequal length raises ConfigError."""
    with pytest.raises(ConfigError, match="must have equal length"):
        build_volume_profile(
            prices=[Decimal("100"), Decimal("101")],
            volumes=[Decimal("10")],
        )
