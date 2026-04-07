"""Tests for strength_signal.py module."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.enums import Exchange
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.strength_scorer import StrengthInputs, StrengthScorer
from iatb.selection.strength_signal import (
    StrengthSignalInput,
    StrengthSignalOutput,
    _validate_input,
    compute_strength_signal,
)

_NOW = datetime(2026, 4, 5, 10, 0, 0, tzinfo=UTC)


def _make_strength_inputs(
    regime: MarketRegime = MarketRegime.BULL,
    adx: Decimal = Decimal("30"),
    breadth_ratio: Decimal = Decimal("1.5"),
    volume_ratio: Decimal = Decimal("1.5"),
    volatility_atr_pct: Decimal = Decimal("0.02"),
) -> StrengthInputs:
    """Helper to create StrengthInputs."""
    return StrengthInputs(
        breadth_ratio=breadth_ratio,
        regime=regime,
        adx=adx,
        volume_ratio=volume_ratio,
        volatility_atr_pct=volatility_atr_pct,
    )


def test_compute_strength_signal_basic() -> None:
    """Test compute_strength_signal with valid inputs."""
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    assert isinstance(result, StrengthSignalOutput)
    assert Decimal("0") <= result.score <= Decimal("1")
    assert Decimal("0") <= result.confidence <= Decimal("1")
    assert result.regime == MarketRegime.BULL
    assert isinstance(result.tradable, bool)
    assert "raw_score" in result.metadata


def test_compute_strength_signal_with_decay() -> None:
    """Test compute_strength_signal applies temporal decay."""
    from datetime import timedelta

    old_timestamp = _NOW - timedelta(hours=2)
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=old_timestamp,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    # Decay should reduce score slightly
    assert result.score < Decimal("1")
    assert result.confidence < Decimal("1")


def test_compute_strength_signal_tradable() -> None:
    """Test compute_strength_signal sets tradable correctly."""
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(adx=Decimal("40")),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    # High ADX should be tradable
    assert result.tradable is True


def test_compute_strength_signal_non_tradable() -> None:
    """Test compute_strength_signal works with weak signals."""
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(
            adx=Decimal("10"),  # Low ADX
            breadth_ratio=Decimal("0.8"),  # Low breadth
        ),
        regime_confidence=Decimal("0.5"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    # Should still produce a valid result
    assert isinstance(result, StrengthSignalOutput)
    assert isinstance(result.tradable, bool)


def test_compute_strength_signal_metadata() -> None:
    """Test compute_strength_signal includes all metadata fields."""
    scorer = StrengthScorer()
    strength = _make_strength_inputs(
        adx=Decimal("35"),
        breadth_ratio=Decimal("1.8"),
        volume_ratio=Decimal("2.0"),
        volatility_atr_pct=Decimal("0.03"),
    )
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=strength,
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    assert result.metadata["raw_score"] != ""
    assert result.metadata["adx"] == "35"
    assert result.metadata["breadth_ratio"] == "1.8"
    assert result.metadata["volume_ratio"] == "2.0"
    assert result.metadata["volatility_atr_pct"] == "0.03"


def test_compute_strength_signal_different_regimes() -> None:
    """Test compute_strength_signal works with different regimes."""
    scorer = StrengthScorer()

    for regime in [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS]:
        inputs = StrengthSignalInput(
            exchange=Exchange.NSE,
            strength_inputs=_make_strength_inputs(regime=regime),
            regime_confidence=Decimal("0.9"),
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        result = compute_strength_signal(scorer, inputs, _NOW)
        assert result.regime == regime


def test_validate_input_utc_timestamps() -> None:
    """Test _validate_input passes with UTC timestamps."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    # Should not raise
    _validate_input(inputs, _NOW)


def test_validate_input_non_utc_timestamp_raises() -> None:
    """Test _validate_input raises for non-UTC timestamp."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=datetime(2026, 4, 5, 10, 0, 0, tzinfo=None),  # noqa: DTZ001
    )

    with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
        _validate_input(inputs, _NOW)


def test_validate_input_non_utc_current_raises() -> None:
    """Test _validate_input raises for non-UTC current time."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    non_utc = datetime(2026, 4, 5, 10, 0, 0, tzinfo=None)  # noqa: DTZ001

    with pytest.raises(ConfigError, match="current_utc must be UTC"):
        _validate_input(inputs, non_utc)


def test_validate_input_empty_symbol_raises() -> None:
    """Test _validate_input raises for empty symbol."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="",
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        _validate_input(inputs, _NOW)


def test_validate_input_whitespace_symbol_raises() -> None:
    """Test _validate_input raises for whitespace-only symbol."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0.9"),
        instrument_symbol="  \t  ",
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
        _validate_input(inputs, _NOW)


def test_validate_invalid_regime_confidence_negative() -> None:
    """Test _validate_input raises for negative regime_confidence."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("-0.1"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="regime_confidence must be in \\[0, 1\\]"):
        _validate_input(inputs, _NOW)


def test_validate_invalid_regime_confidence_above_one() -> None:
    """Test _validate_input raises for regime_confidence > 1."""
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("1.5"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )

    with pytest.raises(ConfigError, match="regime_confidence must be in \\[0, 1\\]"):
        _validate_input(inputs, _NOW)


def test_validate_regime_confidence_boundaries() -> None:
    """Test _validate_input accepts boundary values 0 and 1."""
    for conf in [Decimal("0"), Decimal("0.5"), Decimal("1")]:
        inputs = StrengthSignalInput(
            exchange=Exchange.NSE,
            strength_inputs=_make_strength_inputs(),
            regime_confidence=conf,
            instrument_symbol="NIFTY",
            timestamp_utc=_NOW,
        )
        # Should not raise
        _validate_input(inputs, _NOW)


def test_compute_strength_signal_zero_regime_confidence() -> None:
    """Test compute_strength_signal with zero regime confidence."""
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("0"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    # Zero confidence should zero out the result confidence
    assert result.confidence == Decimal("0")


def test_compute_strength_signal_full_regime_confidence() -> None:
    """Test compute_strength_signal with full regime confidence."""
    scorer = StrengthScorer()
    inputs = StrengthSignalInput(
        exchange=Exchange.NSE,
        strength_inputs=_make_strength_inputs(),
        regime_confidence=Decimal("1"),
        instrument_symbol="NIFTY",
        timestamp_utc=_NOW,
    )
    result = compute_strength_signal(scorer, inputs, _NOW)

    # Full confidence should preserve decay
    assert result.confidence <= Decimal("1")


def test_compute_strength_signal_different_exchanges() -> None:
    """Test compute_strength_signal works with different exchanges."""
    scorer = StrengthScorer()

    for exchange in [Exchange.NSE, Exchange.BINANCE, Exchange.BSE]:
        inputs = StrengthSignalInput(
            exchange=exchange,
            strength_inputs=_make_strength_inputs(),
            regime_confidence=Decimal("0.9"),
            instrument_symbol="TEST",
            timestamp_utc=_NOW,
        )
        result = compute_strength_signal(scorer, inputs, _NOW)
        assert isinstance(result, StrengthSignalOutput)
