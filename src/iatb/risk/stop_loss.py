"""
Stop-loss calculation utilities with trailing stop, time-based auto-squareoff,
and DRL-predicted positive exit probability threshold.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)

# IST is UTC+5:30, so 15:10 IST = 09:40 UTC (stored as naive time for comparison)
_AUTO_SQUAREOFF_UTC_TIME = time(hour=9, minute=40)
_DEFAULT_EXIT_PROB_THRESHOLD = Decimal("0.7")


def _validate_atr_inputs(entry_price: Decimal, atr: Decimal, multiple: Decimal) -> None:
    """Validate ATR stop price inputs.

    Args:
        entry_price: Position entry price.
        atr: Average True Range value.
        multiple: ATR multiplier.

    Raises:
        ConfigError: If any input is invalid.
    """
    if entry_price <= Decimal("0") or atr <= Decimal("0") or multiple <= Decimal("0"):
        msg = "entry_price, atr, and multiple must be positive"
        _LOGGER.error(
            "Invalid atr_stop_price inputs",
            extra={"entry_price": str(entry_price), "atr": str(atr), "multiple": str(multiple)},
        )
        raise ConfigError(msg)


def _calculate_atr_result(
    entry_price: Decimal,
    atr: Decimal,
    side: OrderSide,
    multiple: Decimal,
) -> Decimal:
    """Calculate ATR stop price result.

    Args:
        entry_price: Position entry price.
        atr: Average True Range value.
        side: Order side.
        multiple: ATR multiplier.

    Returns:
        Calculated stop price.
    """
    distance = atr * multiple
    if side == OrderSide.BUY:
        return max(Decimal("0"), entry_price - distance)
    return entry_price + distance


def atr_stop_price(
    entry_price: Decimal, atr: Decimal, side: OrderSide, multiple: Decimal = Decimal("2")
) -> Decimal:
    """Calculate ATR-based stop loss price.

    Args:
        entry_price: Position entry price.
        atr: Average True Range value.
        side: Order side (BUY or SELL).
        multiple: ATR multiplier (default: 2).

    Returns:
        Stop loss price.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_atr_inputs(entry_price, atr, multiple)
    result = _calculate_atr_result(entry_price, atr, side, multiple)
    _LOGGER.debug(
        "ATR stop price calculated",
        extra={
            "entry_price": str(entry_price),
            "atr": str(atr),
            "side": side.value,
            "multiple": str(multiple),
            "stop_price": str(result),
        },
    )
    return result


def _validate_trailing_inputs(
    previous_stop: Decimal, current_price: Decimal, trail_fraction: Decimal
) -> None:
    """Validate trailing stop price inputs.

    Args:
        previous_stop: Previous stop loss price.
        current_price: Current market price.
        trail_fraction: Trailing fraction.

    Raises:
        ConfigError: If any input is invalid.
    """
    if previous_stop <= Decimal("0") or current_price <= Decimal("0"):
        msg = "previous_stop and current_price must be positive"
        _LOGGER.error(
            "Invalid trailing_stop_price inputs",
            extra={"previous_stop": str(previous_stop), "current_price": str(current_price)},
        )
        raise ConfigError(msg)
    if trail_fraction <= Decimal("0") or trail_fraction >= Decimal("1"):
        msg = "trail_fraction must be between 0 and 1"
        _LOGGER.error("Invalid trail_fraction", extra={"trail_fraction": str(trail_fraction)})
        raise ConfigError(msg)


def _calculate_trailing_result(
    previous_stop: Decimal,
    current_price: Decimal,
    side: OrderSide,
    trail_fraction: Decimal,
) -> tuple[Decimal, Decimal]:
    """Calculate trailing stop price result.

    Args:
        previous_stop: Previous stop loss price.
        current_price: Current market price.
        side: Order side.
        trail_fraction: Trailing fraction.

    Returns:
        Tuple of (candidate, result) stop prices.
    """
    distance = current_price * trail_fraction
    candidate = current_price - distance if side == OrderSide.BUY else current_price + distance
    if side == OrderSide.BUY:
        result = max(previous_stop, candidate)
    else:
        result = min(previous_stop, candidate)
    return candidate, result


