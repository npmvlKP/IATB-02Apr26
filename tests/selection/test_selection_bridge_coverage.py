"""Tests for selection/selection_bridge.py — bridge pattern and delegation."""

from decimal import Decimal

import pytest
from iatb.core.enums import Exchange, OrderSide
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs
from iatb.selection.ranking import RankedInstrument, SelectionResult
from iatb.selection.selection_bridge import (
    build_strategy_contexts,
    extract_strength_map,
    scale_quantity_by_rank,
)
from iatb.strategies.base import StrategyContext


def _strength_inputs() -> StrengthInputs:
    return StrengthInputs(
        breadth_ratio=Decimal("1.0"),
        regime=MarketRegime.SIDEWAYS,
        adx=Decimal("20"),
        volume_ratio=Decimal("1.0"),
        volatility_atr_pct=Decimal("0.03"),
    )


def _ranked_instrument(symbol: str, rank: int, score: Decimal) -> RankedInstrument:
    return RankedInstrument(
        symbol=symbol,
        exchange=Exchange.NSE,
        composite_score=score,
        rank=rank,
        metadata={},
    )


class TestBuildStrategyContexts:
    def test_empty_selection_returns_empty(self) -> None:
        selection = SelectionResult(selected=[], filtered_count=0, total_candidates=0)
        result = build_strategy_contexts(selection, {})
        assert result == []

    def test_builds_contexts_from_ranked_instruments(self) -> None:
        ranked = _ranked_instrument("RELIANCE", 1, Decimal("0.85"))
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        strength_map = {"RELIANCE": _strength_inputs()}
        contexts = build_strategy_contexts(selection, strength_map)
        assert len(contexts) == 1
        ctx = contexts[0]
        assert isinstance(ctx, StrategyContext)
        assert ctx.symbol == "RELIANCE"
        assert ctx.exchange == Exchange.NSE
        assert ctx.side == OrderSide.BUY
        assert ctx.selection_rank == 1

    def test_builds_with_sell_side(self) -> None:
        ranked = _ranked_instrument("TCS", 2, Decimal("0.75"))
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        strength_map = {"TCS": _strength_inputs()}
        contexts = build_strategy_contexts(selection, strength_map, side=OrderSide.SELL)
        assert contexts[0].side == OrderSide.SELL

    def test_multiple_instruments(self) -> None:
        r1 = _ranked_instrument("A", 1, Decimal("0.9"))
        r2 = _ranked_instrument("B", 2, Decimal("0.8"))
        selection = SelectionResult(
            selected=[r1, r2], filtered_count=0, total_candidates=2
        )
        sm = {"A": _strength_inputs(), "B": _strength_inputs()}
        contexts = build_strategy_contexts(selection, sm)
        assert len(contexts) == 2
        assert contexts[0].selection_rank == 1
        assert contexts[1].selection_rank == 2

    def test_missing_strength_inputs_raises(self) -> None:
        ranked = _ranked_instrument("MISSING", 1, Decimal("0.8"))
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        with pytest.raises(ConfigError, match="no StrengthInputs"):
            build_strategy_contexts(selection, {})


class TestExtractStrengthMap:
    def test_valid_signals(self) -> None:
        sig = type(
            "InstrumentSignals",
            (),
            {
                "symbol": "RELIANCE",
                "strength_inputs": _strength_inputs(),
            },
        )()
        result = extract_strength_map([sig])
        assert "RELIANCE" in result
        assert isinstance(result["RELIANCE"], StrengthInputs)

    def test_missing_symbol_raises(self) -> None:
        sig = type("BadSignal", (), {"strength_inputs": _strength_inputs()})()
        with pytest.raises(ConfigError, match="missing symbol"):
            extract_strength_map([sig])

    def test_missing_strength_inputs_raises(self) -> None:
        sig = type("BadSignal", (), {"symbol": "X"})()
        with pytest.raises(ConfigError, match="no strength_inputs"):
            extract_strength_map([sig])

    def test_empty_list_returns_empty(self) -> None:
        assert extract_strength_map([]) == {}

    def test_non_string_symbol_raises(self) -> None:
        sig = type(
            "BadSignal", (), {"symbol": 123, "strength_inputs": _strength_inputs()}
        )()
        with pytest.raises(ConfigError, match="missing symbol"):
            extract_strength_map([sig])

    def test_non_strength_inputs_raises(self) -> None:
        sig = type("BadSignal", (), {"symbol": "A", "strength_inputs": "not_valid"})()
        with pytest.raises(ConfigError, match="no strength_inputs"):
            extract_strength_map([sig])


class TestScaleQuantityByRank:
    def test_rank1_gets_full_quantity(self) -> None:
        result = scale_quantity_by_rank(Decimal("100"), 1, 3)
        assert result == Decimal("100")

    def test_rank2_gets_proportional(self) -> None:
        result = scale_quantity_by_rank(Decimal("100"), 2, 3)
        expected = Decimal("100") * Decimal(2) / Decimal(3)
        assert result == expected

    def test_last_rank_gets_minimum(self) -> None:
        result = scale_quantity_by_rank(Decimal("90"), 3, 3)
        expected = Decimal("90") * Decimal(1) / Decimal(3)
        assert result == expected

    def test_zero_total_raises(self) -> None:
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, 0)

    def test_negative_total_raises(self) -> None:
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, -1)

    def test_rank_out_of_range_raises(self) -> None:
        with pytest.raises(ConfigError, match="out of range"):
            scale_quantity_by_rank(Decimal("100"), 5, 3)

    def test_rank_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="out of range"):
            scale_quantity_by_rank(Decimal("100"), 0, 3)

    def test_negative_base_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("-10"), 1, 3)

    def test_zero_base_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("0"), 1, 3)

    def test_single_instrument(self) -> None:
        result = scale_quantity_by_rank(Decimal("50"), 1, 1)
        assert result == Decimal("50")
