import random
from datetime import UTC, datetime, time
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.risk.stop_loss import (
    _AUTO_SQUAREOFF_UTC_TIME,
    _DEFAULT_EXIT_PROB_THRESHOLD,
    atr_stop_price,
    calculate_composite_exit_signal,
    should_auto_squareoff,
    should_drl_exit,
    should_time_exit,
    trailing_stop_price,
)

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


class TestAtrStopPrice:
    """Tests for ATR-based stop loss price calculation."""

    def test_buy_stop_calculation(self) -> None:
        """Test BUY stop loss calculation."""
        stop = atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.BUY, Decimal("2"))
        assert stop == Decimal("96")

    def test_sell_stop_calculation(self) -> None:
        """Test SELL stop loss calculation."""
        stop = atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.SELL, Decimal("2"))
        assert stop == Decimal("104")

    def test_default_multiple(self) -> None:
        """Test default multiple parameter."""
        stop = atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.BUY)
        assert stop == Decimal("96")

    def test_negative_entry_price_raises_error(self) -> None:
        """Test that negative entry price raises ConfigError."""
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("0"), Decimal("1"), OrderSide.BUY)

    def test_negative_atr_raises_error(self) -> None:
        """Test that negative ATR raises ConfigError."""
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("100"), Decimal("0"), OrderSide.BUY)

    def test_negative_multiple_raises_error(self) -> None:
        """Test that negative multiple raises ConfigError."""
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.BUY, Decimal("0"))

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        stop = atr_stop_price(Decimal("100.50"), Decimal("1.25"), OrderSide.BUY, Decimal("2.5"))
        expected = Decimal("100.50") - Decimal("1.25") * Decimal("2.5")
        assert stop == expected

    def test_zero_floor_for_buy(self) -> None:
        """Test that BUY stop price is floored at zero."""
        stop = atr_stop_price(Decimal("1"), Decimal("10"), OrderSide.BUY, Decimal("1"))
        assert stop == Decimal("0")


class TestTrailingStopPrice:
    """Tests for trailing stop price calculation."""

    def test_buy_trailing_stop_up(self) -> None:
        """Test BUY trailing stop when price moves up."""
        stop = trailing_stop_price(Decimal("95"), Decimal("110"), OrderSide.BUY, Decimal("0.01"))
        assert stop == Decimal("108.90")

    def test_sell_trailing_stop_down(self) -> None:
        """Test SELL trailing stop when price moves down."""
        stop = trailing_stop_price(Decimal("105"), Decimal("90"), OrderSide.SELL, Decimal("0.01"))
        assert stop == Decimal("90.90")

    def test_buy_trailing_stop_down_preserves_previous(self) -> None:
        """Test BUY trailing stop preserves previous stop when price drops."""
        stop = trailing_stop_price(Decimal("95"), Decimal("90"), OrderSide.BUY, Decimal("0.01"))
        assert stop == Decimal("95")  # Previous stop preserved

    def test_sell_trailing_stop_up_preserves_previous(self) -> None:
        """Test SELL trailing stop preserves previous stop when price rises."""
        stop = trailing_stop_price(Decimal("105"), Decimal("110"), OrderSide.SELL, Decimal("0.01"))
        assert stop == Decimal("105")  # Previous stop preserved

    def test_negative_previous_stop_raises_error(self) -> None:
        """Test that negative previous stop raises ConfigError."""
        with pytest.raises(ConfigError, match="must be positive"):
            trailing_stop_price(Decimal("0"), Decimal("100"), OrderSide.BUY)

    def test_negative_current_price_raises_error(self) -> None:
        """Test that negative current price raises ConfigError."""
        with pytest.raises(ConfigError, match="must be positive"):
            trailing_stop_price(Decimal("95"), Decimal("0"), OrderSide.BUY)

    def test_zero_trail_fraction_raises_error(self) -> None:
        """Test that zero trail fraction raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            trailing_stop_price(Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("0"))

    def test_one_trail_fraction_raises_error(self) -> None:
        """Test that trail fraction of 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            trailing_stop_price(Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("1"))

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        stop = trailing_stop_price(
            Decimal("100.123"), Decimal("150.456"), OrderSide.BUY, Decimal("0.02")
        )
        distance = Decimal("150.456") * Decimal("0.02")
        candidate = Decimal("150.456") - distance
        assert stop == candidate