def trailing_stop_price(
    previous_stop: Decimal,
    current_price: Decimal,
    side: OrderSide,
    trail_fraction: Decimal = Decimal("0.01"),
) -> Decimal:
    """Calculate trailing stop price.

    Args:
        previous_stop: Previous stop loss price.
        current_price: Current market price.
        side: Order side (BUY or SELL).
        trail_fraction: Trailing fraction (default: 0.01 or 1%).

    Returns:
        New stop loss price (never worse than previous stop).

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_trailing_inputs(previous_stop, current_price, trail_fraction)
    candidate, result = _calculate_trailing_result(
        previous_stop, current_price, side, trail_fraction
    )
    _LOGGER.debug(
        "Trailing stop price calculated",
        extra={
            "previous_stop": str(previous_stop),
            "current_price": str(current_price),
            "side": side.value,
            "trail_fraction": str(trail_fraction),
            "candidate": str(candidate),
            "result": str(result),
        },
    )
    return result


def _validate_time_exit_inputs(
    entry_time_utc: datetime, now_utc: datetime, max_hold_minutes: int
) -> None:
    """Validate time exit inputs.

    Args:
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.

    Raises:
        ConfigError: If any input is invalid.
    """
    if entry_time_utc.tzinfo != UTC or now_utc.tzinfo != UTC:
        msg = "entry_time_utc and now_utc must be timezone-aware UTC datetimes"
        _LOGGER.error(
            "Non-UTC datetime provided to should_time_exit",
            extra={"entry_time_utc": str(entry_time_utc), "now_utc": str(now_utc)},
        )
        raise ConfigError(msg)
    if max_hold_minutes <= 0:
        msg = "max_hold_minutes must be positive"
        _LOGGER.error("Invalid max_hold_minutes", extra={"max_hold_minutes": max_hold_minutes})
        raise ConfigError(msg)


def _log_time_exit_result(
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
    elapsed: timedelta,
    should_exit: bool,
) -> None:
    """Log time exit check result.

    Args:
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.
        elapsed: Elapsed time.
        should_exit: Whether to exit.
    """
    _LOGGER.debug(
        "Time exit check",
        extra={
            "entry_time_utc": str(entry_time_utc),
            "now_utc": str(now_utc),
            "max_hold_minutes": max_hold_minutes,
            "elapsed_minutes": elapsed.total_seconds() / 60,
            "should_exit": should_exit,
        },
    )


def should_time_exit(entry_time_utc: datetime, now_utc: datetime, max_hold_minutes: int) -> bool:
    """Check if position should be exited based on maximum holding time.

    Args:
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.

    Returns:
        True if max holding time exceeded, False otherwise.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_time_exit_inputs(entry_time_utc, now_utc, max_hold_minutes)
    elapsed = now_utc - entry_time_utc
    should_exit = elapsed >= timedelta(minutes=max_hold_minutes)
    _log_time_exit_result(entry_time_utc, now_utc, max_hold_minutes, elapsed, should_exit)
    return should_exit


def _validate_auto_squareoff_input(now_utc: datetime) -> None:
    """Validate auto-squareoff input.

    Args:
        now_utc: Current time (UTC).

    Raises:
        ConfigError: If input is invalid.
    """
    if now_utc.tzinfo != UTC:
        msg = "now_utc must be timezone-aware UTC datetime"
        _LOGGER.error(
            "Non-UTC datetime provided to should_auto_squareoff", extra={"now_utc": str(now_utc)}
        )
        raise ConfigError(msg)


def should_auto_squareoff(now_utc: datetime) -> bool:
    """Check if position should be auto-squared off based on market close time.

    Auto-squareoff triggers at 15:10 IST (09:40 UTC) for safety.

    Args:
        now_utc: Current time (UTC).

    Returns:
        True if auto-squareoff time reached, False otherwise.

    Raises:
        ConfigError: If input is invalid.
    """
    _validate_auto_squareoff_input(now_utc)
    current_time = now_utc.time()
    should_exit = current_time >= _AUTO_SQUAREOFF_UTC_TIME
    _LOGGER.debug(
        "Auto-squareoff check",
        extra={
            "now_utc": str(now_utc),
            "current_time": str(current_time),
            "auto_squareoff_time": str(_AUTO_SQUAREOFF_UTC_TIME),
            "should_exit": should_exit,
        },
    )
    return should_exit


def _validate_drl_exit_inputs(exit_probability: Decimal, threshold: Decimal) -> None:
    """Validate DRL exit inputs.

    Args:
        exit_probability: Probability of positive exit (0-1).
        threshold: Minimum probability threshold.

    Raises:
        ConfigError: If any input is invalid.
    """
    if exit_probability < Decimal("0") or exit_probability > Decimal("1"):
        msg = "exit_probability must be between 0 and 1"
        _LOGGER.error("Invalid exit_probability", extra={"exit_probability": str(exit_probability)})
        raise ConfigError(msg)
    if threshold <= Decimal("0") or threshold >= Decimal("1"):
        msg = "threshold must be between 0 and 1 (exclusive of 1)"
        _LOGGER.error("Invalid threshold", extra={"threshold": str(threshold)})
        raise ConfigError(msg)


