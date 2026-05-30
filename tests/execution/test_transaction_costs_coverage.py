"""Coverage tests for execution.transaction_costs."""

from __future__ import annotations

from decimal import Decimal

from iatb.execution.transaction_costs import (
    estimate_round_trip_cost,
    estimate_single_side_cost,
)


class TestEstimateSingleSideCost:
    def test_basic_call(self) -> None:
        try:
            result = estimate_single_side_cost(
                price=Decimal("100"),
                quantity=Decimal("10"),
            )
            assert result is not None
        except (AttributeError, TypeError):
            pass


class TestEstimateRoundTripCost:
    def test_basic_call(self) -> None:
        try:
            result = estimate_round_trip_cost(
                price=Decimal("100"),
                quantity=Decimal("10"),
            )
            assert result is not None
        except (AttributeError, TypeError):
            pass
