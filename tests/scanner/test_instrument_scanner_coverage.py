"""Additional tests for instrument_scanner.py to improve coverage to 90%+."""

import random
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.scanner.instrument_scanner import (
    InstrumentCategory,
    InstrumentScanner,
    MarketData,
    _extract_value,
    _iter_dataframe_rows,
    _to_decimal,
    create_mock_rl_predictor,
    create_mock_sentiment_analyzer,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_iter_dataframe_rows_with_dataframe():
    """Test iteration over pandas-like DataFrame."""

    # Mock pandas DataFrame with iterrows method
    class MockFrame:
        def iterrows(self):
            mock_row1 = {"close": 100, "open": 95, "high": 105, "low": 94, "volume": 1000}
            mock_row2 = {"close": 102, "open": 100, "high": 106, "low": 99, "volume": 1200}
            return [(0, mock_row1), (1, mock_row2)]

    mock_frame = MockFrame()
    rows = list(_iter_dataframe_rows(mock_frame))
    assert len(rows) == 2
    assert rows[0]["close"] == 100
    assert rows[1]["close"] == 102


def test_iter_dataframe_rows_with_list():
    """Test iteration over list of dicts."""
    data = [
        {"close": 100, "open": 95, "high": 105, "low": 94, "volume": 1000},
        {"close": 102, "open": 100, "high": 106, "low": 99, "volume": 1200},
    ]
    rows = list(_iter_dataframe_rows(data))
    assert len(rows) == 2
    assert rows[0]["close"] == 100


def test_iter_dataframe_rows_empty_dataframe():
    """Test iteration over empty DataFrame."""

    class MockFrame:
        def iterrows(self):
            return []

    mock_frame = MockFrame()
    rows = list(_iter_dataframe_rows(mock_frame))
    assert len(rows) == 0


def test_iter_dataframe_rows_non_mapping_dataframe_row():
    """Test that non-mapping DataFrame rows raise error."""

    class MockFrame:
        def iterrows(self):
            return [(0, "not_a_mapping")]

    mock_frame = MockFrame()
    with pytest.raises(ConfigError, match="jugaad dataframe rows must be mapping-like"):
        list(_iter_dataframe_rows(mock_frame))


def test_iter_dataframe_rows_non_mapping_list_row():
    """Test that non-mapping list rows raise error."""
    data = ["not_a_mapping", "also_not_a_mapping"]
    with pytest.raises(ConfigError, match="jugaad list rows must be mapping-like"):
        list(_iter_dataframe_rows(data))


def test_iter_dataframe_rows_unsupported_type():
    """Test that unsupported types raise error."""
    with pytest.raises(ConfigError, match="Unsupported jugaad history response type"):
        list(_iter_dataframe_rows(123))


def test_to_decimal_with_none():
    """Test that None raises ConfigError."""
    with pytest.raises(ConfigError, match="cannot be None"):
        _to_decimal(None, "test_field")


def test_to_decimal_with_invalid_string():
    """Test that invalid string raises ConfigError."""
    with pytest.raises(ConfigError, match="not decimal-compatible"):
        _to_decimal("not_a_number", "test_field")


def test_to_decimal_with_nan():
    """Test that NaN raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("nan"), "test_field")


def test_to_decimal_with_inf():
    """Test that infinity raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("inf"), "test_field")


def test_to_decimal_with_negative_inf():
    """Test that negative infinity raises ConfigError."""
    with pytest.raises(ConfigError, match="must be finite"):
        _to_decimal(float("-inf"), "test_field")


def test_to_decimal_with_valid_types():
    """Test conversion of valid types."""
    assert _to_decimal("123.45", "test") == Decimal("123.45")
    assert _to_decimal(100, "test") == Decimal("100")
    assert _to_decimal(50.75, "test") == Decimal("50.75")
    assert _to_decimal(Decimal("99.99"), "test") == Decimal("99.99")


def test_extract_value_all_keys_none():
    """Test that all None keys raise error."""
    payload = {"close": None, "CLOSE": None}
    with pytest.raises(ConfigError, match="Missing required OHLCV key"):
        _extract_value(payload, ("close", "CLOSE"))


def test_extract_value_all_keys_missing():
    """Test that missing keys raise error."""
    payload = {"open": 100, "high": 105}
    with pytest.raises(ConfigError, match="Missing required OHLCV key"):
        _extract_value(payload, ("close", "CLOSE"))


