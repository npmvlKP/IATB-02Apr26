"""
Tests for position sizing models.
"""

from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.position_sizer import (
    PositionSizingInput,
    _validate_inputs,
    fixed_fractional_size,
    freeze_limit_slices,
    kelly_fraction,
    lot_rounded_size,
    volatility_adjusted_size,
)


def test_lot_rounded_size_below_lot() -> None:
    """raw_quantity < lot_size returns 0."""
    assert lot_rounded_size(Decimal("30"), Decimal("50")) == Decimal("0")


def test_lot_rounded_size_exact_multiple() -> None:
    """Exact multiple returns same value."""
    assert lot_rounded_size(Decimal("150"), Decimal("50")) == Decimal("150")


def test_lot_rounded_size_with_remainder() -> None:
    """With remainder, rounds down to nearest lot."""
    assert lot_rounded_size(Decimal("170"), Decimal("50")) == Decimal("150")


def test_lot_rounded_size_zero_lot_size() -> None:
    """lot_size <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="lot_size must be positive"):
        lot_rounded_size(Decimal("100"), Decimal("0"))


def test_freeze_limit_slices_single_slice() -> None:
    """Quantity <= freeze_limit returns single slice."""
    assert freeze_limit_slices(Decimal("150"), Decimal("50"), Decimal("200")) == [Decimal("150")]


def test_freeze_limit_slices_multiple_slices() -> None:
    """Quantity > freeze_limit splits into multiple slices."""
    assert freeze_limit_slices(Decimal("350"), Decimal("50"), Decimal("200")) == [
        Decimal("200"),
        Decimal("150"),
    ]


def test_freeze_limit_slices_exact_fit() -> None:
    """Quantity exactly fits multiple slices."""
    assert freeze_limit_slices(Decimal("400"), Decimal("50"), Decimal("200")) == [
        Decimal("200"),
        Decimal("200"),
    ]


def test_freeze_limit_slices_zero_quantity() -> None:
    """Zero quantity returns empty list."""
    assert freeze_limit_slices(Decimal("0"), Decimal("50"), Decimal("200")) == []


def test_freeze_limit_slices_lot_size_alignment() -> None:
    """Slices are aligned to lot_size."""
    # freeze_limit = 150, lot_size = 100 -> max_per_slice = 100
    # quantity = 250 -> rounded to 200 (2 lots of 100)
    # Split 200 into slices of max 100 each -> [100, 100]
    assert freeze_limit_slices(Decimal("250"), Decimal("100"), Decimal("150")) == [
        Decimal("100"),
        Decimal("100"),
    ]


def test_freeze_limit_slices_freeze_smaller_than_lot() -> None:
    """freeze_limit < lot_size raises ConfigError."""
    with pytest.raises(ConfigError, match="freeze_limit is smaller than lot_size"):
        freeze_limit_slices(Decimal("200"), Decimal("100"), Decimal("50"))


def test_freeze_limit_slices_invalid_lot_size() -> None:
    """lot_size <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="lot_size must be positive"):
        freeze_limit_slices(Decimal("200"), Decimal("0"), Decimal("100"))


def test_freeze_limit_slices_invalid_freeze_limit() -> None:
    """freeze_limit <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="freeze_limit must be positive"):
        freeze_limit_slices(Decimal("200"), Decimal("50"), Decimal("0"))


def test_fixed_fractional_size_standard() -> None:
    """Standard calculation with lot_size rounding."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    # risk_amount = 100000 * 0.02 = 2000
    # stop_distance = 10
    # quantity = 2000 / 10 = 200
    # lot_size = 50 -> rounded to 200 (already multiple)
    assert fixed_fractional_size(data, lot_size=Decimal("50")) == Decimal("200")


def test_fixed_fractional_size_with_lot_size_rounding() -> None:
    """Quantity gets rounded down to lot_size."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    # quantity = 200, lot_size = 75 -> 150 (2*75)
    assert fixed_fractional_size(data, lot_size=Decimal("75")) == Decimal("150")


def test_fixed_fractional_size_without_lot_size() -> None:
    """Returns raw quantity when lot_size is None."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    assert fixed_fractional_size(data) == Decimal("200")