class TestShouldTimeExit:
    """Tests for time-based exit logic."""

    def test_no_exit_within_max_hold(self) -> None:
        """Test no exit when within maximum holding time."""
        start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        assert not should_time_exit(start, now, 60)

    def test_exit_after_max_hold(self) -> None:
        """Test exit when maximum holding time exceeded."""
        start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 10, 1, tzinfo=UTC)
        assert should_time_exit(start, now, 60)

    def test_boundary_exact_max_hold(self) -> None:
        """Test boundary case at exact max hold time."""
        start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        assert should_time_exit(start, now, 60)

    def test_non_utc_entry_time_raises_error(self) -> None:
        """Test that non-UTC entry time raises ConfigError."""
        start = datetime(2026, 1, 5, 9, 0)  # noqa: DTZ001
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            should_time_exit(start, now, 60)

    def test_non_utc_now_raises_error(self) -> None:
        """Test that non-UTC now time raises ConfigError."""
        start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 10, 0)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            should_time_exit(start, now, 60)

    def test_negative_max_hold_raises_error(self) -> None:
        """Test that negative max_hold_minutes raises ConfigError."""
        start = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="must be positive"):
            should_time_exit(start, now, 0)


class TestShouldAutoSquareoff:
    """Tests for auto-squareoff at 15:10 IST (09:40 UTC)."""

    def test_no_auto_squareoff_before_time(self) -> None:
        """Test no auto-squareoff before 09:40 UTC."""
        now = datetime(2026, 1, 5, 9, 39, tzinfo=UTC)
        assert not should_auto_squareoff(now)

    def test_auto_squareoff_at_time(self) -> None:
        """Test auto-squareoff at exactly 09:40 UTC."""
        now = datetime(2026, 1, 5, 9, 40, tzinfo=UTC)
        assert should_auto_squareoff(now)

    def test_auto_squareoff_after_time(self) -> None:
        """Test auto-squareoff after 09:40 UTC."""
        now = datetime(2026, 1, 5, 9, 45, tzinfo=UTC)
        assert should_auto_squareoff(now)

    def test_auto_squareoff_midday(self) -> None:
        """Test auto-squareoff in middle of day."""
        now = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
        assert should_auto_squareoff(now)

    def test_auto_squareoff_constant(self) -> None:
        """Verify auto-squareoff time constant is correct."""
        assert _AUTO_SQUAREOFF_UTC_TIME == time(hour=9, minute=40)

    def test_non_utc_datetime_raises_error(self) -> None:
        """Test that non-UTC datetime raises ConfigError."""
        now = datetime(2026, 1, 5, 9, 40)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            should_auto_squareoff(now)


class TestShouldDrlExit:
    """Tests for DRL-predicted positive exit logic."""

    def test_exit_above_threshold(self) -> None:
        """Test exit when probability exceeds threshold."""
        assert should_drl_exit(Decimal("0.8"))

    def test_exit_at_threshold(self) -> None:
        """Test exit when probability equals threshold."""
        assert should_drl_exit(Decimal("0.7"))

    def test_no_exit_below_threshold(self) -> None:
        """Test no exit when probability below threshold."""
        assert not should_drl_exit(Decimal("0.5"))

    def test_custom_threshold(self) -> None:
        """Test custom threshold parameter."""
        assert should_drl_exit(Decimal("0.6"), Decimal("0.5"))
        assert not should_drl_exit(Decimal("0.4"), Decimal("0.5"))

    def test_zero_probability(self) -> None:
        """Test zero probability doesn't trigger exit."""
        assert not should_drl_exit(Decimal("0"))

    def test_one_probability_triggers_exit(self) -> None:
        """Test probability of 1 triggers exit."""
        assert should_drl_exit(Decimal("1"))

    def test_default_threshold_constant(self) -> None:
        """Verify default threshold constant is correct."""
        assert _DEFAULT_EXIT_PROB_THRESHOLD == Decimal("0.7")

    def test_negative_probability_raises_error(self) -> None:
        """Test that negative probability raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            should_drl_exit(Decimal("-0.1"))

    def test_probability_above_one_raises_error(self) -> None:
        """Test that probability above 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            should_drl_exit(Decimal("1.1"))

    def test_negative_threshold_raises_error(self) -> None:
        """Test that negative threshold raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            should_drl_exit(Decimal("0.5"), Decimal("-0.1"))

    def test_threshold_of_one_raises_error(self) -> None:
        """Test that threshold of 1 raises ConfigError."""
        with pytest.raises(ConfigError, match="must be between 0 and 1"):
            should_drl_exit(Decimal("0.5"), Decimal("1"))

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling."""
        assert should_drl_exit(Decimal("0.699999"), Decimal("0.699998"))


