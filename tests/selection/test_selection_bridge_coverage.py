"""
Comprehensive coverage tests for selection_bridge.py.

Tests bridge pattern, delegation, StrategyContext building, and error paths.
"""

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


class TestBuildStrategyContexts:
    """Test build_strategy_contexts function."""

    def test_build_contexts_empty_selection(self) -> None:
        """Test with empty selection."""
        selection = SelectionResult(selected=[], filtered_count=0, total_candidates=0)
        strength_by_symbol = {}

        result = build_strategy_contexts(selection, strength_by_symbol)
        assert result == []

    def test_build_contexts_single_instrument(self) -> None:
        """Test with single instrument."""
        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.8"),
                    rank=1,
                    metadata={},
                )
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_by_symbol = {
            "RELIANCE": StrengthInputs(
                breadth_ratio=Decimal("1.5"),
                regime=MarketRegime.BULL,
                adx=Decimal("25"),
                volume_ratio=Decimal("1.5"),
                volatility_atr_pct=Decimal("0.02"),
            )
        }

        result = build_strategy_contexts(selection, strength_by_symbol)
        assert len(result) == 1
        assert result[0].symbol == "RELIANCE"
        assert result[0].exchange == Exchange.NSE
        assert result[0].side == OrderSide.BUY
        assert result[0].composite_score == Decimal("0.8")
        assert result[0].selection_rank == 1

    def test_build_contexts_multiple_instruments(self) -> None:
        """Test with multiple instruments."""
        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.8"),
                    rank=1,
                    metadata={},
                ),
                RankedInstrument(
                    symbol="TCS",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.7"),
                    rank=2,
                    metadata={},
                ),
            ],
            filtered_count=0,
            total_candidates=2,
        )
        strength_by_symbol = {
            "RELIANCE": StrengthInputs(
                breadth_ratio=Decimal("1.5"),
                regime=MarketRegime.BULL,
                adx=Decimal("25"),
                volume_ratio=Decimal("1.5"),
                volatility_atr_pct=Decimal("0.02"),
            ),
            "TCS": StrengthInputs(
                breadth_ratio=Decimal("1.2"),
                regime=MarketRegime.SIDEWAYS,
                adx=Decimal("30"),
                volume_ratio=Decimal("1.2"),
                volatility_atr_pct=Decimal("0.03"),
            ),
        }

        result = build_strategy_contexts(selection, strength_by_symbol)
        assert len(result) == 2
        assert result[0].symbol == "RELIANCE"
        assert result[1].symbol == "TCS"

    def test_build_contexts_missing_strength_inputs(self) -> None:
        """Test raises ConfigError when strength inputs missing."""
        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.8"),
                    rank=1,
                    metadata={},
                )
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_by_symbol = {}  # Empty

        with pytest.raises(ConfigError) as exc_info:
            build_strategy_contexts(selection, strength_by_symbol)
        assert "no StrengthInputs for selected symbol: RELIANCE" in str(exc_info.value)

    def test_build_contexts_with_sell_side(self) -> None:
        """Test building contexts with SELL side."""
        selection = SelectionResult(
            selected=[
                RankedInstrument(
                    symbol="RELIANCE",
                    exchange=Exchange.NSE,
                    composite_score=Decimal("0.8"),
                    rank=1,
                    metadata={},
                )
            ],
            filtered_count=0,
            total_candidates=1,
        )
        strength_by_symbol = {
            "RELIANCE": StrengthInputs(
                breadth_ratio=Decimal("1.5"),
                regime=MarketRegime.BULL,
                adx=Decimal("25"),
                volume_ratio=Decimal("1.5"),
                volatility_atr_pct=Decimal("0.02"),
            )
        }

        result = build_strategy_contexts(
            selection, strength_by_symbol, side=OrderSide.SELL
        )
        assert result[0].side == OrderSide.SELL


