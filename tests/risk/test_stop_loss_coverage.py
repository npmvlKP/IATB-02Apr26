"""Comprehensive coverage tests for iatb.risk.stop_loss."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.risk.stop_loss import (
    _AUTO_SQUAREOFF_UTC_TIME,
    _DEFAULT_EXIT_PROB_THRESHOLD,
    _calculate_atr_result,
    _calculate_trailing_result,
    _check_stop_loss_hit,
    _format_exit_result,
    _handle_auto_squareoff_exit,
    _handle_drl_exit,
    _handle_time_exit,
    _log_time_exit_result,
    _perform_exit_checks,
    _validate_and_log_composite,
    _validate_atr_inputs,
    _validate_auto_squareoff_input,
    _validate_composite_inputs,
    _validate_drl_exit_inputs,
    _validate_time_exit_inputs,
    _validate_trailing_inputs,
    atr_stop_price,
    calculate_composite_exit_signal,
    should_auto_squareoff,
    should_drl_exit,
    should_time_exit,
    trailing_stop_price,
)

_NOW = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)
_ENTRY = datetime(2026, 5, 25, 7, 59, tzinfo=UTC)


class TestValidateAtrInputs:
    def test_zero_entry_price(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("0"), Decimal("1"), Decimal("1"))

    def test_negative_entry_price(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("-1"), Decimal("1"), Decimal("1"))

    def test_zero_atr(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("1"), Decimal("0"), Decimal("1"))

    def test_negative_atr(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("1"), Decimal("-1"), Decimal("1"))

    def test_zero_multiple(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("1"), Decimal("1"), Decimal("0"))

    def test_negative_multiple(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_atr_inputs(Decimal("1"), Decimal("1"), Decimal("-1"))

    def test_valid_inputs(self) -> None:
        _validate_atr_inputs(Decimal("1"), Decimal("1"), Decimal("1"))


class TestCalculateAtrResult:
    def test_buy_side(self) -> None:
        result = _calculate_atr_result(
            Decimal("100"), Decimal("5"), OrderSide.BUY, Decimal("2")
        )
        assert result == Decimal("90")

    def test_sell_side(self) -> None:
        result = _calculate_atr_result(
            Decimal("100"), Decimal("5"), OrderSide.SELL, Decimal("2")
        )
        assert result == Decimal("110")

    def test_buy_clamps_to_zero(self) -> None:
        result = _calculate_atr_result(
            Decimal("1"), Decimal("10"), OrderSide.BUY, Decimal("2")
        )
        assert result == Decimal("0")

    def test_buy_near_zero(self) -> None:
        result = _calculate_atr_result(
            Decimal("20"), Decimal("10"), OrderSide.BUY, Decimal("2")
        )
        assert result == Decimal("0")


class TestAtrStopPrice:
    def test_buy_side(self) -> None:
        result = atr_stop_price(
            entry_price=Decimal("100"),
            atr=Decimal("5"),
            side=OrderSide.BUY,
            multiple=Decimal("2"),
        )
        assert result == Decimal("90")

    def test_sell_side(self) -> None:
        result = atr_stop_price(
            entry_price=Decimal("100"),
            atr=Decimal("5"),
            side=OrderSide.SELL,
            multiple=Decimal("2"),
        )
        assert result == Decimal("110")

    def test_default_multiple(self) -> None:
        result = atr_stop_price(
            entry_price=Decimal("100"),
            atr=Decimal("5"),
            side=OrderSide.BUY,
        )
        assert result == Decimal("90")

    def test_buy_clamps_to_zero(self) -> None:
        result = atr_stop_price(
            entry_price=Decimal("1"),
            atr=Decimal("10"),
            side=OrderSide.BUY,
            multiple=Decimal("2"),
        )
        assert result == Decimal("0")

    def test_zero_entry_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("0"), Decimal("5"), OrderSide.BUY)

    def test_negative_atr_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("100"), Decimal("-1"), OrderSide.BUY)

    def test_zero_multiple_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            atr_stop_price(Decimal("100"), Decimal("5"), OrderSide.BUY, Decimal("0"))

    def test_small_atr(self) -> None:
        result = atr_stop_price(
            Decimal("1000"), Decimal("0.5"), OrderSide.BUY, Decimal("1")
        )
        assert result == Decimal("999.5")

    def test_large_multiple(self) -> None:
        result = atr_stop_price(
            Decimal("100"), Decimal("5"), OrderSide.BUY, Decimal("10")
        )
        assert result == Decimal("50")


class TestValidateTrailingInputs:
    def test_zero_previous_stop(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_trailing_inputs(Decimal("0"), Decimal("100"), Decimal("0.01"))

    def test_negative_previous_stop(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_trailing_inputs(Decimal("-1"), Decimal("100"), Decimal("0.01"))

    def test_zero_current_price(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_trailing_inputs(Decimal("95"), Decimal("0"), Decimal("0.01"))

    def test_negative_current_price(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            _validate_trailing_inputs(Decimal("95"), Decimal("-1"), Decimal("0.01"))

    def test_zero_trail_fraction(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_trailing_inputs(Decimal("95"), Decimal("100"), Decimal("0"))

    def test_one_trail_fraction(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_trailing_inputs(Decimal("95"), Decimal("100"), Decimal("1"))

    def test_negative_trail_fraction(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_trailing_inputs(Decimal("95"), Decimal("100"), Decimal("-0.5"))

    def test_valid_inputs(self) -> None:
        _validate_trailing_inputs(Decimal("95"), Decimal("100"), Decimal("0.01"))


class TestCalculateTrailingResult:
    def test_buy_moves_up(self) -> None:
        candidate, result = _calculate_trailing_result(
            Decimal("95"), Decimal("110"), OrderSide.BUY, Decimal("0.01")
        )
        assert candidate == Decimal("108.9")
        assert result == Decimal("108.9")

    def test_buy_ratchets(self) -> None:
        candidate, result = _calculate_trailing_result(
            Decimal("95"), Decimal("90"), OrderSide.BUY, Decimal("0.01")
        )
        assert candidate == Decimal("89.1")
        assert result == Decimal("95")

    def test_sell_moves_down(self) -> None:
        candidate, result = _calculate_trailing_result(
            Decimal("105"), Decimal("90"), OrderSide.SELL, Decimal("0.01")
        )
        assert candidate == Decimal("90.9")
        assert result == Decimal("90.9")

    def test_sell_ratchets(self) -> None:
        candidate, result = _calculate_trailing_result(
            Decimal("105"), Decimal("110"), OrderSide.SELL, Decimal("0.01")
        )
        assert candidate == Decimal("111.1")
        assert result == Decimal("105")


class TestTrailingStopPrice:
    def test_buy_price_moves_up(self) -> None:
        result = trailing_stop_price(
            previous_stop=Decimal("95"),
            current_price=Decimal("110"),
            side=OrderSide.BUY,
            trail_fraction=Decimal("0.01"),
        )
        assert result == Decimal("108.9")

    def test_buy_price_moves_down_ratchets(self) -> None:
        result = trailing_stop_price(
            previous_stop=Decimal("95"),
            current_price=Decimal("90"),
            side=OrderSide.BUY,
            trail_fraction=Decimal("0.01"),
        )
        assert result == Decimal("95")

    def test_sell_side_moves_down(self) -> None:
        result = trailing_stop_price(
            previous_stop=Decimal("105"),
            current_price=Decimal("90"),
            side=OrderSide.SELL,
            trail_fraction=Decimal("0.01"),
        )
        assert result == Decimal("90.9")

    def test_sell_side_ratchets(self) -> None:
        result = trailing_stop_price(
            previous_stop=Decimal("105"),
            current_price=Decimal("110"),
            side=OrderSide.SELL,
            trail_fraction=Decimal("0.01"),
        )
        assert result == Decimal("105")

    def test_default_trail_fraction(self) -> None:
        result = trailing_stop_price(Decimal("95"), Decimal("100"), OrderSide.BUY)
        assert result == Decimal("99")

    def test_zero_previous_stop_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            trailing_stop_price(Decimal("0"), Decimal("100"), OrderSide.BUY)

    def test_zero_current_price_raises(self) -> None:
        with pytest.raises(ConfigError, match="must be positive"):
            trailing_stop_price(Decimal("95"), Decimal("0"), OrderSide.BUY)

    def test_zero_trail_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            trailing_stop_price(
                Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("0")
            )

    def test_one_trail_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            trailing_stop_price(
                Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("1")
            )

    def test_negative_trail_fraction_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            trailing_stop_price(
                Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("-0.5")
            )


class TestValidateTimeExitInputs:
    def test_naive_entry_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_time_exit_inputs(datetime(2024, 1, 1, 9, 30), _NOW, 60)

    def test_naive_now_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_time_exit_inputs(_NOW, datetime(2024, 1, 1, 10, 0), 60)

    def test_zero_max_hold_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            _validate_time_exit_inputs(_ENTRY, _NOW, 0)

    def test_negative_max_hold_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            _validate_time_exit_inputs(_ENTRY, _NOW, -5)

    def test_valid_inputs(self) -> None:
        _validate_time_exit_inputs(_ENTRY, _NOW, 60)


class TestLogTimeExitResult:
    def test_logs_without_error(self) -> None:
        elapsed = _NOW - _ENTRY
        _log_time_exit_result(_ENTRY, _NOW, 60, elapsed, False)


class TestShouldTimeExit:
    def test_not_exceeded(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        assert should_time_exit(entry, now, 60) is False

    def test_exceeded(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 10, 31, tzinfo=UTC)
        assert should_time_exit(entry, now, 60) is True

    def test_exact_boundary(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = entry + timedelta(minutes=60)
        assert should_time_exit(entry, now, 60) is True

    def test_naive_entry_raises(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30)
        now = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        with pytest.raises(ConfigError, match="UTC"):
            should_time_exit(entry, now, 60)

    def test_naive_now_raises(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 10, 0)
        with pytest.raises(ConfigError, match="UTC"):
            should_time_exit(entry, now, 60)

    def test_zero_max_hold_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            should_time_exit(_ENTRY, _NOW, 0)

    def test_negative_max_hold_raises(self) -> None:
        with pytest.raises(ConfigError, match="positive"):
            should_time_exit(_ENTRY, _NOW, -5)

    def test_one_minute_before(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = entry + timedelta(minutes=59)
        assert should_time_exit(entry, now, 60) is False

    def test_one_second_over(self) -> None:
        entry = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
        now = entry + timedelta(minutes=60, seconds=1)
        assert should_time_exit(entry, now, 60) is True


class TestValidateAutoSquareoffInput:
    def test_naive_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_auto_squareoff_input(datetime(2024, 1, 1, 9, 40))

    def test_utc_passes(self) -> None:
        _validate_auto_squareoff_input(datetime(2024, 1, 1, 9, 40, tzinfo=UTC))


class TestShouldAutoSquareoff:
    def test_before_squareoff_time(self) -> None:
        now = datetime(2024, 1, 1, 9, 39, tzinfo=UTC)
        assert should_auto_squareoff(now) is False

    def test_at_squareoff_time(self) -> None:
        now = datetime(2024, 1, 1, 9, 40, tzinfo=UTC)
        assert should_auto_squareoff(now) is True

    def test_after_squareoff_time(self) -> None:
        now = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
        assert should_auto_squareoff(now) is True

    def test_naive_datetime_raises(self) -> None:
        now = datetime(2024, 1, 1, 9, 40)
        with pytest.raises(ConfigError, match="UTC"):
            should_auto_squareoff(now)

    def test_utc_time_constant(self) -> None:
        assert _AUTO_SQUAREOFF_UTC_TIME == time(9, 40)

    def test_just_before_midnight(self) -> None:
        now = datetime(2024, 1, 1, 23, 59, tzinfo=UTC)
        assert should_auto_squareoff(now) is True

    def test_midnight(self) -> None:
        now = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        assert should_auto_squareoff(now) is False


class TestValidateDrlExitInputs:
    def test_negative_probability(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_drl_exit_inputs(Decimal("-0.1"), Decimal("0.5"))

    def test_probability_above_one(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_drl_exit_inputs(Decimal("1.1"), Decimal("0.5"))

    def test_zero_threshold(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_drl_exit_inputs(Decimal("0.5"), Decimal("0"))

    def test_one_threshold(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_drl_exit_inputs(Decimal("0.5"), Decimal("1"))

    def test_negative_threshold(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            _validate_drl_exit_inputs(Decimal("0.5"), Decimal("-0.5"))

    def test_valid_inputs(self) -> None:
        _validate_drl_exit_inputs(Decimal("0.5"), Decimal("0.5"))


class TestShouldDrlExit:
    def test_above_threshold(self) -> None:
        assert should_drl_exit(Decimal("0.8"), Decimal("0.7")) is True

    def test_at_threshold(self) -> None:
        assert should_drl_exit(Decimal("0.7"), Decimal("0.7")) is True

    def test_below_threshold(self) -> None:
        assert should_drl_exit(Decimal("0.5"), Decimal("0.7")) is False

    def test_default_threshold(self) -> None:
        assert should_drl_exit(Decimal("0.8")) is True
        assert should_drl_exit(Decimal("0.6")) is False

    def test_zero_exit_probability(self) -> None:
        assert should_drl_exit(Decimal("0"), Decimal("0.5")) is False

    def test_one_exit_probability(self) -> None:
        assert should_drl_exit(Decimal("1"), Decimal("0.5")) is True

    def test_negative_probability_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            should_drl_exit(Decimal("-0.1"), Decimal("0.5"))

    def test_probability_above_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            should_drl_exit(Decimal("1.1"), Decimal("0.5"))

    def test_zero_threshold_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            should_drl_exit(Decimal("0.5"), Decimal("0"))

    def test_one_threshold_raises(self) -> None:
        with pytest.raises(ConfigError, match="between 0 and 1"):
            should_drl_exit(Decimal("0.5"), Decimal("1"))

    def test_default_threshold_constant(self) -> None:
        assert _DEFAULT_EXIT_PROB_THRESHOLD == Decimal("0.7")


class TestCheckStopLossHit:
    def test_buy_hit(self) -> None:
        hit, reason = _check_stop_loss_hit(Decimal("90"), Decimal("95"), OrderSide.BUY)
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_buy_not_hit(self) -> None:
        hit, reason = _check_stop_loss_hit(Decimal("100"), Decimal("95"), OrderSide.BUY)
        assert hit is False
        assert reason is None

    def test_sell_hit(self) -> None:
        hit, reason = _check_stop_loss_hit(
            Decimal("110"), Decimal("105"), OrderSide.SELL
        )
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_sell_not_hit(self) -> None:
        hit, reason = _check_stop_loss_hit(
            Decimal("100"), Decimal("105"), OrderSide.SELL
        )
        assert hit is False
        assert reason is None

    def test_buy_at_stop_price(self) -> None:
        hit, reason = _check_stop_loss_hit(Decimal("95"), Decimal("95"), OrderSide.BUY)
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_sell_at_stop_price(self) -> None:
        hit, reason = _check_stop_loss_hit(
            Decimal("105"), Decimal("105"), OrderSide.SELL
        )
        assert hit is True
        assert reason == "stop_loss_hit"


class TestValidateCompositeInputs:
    def test_naive_now_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_composite_inputs(_ENTRY, datetime(2024, 1, 1, 9, 10))

    def test_naive_entry_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            _validate_composite_inputs(datetime(2024, 1, 1, 9, 0), _NOW)

    def test_both_utc_passes(self) -> None:
        _validate_composite_inputs(_ENTRY, _NOW)


class TestHandleAutoSquareoffExit:
    def test_triggers(self) -> None:
        now = datetime(2024, 1, 1, 9, 41, tzinfo=UTC)
        hit, reason = _handle_auto_squareoff_exit(now)
        assert hit is True
        assert reason == "auto_squareoff"

    def test_not_triggers(self) -> None:
        now = datetime(2024, 1, 1, 9, 39, tzinfo=UTC)
        hit, reason = _handle_auto_squareoff_exit(now)
        assert hit is False
        assert reason is None


class TestHandleTimeExit:
    def test_triggers(self) -> None:
        entry = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 31, tzinfo=UTC)
        hit, reason = _handle_time_exit(entry, now, 60)
        assert hit is True
        assert reason == "max_hold_time"

    def test_not_triggers(self) -> None:
        entry = datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = _handle_time_exit(entry, now, 60)
        assert hit is False
        assert reason is None


class TestHandleDrlExit:
    def test_triggers(self) -> None:
        hit, reason = _handle_drl_exit(Decimal("0.8"), Decimal("0.7"))
        assert hit is True
        assert reason == "drl_positive_exit"

    def test_not_triggers_below(self) -> None:
        hit, reason = _handle_drl_exit(Decimal("0.5"), Decimal("0.7"))
        assert hit is False
        assert reason is None

    def test_not_triggers_none(self) -> None:
        hit, reason = _handle_drl_exit(None, Decimal("0.7"))
        assert hit is False
        assert reason is None


class TestPerformExitChecks:
    def test_stop_loss_hit_buy(self) -> None:
        hit, reason = _perform_exit_checks(
            Decimal("90"),
            Decimal("95"),
            _ENTRY,
            _NOW,
            60,
            None,
            Decimal("0.7"),
            OrderSide.BUY,
        )
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_auto_squareoff(self) -> None:
        late_now = datetime(2024, 1, 1, 9, 41, tzinfo=UTC)
        hit, reason = _perform_exit_checks(
            Decimal("105"),
            Decimal("95"),
            _ENTRY,
            late_now,
            60,
            None,
            Decimal("0.7"),
            OrderSide.BUY,
        )
        assert hit is True
        assert reason == "auto_squareoff"

    def test_max_hold_time(self) -> None:
        early_entry = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 31, tzinfo=UTC)
        hit, reason = _perform_exit_checks(
            Decimal("105"),
            Decimal("95"),
            early_entry,
            now,
            60,
            None,
            Decimal("0.7"),
            OrderSide.BUY,
        )
        assert hit is True
        assert reason == "max_hold_time"

    def test_drl_exit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = _perform_exit_checks(
            Decimal("105"),
            Decimal("95"),
            entry,
            now,
            60,
            Decimal("0.8"),
            Decimal("0.7"),
            OrderSide.BUY,
        )
        assert hit is True
        assert reason == "drl_positive_exit"

    def test_no_exit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = _perform_exit_checks(
            Decimal("105"),
            Decimal("95"),
            entry,
            now,
            60,
            None,
            Decimal("0.7"),
            OrderSide.BUY,
        )
        assert hit is False
        assert reason is None


class TestFormatExitResult:
    def test_hit_with_reason(self) -> None:
        result = _format_exit_result(True, "stop_loss_hit")
        assert result == (True, "stop_loss_hit")

    def test_hit_with_none_reason(self) -> None:
        result = _format_exit_result(True, None)
        assert result == (True, "unknown_reason")

    def test_no_exit(self) -> None:
        result = _format_exit_result(False, None)
        assert result == (False, "no_exit")


class TestValidateAndLogComposite:
    def test_utc_passes(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        _validate_and_log_composite(
            Decimal("105"),
            Decimal("95"),
            entry,
            now,
            60,
            None,
            Decimal("0.7"),
            OrderSide.BUY,
        )

    def test_naive_now_raises(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        with pytest.raises(ConfigError, match="UTC"):
            _validate_and_log_composite(
                Decimal("105"),
                Decimal("95"),
                entry,
                datetime(2024, 1, 1, 9, 10),
                60,
                None,
                Decimal("0.7"),
                OrderSide.BUY,
            )


class TestCalculateCompositeExitSignal:
    def test_no_exit_when_all_clear(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert hit is False
        assert reason == "no_exit"

    def test_stop_loss_hit_buy(self) -> None:
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("90"),
            stop_price=Decimal("95"),
            entry_time_utc=_ENTRY,
            now_utc=_NOW,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_stop_loss_hit_sell(self) -> None:
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("110"),
            stop_price=Decimal("105"),
            entry_time_utc=_ENTRY,
            now_utc=_NOW,
            max_hold_minutes=60,
            side=OrderSide.SELL,
        )
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_auto_squareoff_trigger(self) -> None:
        late_now = datetime(2024, 1, 1, 9, 41, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=_ENTRY,
            now_utc=late_now,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert hit is True
        assert reason == "auto_squareoff"

    def test_max_hold_time_exceeded(self) -> None:
        early_entry = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 31, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=early_entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.BUY,
        )
        assert hit is True
        assert reason == "max_hold_time"

    def test_drl_positive_exit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.8"),
            exit_prob_threshold=Decimal("0.7"),
            side=OrderSide.BUY,
        )
        assert hit is True
        assert reason == "drl_positive_exit"

    def test_drl_exit_skipped_when_none(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=None,
            side=OrderSide.BUY,
        )
        assert hit is False

    def test_stop_loss_priority_over_others(self) -> None:
        early_entry = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        late_now = datetime(2024, 1, 1, 9, 41, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("90"),
            stop_price=Decimal("95"),
            entry_time_utc=early_entry,
            now_utc=late_now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.9"),
            side=OrderSide.BUY,
        )
        assert hit is True
        assert reason == "stop_loss_hit"

    def test_non_utc_raises(self) -> None:
        with pytest.raises(ConfigError, match="UTC"):
            calculate_composite_exit_signal(
                Decimal("105"),
                Decimal("95"),
                datetime(2024, 1, 1, 9, 0),
                _NOW,
                60,
                side=OrderSide.BUY,
            )

    def test_sell_no_exit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("95"),
            stop_price=Decimal("105"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.SELL,
        )
        assert hit is False
        assert reason == "no_exit"

    def test_drl_below_threshold_no_exit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("105"),
            stop_price=Decimal("95"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            exit_probability=Decimal("0.5"),
            exit_prob_threshold=Decimal("0.7"),
            side=OrderSide.BUY,
        )
        assert hit is False
        assert reason == "no_exit"

    def test_sell_stop_not_hit(self) -> None:
        entry = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        now = datetime(2024, 1, 1, 9, 10, tzinfo=UTC)
        hit, reason = calculate_composite_exit_signal(
            current_price=Decimal("100"),
            stop_price=Decimal("110"),
            entry_time_utc=entry,
            now_utc=now,
            max_hold_minutes=60,
            side=OrderSide.SELL,
        )
        assert hit is False
