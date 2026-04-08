"""Tests for lot_rounded_size and freeze_limit_slices.
Optimized with fast/medium/slow settings for better performance.
"""

import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from hypothesis import given
from hypothesis import strategies as st
from iatb.core.exceptions import ConfigError
from iatb.risk.position_sizer import freeze_limit_slices, lot_rounded_size

from tests.conftest_optimized import (
    HYPOTHESIS_FAST_SETTINGS,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestLotRoundedSize:
    def test_exact_multiple(self) -> None:
        assert lot_rounded_size(Decimal("150"), Decimal("75")) == Decimal("150")

    def test_rounds_down(self) -> None:
        assert lot_rounded_size(Decimal("149"), Decimal("75")) == Decimal("75")

    def test_below_lot_size_returns_zero(self) -> None:
        assert lot_rounded_size(Decimal("10"), Decimal("75")) == Decimal("0")

    def test_zero_quantity(self) -> None:
        assert lot_rounded_size(Decimal("0"), Decimal("75")) == Decimal("0")

    def test_invalid_lot_size(self) -> None:
        with pytest.raises(ConfigError, match="lot_size must be positive"):
            lot_rounded_size(Decimal("100"), Decimal("0"))


class TestFreezeLimitSlices:
    def test_single_slice(self) -> None:
        slices = freeze_limit_slices(Decimal("150"), Decimal("75"), Decimal("1800"))
        assert slices == [Decimal("150")]

    def test_multiple_slices(self) -> None:
        slices = freeze_limit_slices(Decimal("3000"), Decimal("75"), Decimal("1800"))
        assert all(s <= Decimal("1800") for s in slices)
        assert sum(slices) == Decimal("3000")

    def test_exact_freeze_boundary(self) -> None:
        slices = freeze_limit_slices(Decimal("1800"), Decimal("75"), Decimal("1800"))
        assert slices == [Decimal("1800")]

    def test_quantity_below_lot_returns_empty(self) -> None:
        assert freeze_limit_slices(Decimal("10"), Decimal("75"), Decimal("1800")) == []

    def test_invalid_freeze_limit(self) -> None:
        with pytest.raises(ConfigError, match="freeze_limit must be positive"):
            freeze_limit_slices(Decimal("100"), Decimal("1"), Decimal("0"))


_qty = st.decimals(
    min_value="0",
    max_value="100000",
    places=0,
    allow_nan=False,
    allow_infinity=False,
)
_lot = st.decimals(
    min_value="1",
    max_value="100",
    places=0,
    allow_nan=False,
    allow_infinity=False,
)


@given(raw=_qty, lot=_lot)
@HYPOTHESIS_FAST_SETTINGS
def test_lot_rounded_invariants(raw: Decimal, lot: Decimal) -> None:
    result = lot_rounded_size(raw, lot)
    assert result >= Decimal("0")
    assert result <= raw
    if result > Decimal("0"):
        assert result % lot == Decimal("0")


@given(
    qty=st.decimals(
        min_value="1",
        max_value="10000",
        places=0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
@HYPOTHESIS_FAST_SETTINGS
def test_freeze_slices_sum_equals_rounded(qty: Decimal) -> None:
    lot = Decimal("75")
    freeze = Decimal("1800")
    slices = freeze_limit_slices(qty, lot, freeze)
    rounded = lot_rounded_size(qty, lot)
    assert sum(slices) == rounded
    assert all(s <= freeze for s in slices)
