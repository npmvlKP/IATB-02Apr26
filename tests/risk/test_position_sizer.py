from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.position_sizer import (
    PositionSizingInput,
    fixed_fractional_size,
    kelly_fraction,
    volatility_adjusted_size,
)


def test_fixed_fractional_size_computes_expected_quantity() -> None:
    inputs = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("200"),
        stop_price=Decimal("190"),
        risk_fraction=Decimal("0.01"),
        realized_volatility=Decimal("0.02"),
    )
    assert fixed_fractional_size(inputs) == Decimal("100")


def test_kelly_fraction_and_volatility_adjusted_size_bounds() -> None:
    kelly = kelly_fraction(Decimal("0.55"), Decimal("1.5"))
    assert kelly > Decimal("0")
    assert kelly <= Decimal("0.5")
    adjusted = volatility_adjusted_size(Decimal("100000"), Decimal("0.02"), Decimal("0.04"))
    assert adjusted == Decimal("1000")


def test_position_sizer_validations_raise_config_error() -> None:
    with pytest.raises(ConfigError, match="between 0 and 1"):
        kelly_fraction(Decimal("2"), Decimal("1.5"))
    with pytest.raises(ConfigError, match="must be positive"):
        volatility_adjusted_size(Decimal("0"), Decimal("0.02"), Decimal("0.01"))
    bad = PositionSizingInput(
        equity=Decimal("1000"),
        entry_price=Decimal("10"),
        stop_price=Decimal("10"),
        risk_fraction=Decimal("0.01"),
        realized_volatility=Decimal("0.01"),
    )
    with pytest.raises(ConfigError, match="stop distance cannot be zero"):
        fixed_fractional_size(bad)
