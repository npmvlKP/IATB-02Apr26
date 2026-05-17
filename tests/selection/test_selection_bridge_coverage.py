"""
Comprehensive coverage tests for selection_bridge.py.

Tests bridge pattern, delegation, and strategy context building.
"""

from decimal import Decimal

import pytest
from iatb.core.enums import OrderSide
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
    """Test strategy context building from selection results."""

    def test_empty_selection_returns_empty_list(self):
        """Test that empty selection returns empty contexts."""
        selection = SelectionResult(selected=[], filtered_count=0, total_candidates=0)
        strength_map = {}
        contexts = build_strategy_contexts(selection, strength_map)
        assert contexts == []

    def test_single_instrument_context(self, sample_strength_inputs):
        """Test building context for single instrument."""
        ranked = RankedInstrument(
            symbol="RELIANCE",
            exchange="NSE",
            composite_score=Decimal("0.75"),
            rank=1,
            metadata={"test": "data"},
        )
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        strength_map = {"RELIANCE": sample_strength_inputs}

        contexts = build_strategy_contexts(selection, strength_map, OrderSide.BUY)

        assert len(contexts) == 1
        ctx = contexts[0]
        assert ctx.exchange == "NSE"
        assert ctx.symbol == "RELIANCE"
        assert ctx.side == OrderSide.BUY
        assert ctx.composite_score == Decimal("0.75")
        assert ctx.selection_rank == 1

    def test_multiple_instruments_contexts(self, sample_strength_inputs):
        """Test building contexts for multiple instruments."""
        ranked_list = [
            RankedInstrument(
                symbol="RELIANCE",
                exchange="NSE",
                composite_score=Decimal("0.85"),
                rank=1,
                metadata={"test": "data"},
            ),
            RankedInstrument(
                symbol="TCS",
                exchange="NSE",
                composite_score=Decimal("0.75"),
                rank=2,
                metadata={"test": "data"},
            ),
            RankedInstrument(
                symbol="INFY",
                exchange="NSE",
                composite_score=Decimal("0.65"),
                rank=3,
                metadata={"test": "data"},
            ),
        ]
        selection = SelectionResult(
            selected=ranked_list, filtered_count=0, total_candidates=3
        )
        strength_map = {
            "RELIANCE": sample_strength_inputs,
            "TCS": sample_strength_inputs,
            "INFY": sample_strength_inputs,
        }

        contexts = build_strategy_contexts(selection, strength_map)

        assert len(contexts) == 3
        assert contexts[0].symbol == "RELIANCE"
        assert contexts[1].symbol == "TCS"
        assert contexts[2].symbol == "INFY"

    def test_missing_strength_raises_config_error(self, sample_strength_inputs):
        """Test that missing strength inputs raises ConfigError."""
        ranked = RankedInstrument(
            symbol="RELIANCE",
            exchange="NSE",
            composite_score=Decimal("0.75"),
            rank=1,
            metadata={"test": "data"},
        )
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        strength_map = {}  # Missing RELIANCE

        with pytest.raises(ConfigError, match="no StrengthInputs for selected symbol"):
            build_strategy_contexts(selection, strength_map)

    def test_sell_side_context(self, sample_strength_inputs):
        """Test building sell-side contexts."""
        ranked = RankedInstrument(
            symbol="RELIANCE",
            exchange="NSE",
            composite_score=Decimal("0.75"),
            rank=1,
            metadata={"test": "data"},
        )
        selection = SelectionResult(
            selected=[ranked], filtered_count=0, total_candidates=1
        )
        strength_map = {"RELIANCE": sample_strength_inputs}

        contexts = build_strategy_contexts(selection, strength_map, OrderSide.SELL)

        assert contexts[0].side == OrderSide.SELL


