"""
Comprehensive coverage tests for selector_validator.py.

Tests pre-selection validation, input validation, and error paths.
"""

from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.selection.selector_validator import (
    validate_instrument_list,
    validate_ranking_inputs,
    validate_selection_config,
)


class TestValidateInstrumentList:
    """Test validate_instrument_list function."""

    def test_valid_instrument_list(self) -> None:
        """Test with valid instrument list."""
        instruments = [
            {"symbol": "RELIANCE", "exchange": Exchange.NSE},
            {"symbol": "TCS", "exchange": Exchange.NSE},
        ]
        result = validate_instrument_list(instruments)
        assert result is True

    def test_empty_instrument_list(self) -> None:
        """Test with empty instrument list."""
        instruments: list[dict] = []
        result = validate_instrument_list(instruments)
        assert result is True  # Empty is valid

    def test_duplicate_symbols(self) -> None:
        """Test with duplicate symbols."""
        instruments = [
            {"symbol": "RELIANCE", "exchange": Exchange.NSE},
            {"symbol": "RELIANCE", "exchange": Exchange.NSE},
        ]
        with pytest.raises(ValueError) as exc_info:
            validate_instrument_list(instruments)
        assert "duplicate" in str(exc_info.value).lower()

    def test_missing_symbol(self) -> None:
        """Test with missing symbol field."""
        instruments = [{"exchange": Exchange.NSE}]
        with pytest.raises(ValueError) as exc_info:
            validate_instrument_list(instruments)
        assert "symbol" in str(exc_info.value).lower()

    def test_missing_exchange(self) -> None:
        """Test with missing exchange field."""
        instruments = [{"symbol": "RELIANCE"}]
        with pytest.raises(ValueError) as exc_info:
            validate_instrument_list(instruments)
        assert "exchange" in str(exc_info.value).lower()


class TestValidateRankingInputs:
    """Test validate_ranking_inputs function."""

    def test_valid_inputs(self) -> None:
        """Test with valid ranking inputs."""
        inputs = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.6"),
            "volume_profile": Decimal("0.7"),
            "drl": Decimal("0.8"),
        }
        result = validate_ranking_inputs(inputs)
        assert result is True

    def test_missing_required_score(self) -> None:
        """Test with missing required score."""
        inputs = {
            "sentiment": Decimal("0.5"),
            "strength": Decimal("0.6"),
            # Missing volume_profile and drl
        }
        with pytest.raises(ValueError) as exc_info:
            validate_ranking_inputs(inputs)
        assert "required" in str(exc_info.value).lower()

    def test_invalid_score_range_high(self) -> None:
        """Test with score above 1.0."""
        inputs = {
            "sentiment": Decimal("1.5"),
            "strength": Decimal("0.6"),
            "volume_profile": Decimal("0.7"),
            "drl": Decimal("0.8"),
        }
        with pytest.raises(ValueError) as exc_info:
            validate_ranking_inputs(inputs)
        assert "range" in str(exc_info.value).lower()

    def test_invalid_score_range_negative(self) -> None:
        """Test with negative score."""
        inputs = {
            "sentiment": Decimal("-0.1"),
            "strength": Decimal("0.6"),
            "volume_profile": Decimal("0.7"),
            "drl": Decimal("0.8"),
        }
        with pytest.raises(ValueError) as exc_info:
            validate_ranking_inputs(inputs)
        assert "negative" in str(exc_info.value).lower()

    def test_non_decimal_score(self) -> None:
        """Test with non-Decimal score."""
        inputs = {
            "sentiment": "0.5",  # String instead of Decimal
            "strength": Decimal("0.6"),
            "volume_profile": Decimal("0.7"),
            "drl": Decimal("0.8"),
        }
        with pytest.raises(ValueError) as exc_info:
            validate_ranking_inputs(inputs)
        assert "decimal" in str(exc_info.value).lower()


class TestValidateSelectionConfig:
    """Test validate_selection_config function."""

    def test_valid_config(self) -> None:
        """Test with valid selection config."""
        config = {
            "max_candidates": 10,
            "min_confidence": Decimal("0.5"),
            "regime": "SIDEWAYS",
        }
        result = validate_selection_config(config)
        assert result is True

    def test_invalid_max_candidates_negative(self) -> None:
        """Test with negative max_candidates."""
        config = {
            "max_candidates": -5,
            "min_confidence": Decimal("0.5"),
        }
        with pytest.raises(ValueError) as exc_info:
            validate_selection_config(config)
        assert "positive" in str(exc_info.value).lower()

    def test_invalid_min_confidence(self) -> None:
        """Test with min_confidence above 1.0."""
        config = {
            "max_candidates": 10,
            "min_confidence": Decimal("1.5"),
        }
        with pytest.raises(ValueError) as exc_info:
            validate_selection_config(config)
        assert "range" in str(exc_info.value).lower()

    def test_missing_required_field(self) -> None:
        """Test with missing required field."""
        config = {
            "max_candidates": 10,
            # Missing min_confidence
        }
        with pytest.raises(ValueError) as exc_info:
            validate_selection_config(config)
        assert "required" in str(exc_info.value).lower()
