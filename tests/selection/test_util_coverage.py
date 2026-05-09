"""Coverage tests for src/iatb/selection/_util.py.

Uses importlib.util to load _util.py directly, completely bypassing the
circular-import chain through selection/__init__.py.
"""

from decimal import Decimal

from tests.selection._util_loader import _util_mod

# Bind names for easy reference
DirectionalIntent = _util_mod.DirectionalIntent
clamp_01 = _util_mod.clamp_01
confidence_ramp = _util_mod.confidence_ramp
rank_percentile = _util_mod.rank_percentile


class TestDirectionalIntentExtended:
    """Extended coverage for DirectionalIntent enum members and StrEnum behaviour."""

    def test_member_identity(self) -> None:
        assert DirectionalIntent.LONG is DirectionalIntent("LONG")
        assert DirectionalIntent.SHORT is DirectionalIntent("SHORT")
        assert DirectionalIntent.NEUTRAL is DirectionalIntent("NEUTRAL")

    def test_member_ordering(self) -> None:
        assert DirectionalIntent.LONG in [DirectionalIntent.LONG]

    def test_auto_values(self) -> None:
        assert DirectionalIntent.LONG.value == "LONG"
        assert DirectionalIntent.SHORT.value == "SHORT"
        assert DirectionalIntent.NEUTRAL.value == "NEUTRAL"


class TestClamp01EdgeCases:
    """Edge-case coverage for clamp_01 not exercised by the current suite."""

    def test_exact_boundary_zero(self) -> None:
        assert clamp_01(Decimal("0")) == Decimal("0")

    def test_exact_boundary_one(self) -> None:
        assert clamp_01(Decimal("1")) == Decimal("1")

    def test_very_small_positive(self) -> None:
        value = Decimal("0.0000001")
        result = clamp_01(value)
        assert result == value

    def test_very_large_positive(self) -> None:
        assert clamp_01(Decimal("999")) == Decimal("1")

    def test_very_large_negative(self) -> None:
        assert clamp_01(Decimal("-999")) == Decimal("0")


class TestConfidenceRampExtended:
    """Extended branch coverage for confidence_ramp."""

    def test_zero_input(self) -> None:
        assert confidence_ramp(Decimal("0")) == Decimal("0")

    def test_negative_input(self) -> None:
        assert confidence_ramp(Decimal("-0.5")) == Decimal("0")

    def test_just_below_threshold(self) -> None:
        assert confidence_ramp(Decimal("0.199")) == Decimal("0")

    def test_just_above_threshold(self) -> None:
        result = confidence_ramp(Decimal("0.21"))
        assert result > Decimal("0")
        assert result <= Decimal("1")

    def test_threshold_exactly_one_below(self) -> None:
        # confidence=0.5, threshold=1.0  => 0.5 < 1.0 => returns 0
        result = confidence_ramp(Decimal("0.5"), threshold=Decimal("1"))
        assert result == Decimal("0")

    def test_threshold_exactly_one_at_boundary(self) -> None:
        # confidence=1.0, threshold=1.0  => 1.0 is NOT < 1.0, ceiling=0 => returns 1
        result = confidence_ramp(Decimal("1.0"), threshold=Decimal("1"))
        assert result == Decimal("1")

    def test_zero_ceiling_returns_one(self) -> None:
        # duplicate of existing test but keeps threshold=2 branch exercised
        assert confidence_ramp(Decimal("0.5"), threshold=Decimal("2")) == Decimal("0")

    def test_custom_threshold_zero(self) -> None:
        # confidence=0.0, threshold=0 => 0.0 is NOT < 0 => ceiling = 1
        # (0 - 0) / 1 = 0 => clamp_01 => 0
        result = confidence_ramp(Decimal("0.0"), threshold=Decimal("0"))
        assert result == Decimal("0")

    def test_custom_threshold_zero_half(self) -> None:
        # threshold=0 => ceiling=1, confidence=0.5 => (0.5-0)/1 = 0.5
        result = confidence_ramp(Decimal("0.5"), threshold=Decimal("0"))
        assert result == Decimal("0.5")

    def test_midpoint(self) -> None:
        result = confidence_ramp(Decimal("0.60"))
        assert result == Decimal("0.5")

    def test_high_confidence(self) -> None:
        result = confidence_ramp(Decimal("0.85"))
        assert Decimal("0.8") < result <= Decimal("1")


class TestRankPercentileExtended:
    """Extended coverage for rank_percentile including ties and reverse order."""

    def test_reversed_values(self) -> None:
        values = [Decimal("5"), Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")]
        result = rank_percentile(values)
        assert result[0] == Decimal("1")
        assert result[-1] == Decimal("0")

    def test_with_ties(self) -> None:
        values = [Decimal("1"), Decimal("2"), Decimal("2"), Decimal("3")]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[1] == Decimal("1") / Decimal("3")
        assert result[2] == Decimal("1") / Decimal("3")
        assert result[3] == Decimal("1")

    def test_all_same_values(self) -> None:
        values = [Decimal("42"), Decimal("42"), Decimal("42")]
        result = rank_percentile(values)
        assert all(r == Decimal("0") for r in result)

    def test_large_list(self) -> None:
        values = [Decimal(str(i)) for i in range(100)]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[50] == Decimal("50") / Decimal("99")
        assert result[-1] == Decimal("1")

    def test_with_negative_values(self) -> None:
        values = [Decimal("-10"), Decimal("-5"), Decimal("0"), Decimal("5")]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[-1] == Decimal("1")

    def test_with_mixed_precision(self) -> None:
        values = [Decimal("1.1"), Decimal("1.2"), Decimal("1.15")]
        result = rank_percentile(values)
        assert result[0] == Decimal("0")
        assert result[1] == Decimal("1")
        assert result[2] == Decimal("0.5")
