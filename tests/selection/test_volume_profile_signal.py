"""Tests for selection.volume_profile_signal module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.market_strength.regime_detector import MarketRegime
from iatb.market_strength.volume_profile import VolumeProfile
from iatb.selection._util import DirectionalIntent
from iatb.selection.volume_profile_signal import (
    ProfileShape,
    VolumeProfileSignalInput,
    VolumeProfileSignalOutput,
    _poc_distance_pct,
    _poc_proximity,
    _regime_adjusted_poc,
    _shape_score_for_intent,
    _va_width_pct,
    _va_width_ratio,
    _validate_input,
    classify_profile_shape,
    compute_volume_profile_signal,
)

NOW_UTC = datetime(2026, 4, 26, 0, 0, 0, tzinfo=UTC)


def _make_vp(
    poc: Decimal = Decimal("95"),
    vah: Decimal = Decimal("110"),
    val: Decimal = Decimal("90"),
    total_volume: Decimal = Decimal("10000"),
) -> VolumeProfile:
    return VolumeProfile(poc=poc, vah=vah, val=val, total_volume=total_volume)


class TestClassifyProfileShape:
    def test_bullish(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("110"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.P_BULLISH

    def test_bearish(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("82"), vah=Decimal("100"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.B_BEARISH

    def test_balanced(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("90"), vah=Decimal("100"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.D_BALANCED

    def test_zero_range(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("100"), val=Decimal("100"), total_volume=Decimal("0")
        )
        assert classify_profile_shape(vp) == ProfileShape.D_BALANCED

    def test_boundary_bullish(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("110"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.P_BULLISH

    def test_boundary_bearish(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("86"), vah=Decimal("110"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.B_BEARISH

    def test_exact_midpoint(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("95"), vah=Decimal("110"), val=Decimal("80"), total_volume=Decimal("1000")
        )
        assert classify_profile_shape(vp) == ProfileShape.D_BALANCED


class TestPocProximity:
    def test_at_poc(self) -> None:
        vp = _make_vp()
        result = _poc_proximity(Decimal("95"), vp)
        assert result == Decimal("1")

    def test_far(self) -> None:
        vp = _make_vp()
        result = _poc_proximity(Decimal("50"), vp)
        assert result < Decimal("1")

    def test_zero_range_at_poc(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("100"), val=Decimal("100"), total_volume=Decimal("0")
        )
        assert _poc_proximity(Decimal("100"), vp) == Decimal("1")

    def test_zero_range_not_at_poc(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("100"), val=Decimal("100"), total_volume=Decimal("0")
        )
        assert _poc_proximity(Decimal("50"), vp) == Decimal("0")

    def test_clamped_to_01(self) -> None:
        vp = _make_vp()
        result = _poc_proximity(Decimal("0"), vp)
        assert Decimal("0") <= result <= Decimal("1")


class TestVaWidthRatio:
    def test_narrow(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("101"), val=Decimal("99"), total_volume=Decimal("1000")
        )
        result = _va_width_ratio(Decimal("100"), vp)
        assert result > Decimal("0")

    def test_wide(self) -> None:
        vp = VolumeProfile(
            poc=Decimal("100"), vah=Decimal("200"), val=Decimal("0"), total_volume=Decimal("1000")
        )
        result = _va_width_ratio(Decimal("100"), vp)
        assert result < Decimal("1")

    def test_zero_price(self) -> None:
        vp = _make_vp()
        assert _va_width_ratio(Decimal("0"), vp) == Decimal("0")

    def test_negative_price(self) -> None:
        vp = _make_vp()
        assert _va_width_ratio(Decimal("-10"), vp) == Decimal("0")


class TestPocDistancePct:
    def test_basic(self) -> None:
        vp = _make_vp()
        result = _poc_distance_pct(Decimal("105"), vp)
        assert result > Decimal("0")

    def test_at_poc(self) -> None:
        vp = _make_vp()
        result = _poc_distance_pct(Decimal("95"), vp)
        assert result == Decimal("0")

    def test_zero_price(self) -> None:
        vp = _make_vp()
        assert _poc_distance_pct(Decimal("0"), vp) == Decimal("0")


class TestVaWidthPct:
    def test_basic(self) -> None:
        vp = _make_vp()
        result = _va_width_pct(Decimal("100"), vp)
        assert result > Decimal("0")

    def test_zero_price(self) -> None:
        vp = _make_vp()
        assert _va_width_pct(Decimal("0"), vp) == Decimal("0")


class TestRegimeAdjustedPoc:
    def test_bull(self) -> None:
        assert _regime_adjusted_poc(Decimal("0.8"), MarketRegime.BULL) < Decimal("0.8")

    def test_bear(self) -> None:
        assert _regime_adjusted_poc(Decimal("0.8"), MarketRegime.BEAR) < Decimal("0.8")

    def test_sideways(self) -> None:
        assert _regime_adjusted_poc(Decimal("0.8"), MarketRegime.SIDEWAYS) == Decimal("0.8")

    def test_clamped(self) -> None:
        result = _regime_adjusted_poc(Decimal("0.8"), MarketRegime.BULL)
        assert Decimal("0") <= result <= Decimal("1")


class TestShapeScoreForIntent:
    def test_long_bullish_high(self) -> None:
        long_score = _shape_score_for_intent(ProfileShape.P_BULLISH, DirectionalIntent.LONG)
        assert long_score == Decimal("0.80")

    def test_short_bullish_low(self) -> None:
        short_score = _shape_score_for_intent(ProfileShape.P_BULLISH, DirectionalIntent.SHORT)
        assert short_score == Decimal("0.20")

    def test_long_bearish_low(self) -> None:
        long_score = _shape_score_for_intent(ProfileShape.B_BEARISH, DirectionalIntent.LONG)
        assert long_score == Decimal("0.20")

    def test_short_bearish_high(self) -> None:
        short_score = _shape_score_for_intent(ProfileShape.B_BEARISH, DirectionalIntent.SHORT)
        assert short_score == Decimal("0.80")

    def test_balanced_equal(self) -> None:
        long_score = _shape_score_for_intent(ProfileShape.D_BALANCED, DirectionalIntent.LONG)
        short_score = _shape_score_for_intent(ProfileShape.D_BALANCED, DirectionalIntent.SHORT)
        assert long_score == short_score == Decimal("0.50")

    def test_neutral_uses_long(self) -> None:
        neutral_score = _shape_score_for_intent(ProfileShape.P_BULLISH, DirectionalIntent.NEUTRAL)
        long_score = _shape_score_for_intent(ProfileShape.P_BULLISH, DirectionalIntent.LONG)
        assert neutral_score == long_score


class TestValidateInput:
    def test_non_utc_timestamp(self) -> None:
        with pytest.raises(ConfigError, match="timestamp_utc must be UTC"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("100"),
                    instrument_symbol="TEST",
                    timestamp_utc=datetime(
                        2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))
                    ),
                ),
                NOW_UTC,
            )

    def test_non_utc_current(self) -> None:
        with pytest.raises(ConfigError, match="current_utc must be UTC"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("100"),
                    instrument_symbol="TEST",
                    timestamp_utc=NOW_UTC,
                ),
                datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            )

    def test_empty_symbol(self) -> None:
        with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("100"),
                    instrument_symbol="",
                    timestamp_utc=NOW_UTC,
                ),
                NOW_UTC,
            )

    def test_whitespace_symbol(self) -> None:
        with pytest.raises(ConfigError, match="instrument_symbol cannot be empty"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("100"),
                    instrument_symbol="   ",
                    timestamp_utc=NOW_UTC,
                ),
                NOW_UTC,
            )

    def test_zero_price(self) -> None:
        with pytest.raises(ConfigError, match="current_price must be positive"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("0"),
                    instrument_symbol="TEST",
                    timestamp_utc=NOW_UTC,
                ),
                NOW_UTC,
            )

    def test_negative_price(self) -> None:
        with pytest.raises(ConfigError, match="current_price must be positive"):
            _validate_input(
                VolumeProfileSignalInput(
                    profile=_make_vp(),
                    current_price=Decimal("-10"),
                    instrument_symbol="TEST",
                    timestamp_utc=NOW_UTC,
                ),
                NOW_UTC,
            )

    def test_valid(self) -> None:
        _validate_input(
            VolumeProfileSignalInput(
                profile=_make_vp(),
                current_price=Decimal("100"),
                instrument_symbol="TEST",
                timestamp_utc=NOW_UTC,
            ),
            NOW_UTC,
        )


class TestComputeVolumeProfileSignal:
    def test_happy_path(self) -> None:
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=NOW_UTC,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC)
        assert isinstance(result, VolumeProfileSignalOutput)
        assert Decimal("0") <= result.score <= Decimal("1")
        assert Decimal("0") <= result.confidence <= Decimal("1")

    def test_metadata_keys(self) -> None:
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=NOW_UTC,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC)
        expected = {"poc", "vah", "val", "shape", "total_volume", "intent"}
        assert expected.issubset(result.metadata.keys())

    def test_decay_over_time(self) -> None:
        old_ts = NOW_UTC - timedelta(hours=200)
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=old_ts,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC)
        assert result.score < Decimal("1")

    def test_bull_regime(self) -> None:
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=NOW_UTC,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC, regime=MarketRegime.BULL)
        assert isinstance(result, VolumeProfileSignalOutput)

    def test_short_intent(self) -> None:
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=NOW_UTC,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC, intent=DirectionalIntent.SHORT)
        assert result.metadata["intent"] == "SHORT"

    def test_shape_preserved(self) -> None:
        inputs = VolumeProfileSignalInput(
            profile=_make_vp(poc=Decimal("100"), vah=Decimal("110"), val=Decimal("80")),
            current_price=Decimal("100"),
            instrument_symbol="TEST",
            timestamp_utc=NOW_UTC,
        )
        result = compute_volume_profile_signal(inputs, NOW_UTC)
        assert result.shape == ProfileShape.P_BULLISH


class TestVolumeProfileSignalOutput:
    def test_frozen(self) -> None:
        output = VolumeProfileSignalOutput(
            score=Decimal("0.5"),
            confidence=Decimal("0.8"),
            shape=ProfileShape.D_BALANCED,
            poc_distance_pct=Decimal("1"),
            va_width_pct=Decimal("5"),
            metadata={},
        )
        with pytest.raises(AttributeError):
            output.score = Decimal("0.9")