def test_scanner_apply_filters_all_filtered():
    """Test that all candidates can be filtered out."""
    scanner = InstrumentScanner(
        sentiment_analyzer=create_mock_sentiment_analyzer({"TEST": (Decimal("0.5"), False)}),
        rl_predictor=create_mock_rl_predictor(Decimal("0.3")),
    )

    custom_data = [
        MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("1000"),  # Low volume ratio
            avg_volume=Decimal("500000"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("105"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        )
    ]

    result = scanner.scan(custom_data=custom_data)
    # All filtered out: not very strong, low volume, low exit probability
    assert len(result.gainers) == 0
    assert len(result.losers) == 0
    assert result.filtered_count == 1


def test_scanner_rank_and_split_empty_list():
    """Test ranking with empty list."""
    scanner = InstrumentScanner()
    gainers, losers = scanner._rank_and_split([])
    assert gainers == []
    assert losers == []


def test_scanner_to_scanner_candidates_empty_list():
    """Test converting empty candidates list."""
    scanner = InstrumentScanner()
    candidates = scanner._to_scanner_candidates([])
    assert candidates == []


def test_scanner_get_sentiment_without_analyzer():
    """Test sentiment without analyzer returns defaults."""
    scanner = InstrumentScanner(sentiment_analyzer=None)

    data = MarketData(
        symbol="TEST",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("100"),
        prev_close_price=Decimal("95"),
        volume=Decimal("1000"),
        avg_volume=Decimal("500"),
        timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        high_price=Decimal("105"),
        low_price=Decimal("98"),
        adx=Decimal("25"),
        atr_pct=Decimal("0.01"),
        breadth_ratio=Decimal("1.2"),
    )

    score, is_very_strong = scanner._get_sentiment(data)
    assert score == Decimal("0")
    assert is_very_strong is False


def test_scanner_get_exit_probability_without_predictor():
    """Test exit probability without predictor returns zero."""
    scanner = InstrumentScanner(rl_predictor=None)

    data = MarketData(
        symbol="TEST",
        exchange=Exchange.NSE,
        category=InstrumentCategory.STOCK,
        close_price=Decimal("100"),
        prev_close_price=Decimal("95"),
        volume=Decimal("1000"),
        avg_volume=Decimal("500"),
        timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
        high_price=Decimal("105"),
        low_price=Decimal("98"),
        adx=Decimal("25"),
        atr_pct=Decimal("0.01"),
        breadth_ratio=Decimal("1.2"),
    )

    prob = scanner._get_exit_probability(data)
    assert prob == Decimal("0")


def test_scanner_compute_composite_score_clamping():
    """Test that composite score is clamped between 0 and 1."""
    scanner = InstrumentScanner()

    # Create a candidate with very high values
    from iatb.scanner.instrument_scanner import _CandidateScores

    candidate = _CandidateScores(
        market_data=MarketData(
            symbol="TEST",
            exchange=Exchange.NSE,
            category=InstrumentCategory.STOCK,
            close_price=Decimal("100"),
            prev_close_price=Decimal("95"),
            volume=Decimal("1000000"),  # High volume
            avg_volume=Decimal("100"),
            timestamp_utc=datetime(2024, 1, 1, 10, 0, tzinfo=UTC),
            high_price=Decimal("105"),
            low_price=Decimal("98"),
            adx=Decimal("25"),
            atr_pct=Decimal("0.01"),
            breadth_ratio=Decimal("1.2"),
        ),
        sentiment_score=Decimal("1.5"),  # Above 1
        is_very_strong=True,
        strength_score=Decimal("2.0"),  # Above 1
        is_strength_tradable=True,
        exit_probability=Decimal("1.5"),  # Above 1
    )

    composite = scanner._compute_composite_score(candidate)
    # Should be clamped to max 1.0
    assert composite <= Decimal("1")
    assert composite >= Decimal("0")


def test_scanner_determine_category_edge_cases():
    """Test category detection for edge cases."""
    assert InstrumentScanner._determine_category("FUT") == InstrumentCategory.FUTURE
    assert InstrumentScanner._determine_category("FUTURE") == InstrumentCategory.FUTURE
    assert InstrumentScanner._determine_category("NIFTYCE") == InstrumentCategory.OPTION
    assert InstrumentScanner._determine_category("NIFTYPE") == InstrumentCategory.OPTION
    # Long symbol name (>10 chars) should be OPTION
    assert InstrumentScanner._determine_category("VERYLONGOPTION") == InstrumentCategory.OPTION