def test_fixed_fractional_size_zero_risk() -> None:
    """risk_fraction = 0 raises ConfigError."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0"),
        realized_volatility=Decimal("0.01"),
    )
    with pytest.raises(ConfigError, match="risk_fraction must be in \\(0, 0.5\\]"):
        fixed_fractional_size(data)


def test_fixed_fractional_size_max_risk() -> None:
    """risk_fraction = 0.5 (max allowed)."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.5"),
        realized_volatility=Decimal("0.01"),
    )
    # risk_amount = 100000 * 0.5 = 50000
    # stop_distance = 10
    # quantity = 50000 / 10 = 5000
    assert fixed_fractional_size(data, lot_size=Decimal("50")) == Decimal("5000")


def test_fixed_fractional_size_stop_distance_zero() -> None:
    """stop_distance = 0 raises ConfigError."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("100"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    with pytest.raises(ConfigError, match="stop distance cannot be zero"):
        fixed_fractional_size(data)


def test_fixed_fractional_size_equity_zero() -> None:
    """equity <= 0 raises ConfigError."""
    data = PositionSizingInput(
        equity=Decimal("0"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    with pytest.raises(ConfigError, match="equity must be positive"):
        fixed_fractional_size(data)


def test_fixed_fractional_size_risk_fraction_too_large() -> None:
    """risk_fraction > 0.5 raises ConfigError."""
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.6"),
        realized_volatility=Decimal("0.01"),
    )
    with pytest.raises(ConfigError, match="risk_fraction must be in \\(0, 0.5\\]"):
        fixed_fractional_size(data)


def test_kelly_fraction_positive() -> None:
    """Standard kelly fraction calculation."""
    # win_rate = 0.6, win_loss_ratio = 2.0
    # kelly = 0.6 - (0.4 / 2.0) = 0.6 - 0.2 = 0.4
    assert kelly_fraction(Decimal("0.6"), Decimal("2.0")) == Decimal("0.4")


def test_kelly_fraction_negative() -> None:
    """Negative kelly fraction returns 0."""
    # win_rate = 0.3, win_loss_ratio = 2.0
    # kelly = 0.3 - (0.7 / 2.0) = 0.3 - 0.35 = -0.05 -> bounded to 0
    assert kelly_fraction(Decimal("0.3"), Decimal("2.0")) == Decimal("0")


def test_kelly_fraction_above_max() -> None:
    """kelly fraction above max_fraction returns max_fraction."""
    # win_rate = 0.8, win_loss_ratio = 2.0
    # kelly = 0.8 - (0.2 / 2.0) = 0.8 - 0.1 = 0.7 -> bounded to 0.5 (default max)
    assert kelly_fraction(Decimal("0.8"), Decimal("2.0")) == Decimal("0.5")


def test_kelly_fraction_custom_max() -> None:
    """kelly fraction with custom max_fraction."""
    # win_rate = 0.8, win_loss_ratio = 2.0, max_fraction = 0.3
    # kelly = 0.7 -> bounded to 0.3
    assert kelly_fraction(Decimal("0.8"), Decimal("2.0"), Decimal("0.3")) == Decimal("0.3")


def test_kelly_fraction_invalid_win_rate() -> None:
    """win_rate < 0 or > 1 raises ConfigError."""
    with pytest.raises(ConfigError, match="win_rate must be between 0 and 1"):
        kelly_fraction(Decimal("-0.1"), Decimal("2.0"))
    with pytest.raises(ConfigError, match="win_rate must be between 0 and 1"):
        kelly_fraction(Decimal("1.1"), Decimal("2.0"))


def test_kelly_fraction_invalid_win_loss_ratio() -> None:
    """win_loss_ratio <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="win_loss_ratio must be positive"):
        kelly_fraction(Decimal("0.6"), Decimal("0"))
    with pytest.raises(ConfigError, match="win_loss_ratio must be positive"):
        kelly_fraction(Decimal("0.6"), Decimal("-1.0"))


