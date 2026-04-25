"""
Comprehensive tests for SEBI Position Limit Enforcement.

Covers:
- Happy path: normal limit validation and position updates
- Edge cases: boundary conditions, zero values, exact limits
- Error paths: limit breaches, invalid inputs, missing configurations
- Type handling: Decimal precision, UTC datetime validation
- Precision handling: accurate notional calculations
- Timezone handling: UTC-aware datetime requirements
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from iatb.core.exceptions import ConfigError
from iatb.risk.position_limit_guard import (
    ExchangeType,
    PositionLimitConfig,
    PositionLimitGuard,
    create_default_limits,
)


class TestPositionLimitConfig:
    """Test PositionLimitConfig validation."""

    def test_valid_config(self) -> None:
        """Test creating a valid configuration."""
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("10000"),
            max_notional_per_symbol=Decimal("50000000"),
            max_total_notional=Decimal("500000000"),
        )
        assert config.exchange == ExchangeType.NSE_FO
        assert config.max_quantity_per_symbol == Decimal("10000")
        assert config.alert_threshold_pct == Decimal("0.8")

    def test_default_alert_threshold(self) -> None:
        """Test default alert threshold is 80%."""
        config = PositionLimitConfig(
            exchange=ExchangeType.MCX,
            max_quantity_per_symbol=Decimal("1000"),
            max_notional_per_symbol=Decimal("100000000"),
            max_total_notional=Decimal("1000000000"),
        )
        assert config.alert_threshold_pct == Decimal("0.8")

    def test_custom_alert_threshold(self) -> None:
        """Test custom alert threshold."""
        config = PositionLimitConfig(
            exchange=ExchangeType.CDS,
            max_quantity_per_symbol=Decimal("10000"),
            max_notional_per_symbol=Decimal("50000000"),
            max_total_notional=Decimal("200000000"),
            alert_threshold_pct=Decimal("0.9"),
        )
        assert config.alert_threshold_pct == Decimal("0.9")

    def test_invalid_quantity_limit(self) -> None:
        """Test zero or negative quantity limit raises error."""
        with pytest.raises(ConfigError, match="max_quantity_per_symbol must be positive"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("0"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            )

    def test_invalid_notional_limit(self) -> None:
        """Test zero or negative notional limit raises error."""
        with pytest.raises(ConfigError, match="max_notional_per_symbol must be positive"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("-100"),
                max_total_notional=Decimal("500000000"),
            )

    def test_invalid_total_notional_limit(self) -> None:
        """Test zero or negative total notional limit raises error."""
        with pytest.raises(ConfigError, match="max_total_notional must be positive"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("0"),
            )

    def test_invalid_alert_threshold_zero(self) -> None:
        """Test zero alert threshold raises error."""
        with pytest.raises(ConfigError, match="alert_threshold_pct must be in"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
                alert_threshold_pct=Decimal("0"),
            )

    def test_invalid_alert_threshold_exceeds_one(self) -> None:
        """Test alert threshold exceeding 100% raises error."""
        with pytest.raises(ConfigError, match="alert_threshold_pct must be in"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
                alert_threshold_pct=Decimal("1.5"),
            )


class TestPositionLimitGuardInit:
    """Test PositionLimitGuard initialization."""

    def test_init_with_valid_limits(self) -> None:
        """Test initialization with valid limit configurations."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        assert guard.get_limit_config(ExchangeType.NSE_FO) == limits[0]

    def test_init_with_empty_limits(self) -> None:
        """Test initialization with empty limits raises error."""
        with pytest.raises(ConfigError, match="limits cannot be empty"):
            PositionLimitGuard([])

    def test_init_with_duplicate_exchange(self) -> None:
        """Test duplicate exchange configuration raises error."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            ),
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("5000"),
                max_notional_per_symbol=Decimal("25000000"),
                max_total_notional=Decimal("250000000"),
            ),
        ]
        with pytest.raises(ConfigError, match="duplicate limit configuration"):
            PositionLimitGuard(limits)

    def test_init_with_multiple_exchanges(self) -> None:
        """Test initialization with multiple exchanges."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        assert guard.get_limit_config(ExchangeType.NSE_FO) is not None
        assert guard.get_limit_config(ExchangeType.MCX) is not None
        assert guard.get_limit_config(ExchangeType.CDS) is not None


