"""Tests for selection utility functions."""

from decimal import Decimal

from iatb.selection._util import (
    DirectionalIntent,
    clamp_01,
    confidence_ramp,
    rank_percentile,
)


class TestDirectionalIntent:
    def test_values(self) -> None:
        assert DirectionalIntent.LONG == "LONG"
        assert DirectionalIntent.SHORT == "SHORT"
        assert DirectionalIntent.NEUTRAL == "NEUTRAL"


class TestClamp01:
    def test_zero(self) -> None:
        assert clamp_01(Decimal("0")) == Decimal("0")

    def test_one(self) -> None:
        assert clamp_01(Decimal("1")) == Decimal("1")

    def test_half(self) -> None:
        assert clamp_01(Decimal("0.5")) == Decimal("0.5")

    def test_negative_clamps_to_zero(self) -> None:
        assert clamp_01(Decimal("-1")) == Decimal("0")

    def test_over_one_clamps_to_one(self) -> None:
        assert clamp_01(Decimal("2")) == Decimal("1")


class TestConfidenceRamp:
    def test_below_threshold_returns_zero(self) -> None:
        assert confidence_ramp(Decimal("0.1")) == Decimal("0")

    def test_at_threshold_returns_zero(self) -> None:
        assert confidence_ramp(Decimal("0.20")) == Decimal("0")

    def test_above_threshold(self) -> None:
        result = confidence_ramp(Decimal("0.60"))
        assert Decimal("0") < result <= Decimal("1")

    def test_at_one_returns_one(self) -> None:
        assert confidence_ramp(Decimal("1.0")) == Decimal("1")

    def test_custom_threshold(self) -> None:
        result = confidence_ramp(Decimal("0.5"), threshold=Decimal("0.5"))
        assert result == Decimal("0")

    def test_zero_ceiling_returns_one(self) -> None:
        assert confidence_ramp(Decimal("0.5"), threshold=Decimal("2")) == Decimal("0")


class TestRankPercentile:
    def test_empty_list(self) -> None:
        assert rank_percentile([]) == []

    def test_single_element(self) -> None:
        assert rank_percentile([Decimal("5")]) == [Decimal("1")]

    def test_two_elements(self) -> None:
        result = rank_percentile([Decimal("3"), Decimal("7")])
        assert result == [Decimal("0"), Decimal("1")]

    def test_all_equal(self) -> None:
        result = rank_percentile([Decimal("5"), Decimal("5"), Decimal("5")])
        assert result == [Decimal("0"), Decimal("0"), Decimal("0")]

    def test_preserves_order(self) -> None:
        values = [Decimal("1"), Decimal("3"), Decimal("2")]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[1] == Decimal("1")
        assert result[2] == Decimal("0.5")

    def test_multiple_values(self) -> None:
        values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[-1] == Decimal("1")
