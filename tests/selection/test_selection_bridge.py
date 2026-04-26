"""Tests for selection.selection_bridge module."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection.ranking import RankedInstrument, SelectionResult
from iatb.selection.selection_bridge import (
    _resolve_strength,
    build_strategy_contexts,
    extract_strength_map,
    scale_quantity_by_rank,
)


def _make_strength_inputs() -> StrengthInputs:
    return StrengthInputs(
        breadth_ratio=Decimal("1.0"),
        regime=MarketRegime.SIDEWAYS,
        adx=Decimal("20"),
        volume_ratio=Decimal("1.0"),
        volatility_atr_pct=Decimal("0.03"),
    )


class TestBuildStrategyContexts:
    def test_empty_selection(self) -> None:
        result = build_strategy_contexts(
            SelectionResult(selected=[], filtered_count=0, total_candidates=0),
            {},
        )
        assert result == []

    def test_missing_strength_raises(self) -> None:
        selection = SelectionResult(
            selected=[
                RankedInstrument("TEST", Exchange.NSE, Decimal("0.8"), 1, {}),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        with pytest.raises(ConfigError, match="no StrengthInputs"):
            build_strategy_contexts(selection, {})

    def test_valid_single(self) -> None:
        selection = SelectionResult(
            selected=[
                RankedInstrument("TEST", Exchange.NSE, Decimal("0.8"), 1, {}),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_map = {"TEST": _make_strength_inputs()}
        result = build_strategy_contexts(selection, strength_map)
        assert len(result) == 1
        assert result[0].symbol == "TEST"
        assert result[0].exchange == Exchange.NSE
        assert result[0].side == OrderSide.BUY

    def test_sell_side(self) -> None:
        selection = SelectionResult(
            selected=[
                RankedInstrument("TEST", Exchange.NSE, Decimal("0.8"), 1, {}),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_map = {"TEST": _make_strength_inputs()}
        result = build_strategy_contexts(selection, strength_map, side=OrderSide.SELL)
        assert result[0].side == OrderSide.SELL

    def test_multiple_instruments(self) -> None:
        selection = SelectionResult(
            selected=[
                RankedInstrument("A", Exchange.NSE, Decimal("0.9"), 1, {}),
                RankedInstrument("B", Exchange.BSE, Decimal("0.7"), 2, {}),
            ],
            filtered_count=0,
            total_candidates=2,
        )
        strength_map = {
            "A": _make_strength_inputs(),
            "B": _make_strength_inputs(),
        }
        result = build_strategy_contexts(selection, strength_map)
        assert len(result) == 2
        assert result[0].selection_rank == 1
        assert result[1].selection_rank == 2

    def test_composite_score_preserved(self) -> None:
        selection = SelectionResult(
            selected=[
                RankedInstrument("TEST", Exchange.NSE, Decimal("0.85"), 1, {}),
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_map = {"TEST": _make_strength_inputs()}
        result = build_strategy_contexts(selection, strength_map)
        assert result[0].composite_score == Decimal("0.85")


class TestResolveStrength:
    def test_found(self) -> None:
        ranked = RankedInstrument("TEST", Exchange.NSE, Decimal("0.8"), 1, {})
        result = _resolve_strength(ranked, {"TEST": _make_strength_inputs()})
        assert result is not None

    def test_not_found_raises(self) -> None:
        ranked = RankedInstrument("MISSING", Exchange.NSE, Decimal("0.8"), 1, {})
        with pytest.raises(ConfigError, match="no StrengthInputs"):
            _resolve_strength(ranked, {})


class TestScaleQuantityByRank:
    def test_rank_1_full(self) -> None:
        result = scale_quantity_by_rank(Decimal("100"), 1, 3)
        assert result == Decimal("100")

    def test_lower_rank(self) -> None:
        result = scale_quantity_by_rank(Decimal("100"), 3, 3)
        assert result < Decimal("100")
        assert result == Decimal("100") / Decimal("3")

    def test_rank_2_of_3(self) -> None:
        result = scale_quantity_by_rank(Decimal("100"), 2, 3)
        assert result == Decimal("200") / Decimal("3")

    def test_zero_total_raises(self) -> None:
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, 0)

    def test_negative_total_raises(self) -> None:
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, -1)

    def test_rank_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="rank .+ out of range"):
            scale_quantity_by_rank(Decimal("100"), 0, 3)

    def test_rank_exceeds_total_raises(self) -> None:
        with pytest.raises(ConfigError, match="rank .+ out of range"):
            scale_quantity_by_rank(Decimal("100"), 4, 3)

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("-10"), 1, 3)

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("0"), 1, 3)

    def test_single_item(self) -> None:
        result = scale_quantity_by_rank(Decimal("50"), 1, 1)
        assert result == Decimal("50")


class TestExtractStrengthMap:
    def test_missing_symbol_raises(self) -> None:
        class FakeSignal:
            pass

        with pytest.raises(ConfigError, match="missing symbol"):
            extract_strength_map([FakeSignal()])

    def test_non_string_symbol_raises(self) -> None:
        class FakeSignal:
            symbol = 123

        with pytest.raises(ConfigError, match="missing symbol"):
            extract_strength_map([FakeSignal()])

    def test_missing_inputs_raises(self) -> None:
        class FakeSignal:
            symbol = "TEST"

        with pytest.raises(ConfigError, match="no strength_inputs"):
            extract_strength_map([FakeSignal()])

    def test_wrong_type_inputs_raises(self) -> None:
        class FakeSignal:
            symbol = "TEST"
            strength_inputs = "not a StrengthInputs"

        with pytest.raises(ConfigError, match="no strength_inputs"):
            extract_strength_map([FakeSignal()])

    def test_valid_signal(self) -> None:
        @dataclass
        class FakeSignal:
            symbol: str
            strength_inputs: StrengthInputs

        si = _make_strength_inputs()
        result = extract_strength_map([FakeSignal("TEST", si)])
        assert result["TEST"] is si

    def test_multiple_signals(self) -> None:
        @dataclass
        class FakeSignal:
            symbol: str
            strength_inputs: StrengthInputs

        si1 = _make_strength_inputs()
        si2 = _make_strength_inputs()
        result = extract_strength_map([FakeSignal("A", si1), FakeSignal("B", si2)])
        assert len(result) == 2
        assert "A" in result
        assert "B" in result