class TestExtractStrengthMap:
    """Test strength map extraction from signal objects."""

    def test_extract_from_empty_list(self):
        """Test extracting from empty list."""
        result = extract_strength_map([])
        assert result == {}

    def test_extract_valid_signals(self, sample_strength_inputs):
        """Test extracting from valid signals."""

        # Create mock signal objects
        class MockSignal:
            def __init__(self, symbol, strength):
                self.symbol = symbol
                self.strength_inputs = strength

        signals = [
            MockSignal("RELIANCE", sample_strength_inputs),
            MockSignal("TCS", sample_strength_inputs),
        ]

        result = extract_strength_map(signals)

        assert len(result) == 2
        assert "RELIANCE" in result
        assert "TCS" in result
        assert result["RELIANCE"] == sample_strength_inputs

    def test_missing_symbol_raises_config_error(self, sample_strength_inputs):
        """Test that missing symbol attribute raises ConfigError."""

        class MockSignal:
            def __init__(self, strength):
                self.strength_inputs = strength
                # No symbol attribute

        signals = [MockSignal(sample_strength_inputs)]

        with pytest.raises(ConfigError, match="signal missing symbol attribute"):
            extract_strength_map(signals)

    def test_missing_strength_raises_config_error(self):
        """Test that missing strength_inputs raises ConfigError."""

        class MockSignal:
            def __init__(self, symbol):
                self.symbol = symbol
                # No strength_inputs attribute

        signals = [MockSignal("RELIANCE")]

        with pytest.raises(
            ConfigError, match="no strength_inputs on InstrumentSignals"
        ):
            extract_strength_map(signals)

    def test_invalid_symbol_type_raises_config_error(self, sample_strength_inputs):
        """Test that non-string symbol raises ConfigError."""

        class MockSignal:
            def __init__(self, symbol, strength):
                self.symbol = symbol
                self.strength_inputs = strength

        signals = [MockSignal(123, sample_strength_inputs)]  # Invalid type

        with pytest.raises(ConfigError, match="signal missing symbol attribute"):
            extract_strength_map(signals)

    def test_invalid_strength_type_raises_config_error(self):
        """Test that non-StrengthInputs raises ConfigError."""

        class MockSignal:
            def __init__(self, symbol):
                self.symbol = symbol
                self.strength_inputs = "invalid"  # Invalid type

        signals = [MockSignal("RELIANCE")]

        with pytest.raises(
            ConfigError, match="no strength_inputs on InstrumentSignals"
        ):
            extract_strength_map(signals)


class TestScaleQuantityByRank:
    """Test quantity scaling based on rank."""

    def test_rank_1_gets_full_quantity(self):
        """Test that rank 1 gets full base quantity."""
        base = Decimal("100")
        rank = 1
        total = 5
        result = scale_quantity_by_rank(base, rank, total)
        assert result == Decimal("100")

    def test_rank_2_gets_reduced_quantity(self):
        """Test that rank 2 gets reduced quantity."""
        base = Decimal("100")
        rank = 2
        total = 5
        result = scale_quantity_by_rank(base, rank, total)
        # Weight = (5 - 2 + 1) / 5 = 4/5 = 0.8
        assert result == Decimal("80")

    def test_last_rank_gets_minimum_quantity(self):
        """Test that last rank gets minimum quantity."""
        base = Decimal("100")
        rank = 5
        total = 5
        result = scale_quantity_by_rank(base, rank, total)
        # Weight = (5 - 5 + 1) / 5 = 1/5 = 0.2
        assert result == Decimal("20")

    def test_zero_total_raises_config_error(self):
        """Test that zero total_selected raises ConfigError."""
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, 0)

    def test_negative_total_raises_config_error(self):
        """Test that negative total_selected raises ConfigError."""
        with pytest.raises(ConfigError, match="total_selected must be positive"):
            scale_quantity_by_rank(Decimal("100"), 1, -1)

    def test_rank_below_range_raises_config_error(self):
        """Test that rank < 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="rank 0 out of range"):
            scale_quantity_by_rank(Decimal("100"), 0, 5)

    def test_rank_above_range_raises_config_error(self):
        """Test that rank > total raises ConfigError."""
        with pytest.raises(ConfigError, match="rank 6 out of range"):
            scale_quantity_by_rank(Decimal("100"), 6, 5)

    def test_negative_base_quantity_raises_config_error(self):
        """Test that negative base_quantity raises ConfigError."""
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("-100"), 1, 5)

    def test_zero_base_quantity_raises_config_error(self):
        """Test that zero base_quantity raises ConfigError."""
        with pytest.raises(ConfigError, match="base_quantity must be positive"):
            scale_quantity_by_rank(Decimal("0"), 1, 5)

    def test_single_item_selection(self):
        """Test scaling with single item selection."""
        base = Decimal("100")
        rank = 1
        total = 1
        result = scale_quantity_by_rank(base, rank, total)
        assert result == Decimal("100")


@pytest.fixture
def sample_strength_inputs():
    """Provide sample StrengthInputs for testing."""
    return StrengthInputs(
        breadth_ratio=Decimal("1.0"),
        regime=MarketRegime.SIDEWAYS,
        adx=Decimal("20"),
        volume_ratio=Decimal("1.0"),
        volatility_atr_pct=Decimal("0.03"),
    )