class TestExtractStrengthMap:
    """Test extract_strength_map function."""

    def test_extract_from_empty_list(self) -> None:
        """Test with empty list."""
        result = extract_strength_map([])
        assert result == {}

    def test_extract_success(self) -> None:
        """Test successful extraction."""

        # Mock InstrumentSignals objects
        class MockSignals:
            def __init__(self, symbol: str, strength_inputs: StrengthInputs) -> None:
                self.symbol = symbol
                self.strength_inputs = strength_inputs

        signals_list = [
            MockSignals(
                "RELIANCE",
                StrengthInputs(
                    breadth_ratio=Decimal("1.5"),
                    regime=MarketRegime.BULL,
                    adx=Decimal("25"),
                    volume_ratio=Decimal("1.5"),
                    volatility_atr_pct=Decimal("0.02"),
                ),
            ),
            MockSignals(
                "TCS",
                StrengthInputs(
                    breadth_ratio=Decimal("1.2"),
                    regime=MarketRegime.SIDEWAYS,
                    adx=Decimal("30"),
                    volume_ratio=Decimal("1.2"),
                    volatility_atr_pct=Decimal("0.03"),
                ),
            ),
        ]

        result = extract_strength_map(signals_list)
        assert len(result) == 2
        assert "RELIANCE" in result
        assert "TCS" in result
        assert result["RELIANCE"].breadth_ratio == Decimal("1.5")

    def test_extract_missing_symbol(self) -> None:
        """Test raises ConfigError when symbol missing."""

        class MockSignals:
            def __init__(self) -> None:
                self.strength_inputs = StrengthInputs(
                    breadth_ratio=Decimal("1.5"),
                    regime=MarketRegime.BULL,
                    adx=Decimal("25"),
                    volume_ratio=Decimal("1.5"),
                    volatility_atr_pct=Decimal("0.02"),
                )

        signals_list = [MockSignals()]

        with pytest.raises(ConfigError) as exc_info:
            extract_strength_map(signals_list)
        assert "signal missing symbol attribute" in str(exc_info.value)

    def test_extract_missing_strength_inputs(self) -> None:
        """Test raises ConfigError when strength_inputs missing."""

        class MockSignals:
            def __init__(self, symbol: str) -> None:
                self.symbol = symbol

        signals_list = [MockSignals("RELIANCE")]

        with pytest.raises(ConfigError) as exc_info:
            extract_strength_map(signals_list)
        assert "no strength_inputs on InstrumentSignals for RELIANCE" in str(
            exc_info.value
        )

    def test_extract_invalid_symbol_type(self) -> None:
        """Test raises ConfigError when symbol is not a string."""

        class MockSignals:
            def __init__(self) -> None:
                self.symbol = 123  # Invalid type
                self.strength_inputs = StrengthInputs(
                    breadth_ratio=Decimal("1.5"),
                    regime=MarketRegime.BULL,
                    adx=Decimal("25"),
                    volume_ratio=Decimal("1.5"),
                    volatility_atr_pct=Decimal("0.02"),
                )

        signals_list = [MockSignals()]

        with pytest.raises(ConfigError) as exc_info:
            extract_strength_map(signals_list)
        assert "signal missing symbol attribute" in str(exc_info.value)


class TestScaleQuantityByRank:
    """Test scale_quantity_by_rank function."""

    def test_scale_rank_1(self) -> None:
        """Test scaling for rank 1 (full quantity)."""
        result = scale_quantity_by_rank(Decimal("100"), 1, 5)
        assert result == Decimal("100")

    def test_scale_rank_middle(self) -> None:
        """Test scaling for middle rank."""
        result = scale_quantity_by_rank(Decimal("100"), 3, 5)
        assert result == Decimal("60")  # 100 * (5-3+1)/5 = 100 * 3/5

    def test_scale_rank_last(self) -> None:
        """Test scaling for last rank (minimum quantity)."""
        result = scale_quantity_by_rank(Decimal("100"), 5, 5)
        assert result == Decimal("20")  # 100 * (5-5+1)/5 = 100 * 1/5

    def test_scale_invalid_total_selected_zero(self) -> None:
        """Test raises ConfigError when total_selected is zero."""
        with pytest.raises(ConfigError) as exc_info:
            scale_quantity_by_rank(Decimal("100"), 1, 0)
        assert "total_selected must be positive" in str(exc_info.value)

    def test_scale_invalid_rank_zero(self) -> None:
        """Test raises ConfigError when rank is zero."""
        with pytest.raises(ConfigError) as exc_info:
            scale_quantity_by_rank(Decimal("100"), 0, 5)
        assert "rank 0 out of range [1, 5]" in str(exc_info.value)

    def test_scale_invalid_rank_above_total(self) -> None:
        """Test raises ConfigError when rank exceeds total."""
        with pytest.raises(ConfigError) as exc_info:
            scale_quantity_by_rank(Decimal("100"), 6, 5)
        assert "rank 6 out of range [1, 5]" in str(exc_info.value)

    def test_scale_negative_base_quantity(self) -> None:
        """Test raises ConfigError when base_quantity is negative."""
        with pytest.raises(ConfigError) as exc_info:
            scale_quantity_by_rank(Decimal("-100"), 1, 5)
        assert "base_quantity must be positive" in str(exc_info.value)

    def test_scale_zero_base_quantity(self) -> None:
        """Test raises ConfigError when base_quantity is zero."""
        with pytest.raises(ConfigError) as exc_info:
            scale_quantity_by_rank(Decimal("0"), 1, 5)
        assert "base_quantity must be positive" in str(exc_info.value)

    def test_scale_precision(self) -> None:
        """Test Decimal precision in scaling."""
        result = scale_quantity_by_rank(Decimal("100.123"), 2, 3)
        # 100.123 * (3-2+1)/3 = 100.123 * 2/3 ≈ 66.748666...
        assert result > Decimal("66")
        assert result < Decimal("67")
