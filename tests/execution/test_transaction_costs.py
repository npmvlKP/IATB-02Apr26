from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.execution.transaction_costs import estimate_round_trip_cost, estimate_single_side_cost


def test_transaction_cost_calculation_accuracy() -> None:
    single = estimate_single_side_cost(Decimal("100000"), "fo")
    round_trip = estimate_round_trip_cost(Decimal("100000"), "fo")
    assert single == Decimal("16.622600000")
    assert round_trip == Decimal("33.245200000")


def test_transaction_cost_validation() -> None:
    with pytest.raises(ConfigError, match="must be positive"):
        estimate_single_side_cost(Decimal("0"), "fo")