class TestValidateOrder:
    """Test order validation against position limits."""

    def test_validate_order_first_position(self) -> None:
        """Test validating first order for a symbol."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        state = guard.validate_order(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        assert state.symbol == "NIFTY-FUT"
        assert state.current_quantity == Decimal("0")
        assert state.current_notional == Decimal("0")

    def test_validate_order_within_limits(self) -> None:
        """Test validating order within position limits."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        state = guard.validate_order(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity=Decimal("50"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        assert state.current_quantity == Decimal("100")
        assert state.current_notional == Decimal("2000000")

    def test_validate_order_quantity_limit_breach(self) -> None:
        """Test quantity limit breach raises error."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("9999"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        with pytest.raises(ConfigError, match="quantity .* exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("10"),
                price=Decimal("20000"),
                now_utc=now_utc,
            )

    def test_validate_order_notional_limit_breach(self) -> None:
        """Test notional limit breach raises error."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("2499"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        with pytest.raises(ConfigError, match="notional .* exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("1"),
                price=Decimal("20000"),
                now_utc=now_utc,
            )

    def test_validate_order_exchange_total_breach(self) -> None:
        """Test exchange total notional breach raises error."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("10000000"),
                max_total_notional=Decimal("15000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("500"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        with pytest.raises(ConfigError, match="exchange total notional .* exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="BANKNIFTY-FUT",
                quantity=Decimal("300"),
                price=Decimal("20000"),
                now_utc=now_utc,
            )

    def test_validate_order_unconfigured_exchange(self) -> None:
        """Test validation for unconfigured exchange raises error."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("10000000"),
                max_total_notional=Decimal("50000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        with pytest.raises(ConfigError, match="no position limit configured"):
            guard.validate_order(
                exchange=ExchangeType.MCX,
                symbol="CRUDEOIL-FUT",
                quantity=Decimal("100"),
                price=Decimal("5000"),
                now_utc=now_utc,
            )

    def test_validate_order_naive_datetime_raises_error(self) -> None:
        """Test naive datetime raises validation error."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        # Create naive datetime by removing timezone from aware datetime
        now_aware = datetime.now(UTC)
        now_naive = now_aware.replace(tzinfo=None)

        with pytest.raises(ConfigError, match="datetime must be UTC-aware"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("100"),
                price=Decimal("20000"),
                now_utc=now_naive,
            )


class TestUpdatePosition:
    """Test position updates after order fills."""

    def test_update_position_open_long(self) -> None:
        """Test opening a long position."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        state = guard.get_position_state("NIFTY-FUT")
        assert state is not None
        assert state.current_quantity == Decimal("100")
        assert state.current_notional == Decimal("2000000")

    def test_update_position_add_to_long(self) -> None:
        """Test adding to an existing long position."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("50"),
            price=Decimal("20500"),
            now_utc=now_utc,
        )

        state = guard.get_position_state("NIFTY-FUT")
        assert state is not None
        assert state.current_quantity == Decimal("150")
        assert state.current_notional == Decimal("3025000")

    def test_update_position_close_long(self) -> None:
        """Test closing a long position."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("-100"),
            price=Decimal("20500"),
            now_utc=now_utc,
        )

        state = guard.get_position_state("NIFTY-FUT")
        assert state is None

    def test_update_position_naive_datetime_raises_error(self) -> None:
        """Test naive datetime raises error on position update."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        # Create naive datetime by removing timezone from aware datetime
        now_aware = datetime.now(UTC)
        now_naive = now_aware.replace(tzinfo=None)

        with pytest.raises(ConfigError, match="datetime must be UTC-aware"):
            guard.update_position(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity_delta=Decimal("100"),
                price=Decimal("20000"),
                now_utc=now_naive,
            )


class TestPositionState:
    """Test position state queries."""

    def test_get_position_state_exists(self) -> None:
        """Test getting state for existing position."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        state = guard.get_position_state("NIFTY-FUT")
        assert state is not None
        assert state.symbol == "NIFTY-FUT"
        assert state.current_quantity == Decimal("100")
        assert state.exchange == ExchangeType.NSE_FO

    def test_get_position_state_not_exists(self) -> None:
        """Test getting state for non-existent position."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)

        state = guard.get_position_state("NONEXISTENT")
        assert state is None

    def test_get_exchange_summary(self) -> None:
        """Test getting exchange position summary."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        summary = guard.get_exchange_summary(ExchangeType.NSE_FO)
        assert summary["total_notional"] == Decimal("2000000")
        assert summary["position_count"] == Decimal("1")


