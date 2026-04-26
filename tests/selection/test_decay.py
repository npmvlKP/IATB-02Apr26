"""Tests for selection.decay module."""

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


def test_validate_timestamps_signal_not_utc() -> None:
    naive = datetime(2026, 1, 1)  # noqa: DTZ001
    with pytest.raises(ConfigError, match="signal_timestamp must be UTC"):
        _validate_timestamps(naive, datetime.now(UTC))


def test_validate_timestamps_current_not_utc() -> None:
    naive = datetime(2026, 1, 1)  # noqa: DTZ001
    with pytest.raises(ConfigError, match="current_timestamp must be UTC"):
        _validate_timestamps(datetime.now(UTC), naive)


def test_decay_rate_for_known_signal() -> None:
    assert _decay_rate_for("sentiment") == Decimal("0.25")
    assert _decay_rate_for("strength") == Decimal("0.10")


def test_decay_rate_for_override() -> None:
    assert _decay_rate_for("sentiment", {"sentiment": Decimal("0.5")}) == Decimal("0.5")


def test_decay_rate_for_unknown_signal() -> None:
    with pytest.raises(ConfigError, match="unknown signal_name"):
        _decay_rate_for("nonexistent")


def test_temporal_decay_recent() -> None:
    signal_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    current_time = datetime(2026, 1, 1, 10, 30, 0, tzinfo=UTC)
    result = temporal_decay(signal_time, current_time, "sentiment")
    assert Decimal("0") < result <= Decimal("1")


def test_temporal_decay_far_past() -> None:
    signal_time = datetime(2026, 1, 1, tzinfo=UTC)
    current_time = datetime(2026, 1, 3, tzinfo=UTC)
    result = temporal_decay(signal_time, current_time, "sentiment")
    assert result < Decimal("0.5")


def test_temporal_decay_future_raises() -> None:
    signal_time = datetime(2026, 1, 2, tzinfo=UTC)
    current_time = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ConfigError, match="cannot be in the future"):
        temporal_decay(signal_time, current_time, "sentiment")


def test_temporal_decay_clamped_at_zero_and_one() -> None:
    signal_time = datetime(2026, 1, 1, tzinfo=UTC)
    current_time = signal_time
    result = temporal_decay(signal_time, current_time, "sentiment")
    assert Decimal("0") <= result <= Decimal("1")


def test_temporal_decay_drl_slower_decay() -> None:
    signal_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    current_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    drl = temporal_decay(signal_time, current_time, "drl")
    sentiment = temporal_decay(signal_time, current_time, "sentiment")
    assert drl > sentiment