def test_kelly_fraction_invalid_max_fraction() -> None:
    """max_fraction <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="max_fraction must be positive"):
        kelly_fraction(Decimal("0.6"), Decimal("2.0"), Decimal("0"))
    with pytest.raises(ConfigError, match="max_fraction must be positive"):
        kelly_fraction(Decimal("0.6"), Decimal("2.0"), Decimal("-0.5"))


def test_volatility_adjusted_size_standard() -> None:
    """Standard volatility adjusted size."""
    # equity=100000, target_risk_fraction=0.02, realized_volatility=0.02
    # adjusted_fraction = 0.02 * (0.02 / 0.02) = 0.02
    # capped_fraction = min(0.5, max(0.01, 0.02)) = 0.02
    # quantity = 100000 * 0.02 = 2000
    assert volatility_adjusted_size(
        equity=Decimal("100000"),
        target_risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.02"),
    ) == Decimal("2000")


def test_volatility_adjusted_size_high_vol() -> None:
    """High volatility floors fraction at 0.01."""
    # equity = 100000, target_risk_fraction = 0.02, realized_volatility = 0.1 (high)
    # adjusted_fraction = 0.02 * (0.02 / 0.1) = 0.004 -> floored to 0.01
    # quantity = 100000 * 0.01 = 1000
    assert volatility_adjusted_size(
        equity=Decimal("100000"),
        target_risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.1"),
    ) == Decimal("1000")


def test_volatility_adjusted_size_low_vol() -> None:
    """Low volatility caps fraction at 0.5."""
    # To exceed 0.5: adjusted_fraction > 0.5
    # => realized_volatility < target_risk_fraction * base_volatility / 0.5
    # => realized_volatility < 0.02 * 0.02 / 0.5 = 0.0008
    # So set realized_volatility = 0.0007
    # adjusted_fraction = 0.02 * (0.02 / 0.0007) ≈ 0.02 * 28.57 ≈ 0.5714 -> capped to 0.5
    # quantity = 100000 * 0.5 = 50000
    assert volatility_adjusted_size(
        equity=Decimal("100000"),
        target_risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.0007"),
    ) == Decimal("50000")


def test_volatility_adjusted_size_with_lot_size() -> None:
    """Quantity gets rounded down to lot_size."""
    # Standard case: quantity = 2000, lot_size = 500 -> 2000 (multiple)
    assert volatility_adjusted_size(
        equity=Decimal("100000"),
        target_risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.02"),
        lot_size=Decimal("500"),
    ) == Decimal("2000")
    # Now with rounding: quantity = 2000, lot_size = 700 -> 1400 (2*700)
    assert volatility_adjusted_size(
        equity=Decimal("100000"),
        target_risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.02"),
        lot_size=Decimal("700"),
    ) == Decimal("1400")


def test_volatility_adjusted_size_invalid_equity() -> None:
    """equity <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="equity must be positive"):
        volatility_adjusted_size(
            equity=Decimal("0"),
            target_risk_fraction=Decimal("0.02"),
            realized_volatility=Decimal("0.02"),
        )


def test_volatility_adjusted_size_invalid_target_risk() -> None:
    """target_risk_fraction <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="target_risk_fraction must be positive"):
        volatility_adjusted_size(
            equity=Decimal("100000"),
            target_risk_fraction=Decimal("0"),
            realized_volatility=Decimal("0.02"),
        )


def test_volatility_adjusted_size_invalid_volatility() -> None:
    """realized_volatility <= 0 raises ConfigError."""
    with pytest.raises(ConfigError, match="realized_volatility must be positive"):
        volatility_adjusted_size(
            equity=Decimal("100000"),
            target_risk_fraction=Decimal("0.02"),
            realized_volatility=Decimal("0"),
        )


def test_validate_inputs() -> None:
    """Test the internal validation function."""
    # Valid input should not raise
    data = PositionSizingInput(
        equity=Decimal("100000"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        risk_fraction=Decimal("0.02"),
        realized_volatility=Decimal("0.01"),
    )
    _validate_inputs(data)  # Should not raise

    # Test each validation branch
    with pytest.raises(ConfigError, match="equity must be positive"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("0"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.02"),
                realized_volatility=Decimal("0.01"),
            )
        )

    with pytest.raises(ConfigError, match="entry_price and stop_price must be positive"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("100000"),
                entry_price=Decimal("0"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.02"),
                realized_volatility=Decimal("0.01"),
            )
        )

    with pytest.raises(ConfigError, match="entry_price and stop_price must be positive"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("100000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("0"),
                risk_fraction=Decimal("0.02"),
                realized_volatility=Decimal("0.01"),
            )
        )

    with pytest.raises(ConfigError, match="risk_fraction must be in \\(0, 0.5\\]"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("100000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0"),
                realized_volatility=Decimal("0.01"),
            )
        )

    with pytest.raises(ConfigError, match="risk_fraction must be in \\(0, 0.5\\]"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("100000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.6"),
                realized_volatility=Decimal("0.01"),
            )
        )

    with pytest.raises(ConfigError, match="realized_volatility must be positive"):
        _validate_inputs(
            PositionSizingInput(
                equity=Decimal("100000"),
                entry_price=Decimal("100"),
                stop_price=Decimal("90"),
                risk_fraction=Decimal("0.02"),
                realized_volatility=Decimal("0"),
            )
        )