class TestCalculateCompositeExitSignal:
    """Tests for composite exit signal calculation."""

    def test_no_exit_all_conditions_safe(self) -> None:
        """Test no exit when all conditions are safe."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.5"),
            side=OrderSide.BUY,
        )
        assert not should_exit
        assert reason == "no_exit"

    def test_exit_stop_loss_hit_buy(self) -> None:
        """Test exit when stop loss hit for BUY position."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("94"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "stop_loss_hit"

    def test_exit_stop_loss_hit_sell(self) -> None:
        """Test exit when stop loss hit for SELL position."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("106"),
            stop_price=Decimal("105"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.SELL,
        )
        assert should_exit
        assert reason == "stop_loss_hit"

    def test_exit_auto_squareoff(self) -> None:
        """Test exit at auto-squareoff time."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 40, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "auto_squareoff"

    def test_exit_max_hold_time(self) -> None:
        """Test exit when maximum holding time exceeded (before auto-squareoff)."""
        # Use 9:00 AM entry with 30 minute max hold = 9:30 AM exit (before 9:40 auto-squareoff)
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 31, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=30,
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "max_hold_time"

    def test_exit_drl_positive_signal(self) -> None:
        """Test exit on DRL positive exit signal."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.8"),
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "drl_positive_exit"

    def test_no_exit_drl_signal_below_threshold(self) -> None:
        """Test no exit when DRL signal below threshold."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.5"),
            side=OrderSide.BUY,
        )
        assert not should_exit
        assert reason == "no_exit"

    def test_custom_exit_threshold(self) -> None:
        """Test custom exit probability threshold."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.6"),
            exit_prob_threshold=Decimal("0.5"),
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "drl_positive_exit"

    def test_priority_order_stop_loss_first(self) -> None:
        """Test that stop loss takes priority over other signals."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 40, tzinfo=UTC)  # Auto-squareoff time
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("94"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=120,  # Not exceeded
            exit_probability=Decimal("0.8"),
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "stop_loss_hit"

    def test_none_exit_probability_ignored(self) -> None:
        """Test that None exit probability doesn't cause exit."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=None,
            side=OrderSide.BUY,
        )
        assert not should_exit
        assert reason == "no_exit"

    def test_non_utc_entry_raises_error(self) -> None:
        """Test that non-UTC entry time raises ConfigError."""
        entry = datetime(2026, 1, 5, 9, 0)  # noqa: DTZ001
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            calculate_composite_exit_signal(
                current_price=Decimal("105"),
                stop_price=Decimal("95"),
                entry_time_utc=entry,
                now_utc=now,
                max_hold_minutes=60,
                side=OrderSide.BUY,
            )

    def test_non_utc_now_raises_error(self) -> None:
        """Test that non-UTC now time raises ConfigError."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30)  # noqa: DTZ001
        with pytest.raises(ConfigError, match="timezone-aware UTC"):
            calculate_composite_exit_signal(
                current_price=Decimal("105"),
                stop_price=Decimal("95"),
                entry_time_utc=entry,
                now_utc=now,
                max_hold_minutes=60,
                side=OrderSide.BUY,
            )

    def test_precision_handling(self) -> None:
        """Test Decimal precision handling in composite signal."""
        entry = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
        now = datetime(2026, 1, 5, 9, 30, tzinfo=UTC)
        should_exit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105.123"),
            stop_price=Decimal("95.456"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.699999"),
            exit_prob_threshold=Decimal("0.699998"),
            side=OrderSide.BUY,
        )
        assert should_exit
        assert reason == "drl_positive_exit"