def should_drl_exit(
    exit_probability: Decimal,
    threshold: Decimal = _DEFAULT_EXIT_PROB_THRESHOLD,
) -> bool:
    """Check if DRL model predicts favorable exit conditions.

    Args:
        exit_probability: Probability of positive exit (0-1).
        threshold: Minimum probability threshold (default: 0.7).

    Returns:
        True if exit probability exceeds threshold, False otherwise.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_drl_exit_inputs(exit_probability, threshold)
    should_exit = exit_probability >= threshold
    _LOGGER.debug(
        "DRL exit check",
        extra={
            "exit_probability": str(exit_probability),
            "threshold": str(threshold),
            "should_exit": should_exit,
        },
    )
    return should_exit


def _check_stop_loss_hit(
    current_price: Decimal, stop_price: Decimal, side: OrderSide
) -> tuple[bool, str | None]:
    """Check if stop loss has been hit.

    Args:
        current_price: Current market price.
        stop_price: Stop loss price.
        side: Order side.

    Returns:
        Tuple of (hit, reason) or (False, None) if not hit.
    """
    stop_hit = (
        (current_price <= stop_price) if side == OrderSide.BUY else (current_price >= stop_price)
    )
    if stop_hit:
        _LOGGER.warning(
            "Stop loss hit",
            extra={
                "current_price": str(current_price),
                "stop_price": str(stop_price),
                "side": side.value,
            },
        )
        return True, "stop_loss_hit"
    return False, None


def _validate_composite_inputs(
    entry_time_utc: datetime,
    now_utc: datetime,
) -> None:
    """Validate datetime inputs for composite exit signal.

    Args:
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).

    Raises:
        ConfigError: If datetimes are not UTC-aware.
    """
    if now_utc.tzinfo != UTC or entry_time_utc.tzinfo != UTC:
        msg = "All datetimes must be timezone-aware UTC"
        _LOGGER.error(
            "Non-UTC datetime in composite exit signal",
            extra={"entry_time_utc": str(entry_time_utc), "now_utc": str(now_utc)},
        )
        raise ConfigError(msg)


def _log_composite_signal_context(
    current_price: Decimal,
    stop_price: Decimal,
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
    exit_probability: Decimal | None,
    exit_prob_threshold: Decimal,
    side: OrderSide,
) -> None:
    """Log context for composite exit signal calculation.

    Args:
        current_price: Current market price.
        stop_price: Stop loss price.
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.
        exit_probability: DRL-predicted exit probability.
        exit_prob_threshold: DRL exit probability threshold.
        side: Order side.
    """
    _LOGGER.info(
        "Calculating composite exit signal",
        extra={
            "current_price": str(current_price),
            "stop_price": str(stop_price),
            "entry_time_utc": str(entry_time_utc),
            "now_utc": str(now_utc),
            "max_hold_minutes": max_hold_minutes,
            "exit_probability": str(exit_probability) if exit_probability else None,
            "exit_prob_threshold": str(exit_prob_threshold),
            "side": side.value,
        },
    )


def _handle_auto_squareoff_exit(now_utc: datetime) -> tuple[bool, str | None]:
    """Handle auto-squareoff exit check.

    Args:
        now_utc: Current time (UTC).

    Returns:
        Tuple of (should_exit, reason) or (False, None) if no exit.
    """
    if should_auto_squareoff(now_utc):
        _LOGGER.warning(
            "Auto-squareoff triggered at 15:10 IST",
            extra={"now_utc": str(now_utc)},
        )
        return True, "auto_squareoff"
    return False, None


def _handle_time_exit(
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
) -> tuple[bool, str | None]:
    """Handle time-based exit check.

    Args:
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.

    Returns:
        Tuple of (should_exit, reason) or (False, None) if no exit.
    """
    if should_time_exit(entry_time_utc, now_utc, max_hold_minutes):
        elapsed = (now_utc - entry_time_utc).total_seconds() / 60
        _LOGGER.warning(
            "Maximum holding time exceeded",
            extra={"elapsed_minutes": elapsed, "max_hold_minutes": max_hold_minutes},
        )
        return True, "max_hold_time"
    return False, None


def _handle_drl_exit(
    exit_probability: Decimal | None,
    exit_prob_threshold: Decimal,
) -> tuple[bool, str | None]:
    """Handle DRL-predicted exit check.

    Args:
        exit_probability: DRL-predicted exit probability.
        exit_prob_threshold: DRL exit probability threshold.

    Returns:
        Tuple of (should_exit, reason) or (False, None) if no exit.
    """
    if exit_probability is not None and should_drl_exit(exit_probability, exit_prob_threshold):
        _LOGGER.info(
            "DRL positive exit signal",
            extra={
                "exit_probability": str(exit_probability),
                "threshold": str(exit_prob_threshold),
            },
        )
        return True, "drl_positive_exit"
    return False, None


def _perform_exit_checks(
    current_price: Decimal,
    stop_price: Decimal,
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
    exit_probability: Decimal | None,
    exit_prob_threshold: Decimal,
    side: OrderSide,
) -> tuple[bool, str | None]:
    """Perform all exit checks in priority order.

    Args:
        current_price: Current market price.
        stop_price: Stop loss price.
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.
        exit_probability: DRL-predicted exit probability.
        exit_prob_threshold: DRL exit probability threshold.
        side: Order side.

    Returns:
        Tuple of (should_exit, reason) or (False, None) if no exit.
    """
    # Check 1: Stop loss hit
    hit, reason = _check_stop_loss_hit(current_price, stop_price, side)
    if hit:
        return True, reason
    # Check 2: Auto-squareoff at 15:10 IST
    hit, reason = _handle_auto_squareoff_exit(now_utc)
    if hit:
        return True, reason
    # Check 3: Maximum holding time exceeded
    hit, reason = _handle_time_exit(entry_time_utc, now_utc, max_hold_minutes)
    if hit:
        return True, reason
    # Check 4: DRL-predicted positive exit
    return _handle_drl_exit(exit_probability, exit_prob_threshold)


def _validate_and_log_composite(
    current_price: Decimal,
    stop_price: Decimal,
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
    exit_probability: Decimal | None,
    exit_prob_threshold: Decimal,
    side: OrderSide,
) -> None:
    """Validate inputs and log composite signal context.

    Args:
        current_price: Current market price.
        stop_price: Stop loss price.
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.
        exit_probability: DRL-predicted exit probability.
        exit_prob_threshold: DRL exit probability threshold.
        side: Order side.

    Raises:
        ConfigError: If datetimes are not UTC-aware.
    """
    _validate_composite_inputs(entry_time_utc, now_utc)
    _log_composite_signal_context(
        current_price,
        stop_price,
        entry_time_utc,
        now_utc,
        max_hold_minutes,
        exit_probability,
        exit_prob_threshold,
        side,
    )


def _format_exit_result(hit: bool, reason: str | None) -> tuple[bool, str]:
    """Format the final exit result.

    Args:
        hit: Whether an exit was triggered.
        reason: The exit reason (if any).

    Returns:
        Tuple of (should_exit, reason).
    """
    if hit:
        return True, reason if reason is not None else "unknown_reason"
    _LOGGER.debug("No exit signal triggered")
    return False, "no_exit"


def calculate_composite_exit_signal(
    current_price: Decimal,
    stop_price: Decimal,
    entry_time_utc: datetime,
    now_utc: datetime,
    max_hold_minutes: int,
    exit_probability: Decimal | None = None,
    exit_prob_threshold: Decimal = _DEFAULT_EXIT_PROB_THRESHOLD,
    side: OrderSide = OrderSide.BUY,
) -> tuple[bool, str]:
    """Calculate composite exit signal combining multiple risk controls.

    Checks stop loss hit, time-based exit, auto-squareoff, and DRL prediction.

    Args:
        current_price: Current market price.
        stop_price: Stop loss price to check.
        entry_time_utc: Position entry time (UTC).
        now_utc: Current time (UTC).
        max_hold_minutes: Maximum holding time in minutes.
        exit_probability: DRL-predicted exit probability (optional).
        exit_prob_threshold: DRL exit probability threshold (default: 0.7).
        side: Order side (BUY or SELL).

    Returns:
        Tuple of (should_exit, reason) where reason explains why exit triggered.

    Raises:
        ConfigError: If any input is invalid.
    """
    _validate_and_log_composite(
        current_price,
        stop_price,
        entry_time_utc,
        now_utc,
        max_hold_minutes,
        exit_probability,
        exit_prob_threshold,
        side,
    )
    hit, reason = _perform_exit_checks(
        current_price,
        stop_price,
        entry_time_utc,
        now_utc,
        max_hold_minutes,
        exit_probability,
        exit_prob_threshold,
        side,
    )
    return _format_exit_result(hit, reason)