class TestMonitoring:
    """Test background monitoring and alerting."""

    @pytest.mark.asyncio
    async def test_start_monitoring_task(self) -> None:
        """Test starting monitoring task."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)

        # start_monitoring is async, so we need to await it to get the task
        task = await guard.start_monitoring(interval_seconds=1, check_alerts=False)
        assert isinstance(task, asyncio.Task)

        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def test_start_monitoring_invalid_interval(self) -> None:
        """Test monitoring with invalid interval raises error."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)

        # Call the validation method directly for synchronous testing
        with pytest.raises(ConfigError, match="interval_seconds must be positive"):
            guard._validate_monitoring_interval(interval_seconds=0)


class TestReset:
    """Test guard reset functionality."""

    def test_reset_clears_positions(self) -> None:
        """Test reset clears all positions."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("100"),
            price=Decimal("20000"),
            now_utc=now_utc,
        )

        guard.reset(now_utc)

        state = guard.get_position_state("NIFTY-FUT")
        assert state is None

        summary = guard.get_exchange_summary(ExchangeType.NSE_FO)
        assert summary["total_notional"] == Decimal("0")

    def test_reset_naive_datetime_raises_error(self) -> None:
        """Test reset with naive datetime raises error."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        # Create naive datetime by removing timezone from aware datetime
        now_aware = datetime.now(UTC)
        now_naive = now_aware.replace(tzinfo=None)

        with pytest.raises(ConfigError, match="datetime must be UTC-aware"):
            guard.reset(now_naive)


class TestCreateDefaultLimits:
    """Test default limit creation."""

    def test_create_default_limits_returns_all_exchanges(self) -> None:
        """Test default limits include NSE_FO, MCX, and CDS."""
        limits = create_default_limits()
        assert len(limits) == 3

        exchanges = {limit.exchange for limit in limits}
        assert ExchangeType.NSE_FO in exchanges
        assert ExchangeType.MCX in exchanges
        assert ExchangeType.CDS in exchanges

    def test_default_limits_are_valid(self) -> None:
        """Test all default limits pass validation."""
        limits = create_default_limits()
        for limit in limits:
            assert limit.max_quantity_per_symbol > Decimal("0")
            assert limit.max_notional_per_symbol > Decimal("0")
            assert limit.max_total_notional > Decimal("0")


class TestPrecisionHandling:
    """Test Decimal precision in calculations."""

    def test_notional_calculation_precision(self) -> None:
        """Test notional calculations maintain Decimal precision."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        quantity = Decimal("100.5")
        price = Decimal("20000.75")
        expected_notional = Decimal("2010075.375")

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=quantity,
            price=price,
            now_utc=now_utc,
        )

        state = guard.get_position_state("NIFTY-FUT")
        assert state is not None
        assert state.current_notional == expected_notional

    def test_limit_comparison_precision(self) -> None:
        """Test limit comparisons use exact Decimal precision and reject exact matches."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000.0001"),
                max_notional_per_symbol=Decimal("50000000.0001"),
                max_total_notional=Decimal("500000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        guard.update_position(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity_delta=Decimal("10000"),
            price=Decimal("5000"),
            now_utc=now_utc,
        )

        # Exact match to limit with fractional precision should be rejected
        with pytest.raises(ConfigError, match="quantity .* meets or exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("0.0001"),
                price=Decimal("5000"),
                now_utc=now_utc,
            )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exact_quantity_limit(self) -> None:
        """Test order at exact quantity limit is rejected."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        with pytest.raises(ConfigError, match="quantity .* exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("1000"),
                price=Decimal("100"),
                now_utc=now_utc,
            )

    def test_exact_notional_limit(self) -> None:
        """Test order at exact notional limit is rejected."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("10000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        with pytest.raises(ConfigError, match="notional .* exceeds limit"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("2500"),
                price=Decimal("20000"),
                now_utc=now_utc,
            )

    def test_one_below_limit(self) -> None:
        """Test order one unit below limit is accepted."""
        limits = [
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("1000"),
                max_notional_per_symbol=Decimal("50000000"),
                max_total_notional=Decimal("500000000"),
            )
        ]
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        state = guard.validate_order(
            exchange=ExchangeType.NSE_FO,
            symbol="NIFTY-FUT",
            quantity=Decimal("999"),
            price=Decimal("100"),
            now_utc=now_utc,
        )

        assert state is not None

    def test_zero_price_notional(self) -> None:
        """Test zero price results in zero notional."""
        limits = create_default_limits()
        guard = PositionLimitGuard(limits)
        now_utc = datetime.now(UTC)

        with pytest.raises(ConfigError, match="no valid last price"):
            guard.validate_order(
                exchange=ExchangeType.NSE_FO,
                symbol="NIFTY-FUT",
                quantity=Decimal("100"),
                price=Decimal("0"),
                now_utc=now_utc,
            )
