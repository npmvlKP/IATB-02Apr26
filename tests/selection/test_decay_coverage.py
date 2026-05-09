"""Extended coverage tests for selection.decay module.

This module exercises every branch, boundary, and error path in decay.py
to drive statement and branch coverage to 100%%.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.selection.decay import (
    _decay_rate_for,
    _validate_timestamps,
    temporal_decay,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> datetime:
    """Build a UTC datetime to cut boilerplate."""
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


# ---------------------------------------------------------------------------
# _validate_timestamps – error paths (already partially covered by test_decay.py)
# ---------------------------------------------------------------------------


def test_validate_timestamps_both_utc() -> None:
    """Both timestamps in UTC should pass without raising."""
    signal = _utc(2026, 1, 1)
    current = _utc(2026, 1, 1)
    _validate_timestamps(signal, current)


def test_validate_timestamps_current_not_utc_raises() -> None:
    """Current timestamp not in UTC raises ConfigError."""
    signal = _utc(2026, 1, 1)
    current = datetime(2026, 1, 1)  # noqa: DTZ001
    with pytest.raises(ConfigError, match="current_timestamp must be UTC"):
        _validate_timestamps(signal, current)


def test_validate_timestamps_signal_not_utc_raises() -> None:
    """Signal timestamp not in UTC raises ConfigError."""
    signal = datetime(2026, 1, 1)  # noqa: DTZ001
    current = _utc(2026, 1, 1)
    with pytest.raises(ConfigError, match="signal_timestamp must be UTC"):
        _validate_timestamps(signal, current)


# ---------------------------------------------------------------------------
# _decay_rate_for – boundary and override coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "signal_name,overrides,expected",
    [
        ("sentiment", None, Decimal("0.25")),
        ("strength", None, Decimal("0.10")),
        ("volume_profile", None, Decimal("0.15")),
        ("drl", None, Decimal("0.05")),
        ("sentiment", {"sentiment": Decimal("0.99")}, Decimal("0.99")),
        ("sentiment", {}, Decimal("0.25")),  # empty overrides dict
    ],
)
def test_decay_rate_for_parametrized(
    signal_name: str, overrides: dict[str, Decimal] | None, expected: Decimal
) -> None:
    """Decay rate lookup with and without overrides."""
    result = _decay_rate_for(signal_name, overrides)
    assert result == expected


def test_decay_rate_for_unknown_signal_raises() -> None:
    """Unknown signal name raises ConfigError."""
    with pytest.raises(ConfigError, match="unknown signal_name for decay"):
        _decay_rate_for("nonexistent_signal")


# ---------------------------------------------------------------------------
# temporal_decay – happy path, boundaries, and edge cases
# ---------------------------------------------------------------------------


def test_temporal_decay_zero_elapsed() -> None:
    """When signal and current are identical, decay factor should be 1.0."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    result = temporal_decay(signal_time, signal_time, "sentiment")
    assert result == Decimal("1")


def test_temporal_decay_half_life() -> None:
    """After one half-life, decay factor should be approximately 0.5.

    For sentiment (rate=0.25), half-life = ln(2)/rate ≈ 2.77 hours.
    We compute the exact expected value with exp(-rate * hours).
    """
    from math import exp, log

    rate_float = 0.25
    half_life_hours = log(2) / rate_float  # ≈ 2.7726 hours
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 10, 0, 0) + __import__("datetime").timedelta(
        hours=half_life_hours
    )
    result = temporal_decay(signal_time, current_time, "sentiment")
    expected = Decimal(str(exp(-rate_float * half_life_hours)))
    # Allow small tolerance for float→Decimal conversion
    assert abs(result - expected) < Decimal("0.0001")
    assert abs(result - Decimal("0.5")) < Decimal("0.0001")


def test_temporal_decay_exact_one_hour() -> None:
    """One hour elapsed with sentiment rate 0.25 → exp(-0.25) ≈ 0.7788."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 11, 0, 0)
    result = temporal_decay(signal_time, current_time, "sentiment")
    expected = Decimal(str(__import__("math").exp(-0.25)))  # noqa: S301
    assert abs(result - expected) < Decimal("0.0001")


def test_temporal_decay_very_large_elapsed_clamps_exponent() -> None:
    """Extremely large elapsed time should not overflow math.exp because exponent is clamped."""
    signal_time = _utc(2026, 1, 1, 0, 0, 0)
    # 100 years later
    current_time = _utc(2126, 1, 1, 0, 0, 0)
    result = temporal_decay(signal_time, current_time, "sentiment")
    # Should be a very small positive number, clamped to [0, 1]
    assert Decimal("0") <= result <= Decimal("1")
    assert result < Decimal("0.0001")


# ---------------------------------------------------------------------------
# temporal_decay – zero / negative elapsed handling
# ---------------------------------------------------------------------------


def test_temporal_decay_negative_elapsed_raises() -> None:
    """signal_timestamp in the future raises ConfigError."""
    signal_time = _utc(2026, 1, 2, 0, 0, 0)
    current_time = _utc(2026, 1, 1, 0, 0, 0)
    with pytest.raises(ConfigError, match="cannot be in the future"):
        temporal_decay(signal_time, current_time, "sentiment")


def test_temporal_decay_all_builtin_signals() -> None:
    """Ensure every built-in signal can be evaluated without error."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 11, 0, 0)
    for signal_name in ("sentiment", "strength", "volume_profile", "drl"):
        result = temporal_decay(signal_time, current_time, signal_name)
        assert Decimal("0") < result <= Decimal("1")


# ---------------------------------------------------------------------------
# temporal_decay – override integration
# ---------------------------------------------------------------------------


def test_temporal_decay_with_override() -> None:
    """Overriding rate affects computed decay."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 12, 0, 0)
    default_result = temporal_decay(signal_time, current_time, "sentiment")
    override_result = temporal_decay(
        signal_time,
        current_time,
        "sentiment",
        decay_overrides={"sentiment": Decimal("0.5")},
    )
    # Higher rate → faster decay → smaller value
    assert override_result < default_result


# ---------------------------------------------------------------------------
# temporal_decay – Decimal output validation
# ---------------------------------------------------------------------------


def test_temporal_decay_returns_decimal() -> None:
    """Result must be a Decimal instance."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 11, 0, 0)
    result = temporal_decay(signal_time, current_time, "sentiment")
    assert isinstance(result, Decimal)


def test_temporal_decay_output_precision() -> None:
    """Result should not lose precision beyond acceptable float→Decimal bounds."""
    signal_time = _utc(2026, 1, 1, 10, 0, 0)
    current_time = _utc(2026, 1, 1, 10, 30, 0)
    result = temporal_decay(signal_time, current_time, "sentiment")
    # exp(-0.25 * 0.5) ≈ 0.8824969
    expected = Decimal("0.8824969")
    assert abs(result - expected) < Decimal("0.0001")


# ---------------------------------------------------------------------------
# Branch coverage: clamp_01 interaction
# ---------------------------------------------------------------------------


def test_temporal_decay_near_zero_returns_small_positive() -> None:
    """Very old signals should still return a small positive Decimal, not negative."""
    signal_time = _utc(2000, 1, 1, 0, 0, 0)
    current_time = _utc(2026, 1, 1, 0, 0, 0)
    result = temporal_decay(signal_time, current_time, "sentiment")
    assert result >= Decimal("0")
    assert result < Decimal("0.01")
