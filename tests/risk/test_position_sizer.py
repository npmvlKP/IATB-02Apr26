import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.risk.position_sizer import (
    PositionSizingInput,
    fixed_fractional_size,
    kelly_fraction,
    volatility_adjusted_size,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


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


def test_fixed_fractional_size_with_lot_size() -> None:
    inputs = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("200"),
        stop_price=Decimal("190"),
        risk_fraction=Decimal("0.01"),
        realized_volatility=Decimal("0.02"),
    )
    result = fixed_fractional_size(inputs, lot_size=Decimal("75"))
    assert result % Decimal("75") == Decimal("0")
    assert result <= Decimal("100")
    assert result == Decimal("75")


def test_fixed_fractional_size_lot_size_none_unchanged() -> None:
    inputs = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("200"),
        stop_price=Decimal("190"),
        risk_fraction=Decimal("0.01"),
        realized_volatility=Decimal("0.02"),
    )
    assert fixed_fractional_size(inputs, lot_size=None) == Decimal("100")


def test_volatility_adjusted_size_with_lot_size() -> None:
    result = volatility_adjusted_size(
        Decimal("100000"),
        Decimal("0.02"),
        Decimal("0.04"),
        lot_size=Decimal("250"),
    )
    assert result % Decimal("250") == Decimal("0")
    assert result <= Decimal("1000")


def test_volatility_adjusted_size_lot_size_none_unchanged() -> None:
    result = volatility_adjusted_size(
        Decimal("100000"),
        Decimal("0.02"),
        Decimal("0.04"),
        lot_size=None,
    )
    assert result == Decimal("1000")


def test_kelly_fraction_edge_cases() -> None:
    with pytest.raises(ConfigError, match="win_loss_ratio must be positive"):
        kelly_fraction(Decimal("0.5"), Decimal("0"))
    with pytest.raises(ConfigError, match="max_fraction must be positive"):
        kelly_fraction(Decimal("0.5"), Decimal("1.5"), Decimal("0"))
    result = kelly_fraction(Decimal("0"), Decimal("1.5"))
    assert result == Decimal("0")


def test_volatility_adjusted_size_validations() -> None:
    with pytest.raises(ConfigError, match="target_risk_fraction must be positive"):
        volatility_adjusted_size(Decimal("100000"), Decimal("0"), Decimal("0.02"))
    with pytest.raises(ConfigError, match="realized_volatility must be positive"):
        volatility_adjusted_size(Decimal("100000"), Decimal("0.02"), Decimal("0"))


def test_position_sizing_input_validations() -> None:
    with pytest.raises(ConfigError, match="equity must be positive"):
        fixed_fractional_size(
            PositionSizingInput(
                equity=Decimal("0"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.01"),
                realized_volatility=Decimal("0.02"),
            )
        )
    with pytest.raises(ConfigError, match="entry_price and stop_price must be positive"):
        fixed_fractional_size(
            PositionSizingInput(
                equity=Decimal("1000"),
                entry_price=Decimal("0"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.01"),
                realized_volatility=Decimal("0.02"),
            )
        )
    with pytest.raises(ConfigError, match="risk_fraction must be in"):
        fixed_fractional_size(
            PositionSizingInput(
                equity=Decimal("1000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.6"),
                realized_volatility=Decimal("0.02"),
            )
        )
    with pytest.raises(ConfigError, match="realized_volatility must be positive"):
        fixed_fractional_size(
            PositionSizingInput(
                equity=Decimal("1000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.01"),
                realized_volatility=Decimal("0"),
            )
        )
