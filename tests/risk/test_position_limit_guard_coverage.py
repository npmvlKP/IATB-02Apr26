"""Comprehensive coverage tests for iatb.risk.position_limit_guard."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.core.observability.alerting import AlertLevel, MultiChannelAlertManager
from iatb.risk.position_limit_guard import (
    ExchangeType,
    PositionLimitConfig,
    PositionLimitGuard,
    PositionState,
    create_default_limits,
)


def _now() -> datetime:
    return datetime(2024, 6, 1, 10, 0, tzinfo=UTC)


def _nse_config() -> PositionLimitConfig:
    return PositionLimitConfig(
        exchange=ExchangeType.NSE_FO,
        max_quantity_per_symbol=Decimal("100"),
        max_notional_per_symbol=Decimal("1000000"),
        max_total_notional=Decimal("5000000"),
        alert_threshold_pct=Decimal("0.8"),
    )


class TestExchangeType:
    def test_values(self) -> None:
        assert ExchangeType.NSE_FO.value == "NSE_FO"
        assert ExchangeType.MCX.value == "MCX"
        assert ExchangeType.CDS.value == "CDS"
        assert ExchangeType.NSE_EQ.value == "NSE_EQ"
        assert ExchangeType.BSE_EQ.value == "BSE_EQ"


class TestPositionLimitConfig:
    def test_valid_creation(self) -> None:
        config = _nse_config()
        assert config.exchange == ExchangeType.NSE_FO
        assert config.max_quantity_per_symbol == Decimal("100")

    def test_zero_quantity_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="max_quantity_per_symbol must be positive"
        ):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("0"),
                max_notional_per_symbol=Decimal("1000000"),
                max_total_notional=Decimal("5000000"),
            )

    def test_zero_notional_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="max_notional_per_symbol must be positive"
        ):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("100"),
                max_notional_per_symbol=Decimal("0"),
                max_total_notional=Decimal("5000000"),
            )

    def test_zero_total_notional_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_total_notional must be positive"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("100"),
                max_notional_per_symbol=Decimal("1000000"),
                max_total_notional=Decimal("0"),
            )

    def test_zero_alert_threshold_raises(self) -> None:
        with pytest.raises(ConfigError, match="alert_threshold_pct must be in"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("100"),
                max_notional_per_symbol=Decimal("1000000"),
                max_total_notional=Decimal("5000000"),
                alert_threshold_pct=Decimal("0"),
            )

    def test_alert_threshold_over_one_raises(self) -> None:
        with pytest.raises(ConfigError, match="alert_threshold_pct must be in"):
            PositionLimitConfig(
                exchange=ExchangeType.NSE_FO,
                max_quantity_per_symbol=Decimal("100"),
                max_notional_per_symbol=Decimal("1000000"),
                max_total_notional=Decimal("5000000"),
                alert_threshold_pct=Decimal("1.5"),
            )

    def test_alert_threshold_exactly_one_ok(self) -> None:
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("100"),
            max_notional_per_symbol=Decimal("1000000"),
            max_total_notional=Decimal("5000000"),
            alert_threshold_pct=Decimal("1"),
        )
        assert config.alert_threshold_pct == Decimal("1")

    def test_frozen(self) -> None:
        config = _nse_config()
        with pytest.raises(AttributeError):
            config.exchange = ExchangeType.MCX  # type: ignore[misc]


class TestPositionLimitGuard:
    def test_empty_limits_raises(self) -> None:
        with pytest.raises(ConfigError, match="limits cannot be empty"):
            PositionLimitGuard([])

    def test_duplicate_exchange_raises(self) -> None:
        config = _nse_config()
        with pytest.raises(ConfigError, match="duplicate limit"):
            PositionLimitGuard([config, config])

    def test_validate_order_passes(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        state = guard.validate_order(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        assert state.symbol == "RELIANCE"

    def test_validate_order_zero_price_raises(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="no valid last price"):
            guard.validate_order(
                ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("0"), _now()
            )

    def test_validate_order_quantity_limit_breach(self) -> None:
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("10"),
            max_notional_per_symbol=Decimal("1000000"),
            max_total_notional=Decimal("5000000"),
        )
        guard = PositionLimitGuard([config])
        with pytest.raises(ConfigError, match="quantity.*meets or exceeds"):
            guard.validate_order(
                ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
            )

    def test_validate_order_notional_limit_breach(self) -> None:
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("1000"),
            max_notional_per_symbol=Decimal("1000"),
            max_total_notional=Decimal("5000000"),
        )
        guard = PositionLimitGuard([config])
        with pytest.raises(ConfigError, match="notional.*meets or exceeds"):
            guard.validate_order(
                ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("200"), _now()
            )

    def test_validate_order_exchange_total_breach(self) -> None:
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("1000"),
            max_notional_per_symbol=Decimal("10000000"),
            max_total_notional=Decimal("1000"),
        )
        guard = PositionLimitGuard([config])
        with pytest.raises(ConfigError, match="exchange total notional"):
            guard.validate_order(
                ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("200"), _now()
            )

    def test_validate_order_unconfigured_exchange(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="no position limit configured"):
            guard.validate_order(
                ExchangeType.MCX, "GOLD", Decimal("1"), Decimal("5000"), _now()
            )

    def test_naive_datetime_raises(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="UTC"):
            guard.validate_order(
                ExchangeType.NSE_FO,
                "RELIANCE",
                Decimal("1"),
                Decimal("1000"),
                datetime(2024, 1, 1),
            )

    def test_update_position_buy(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        ps = guard.get_position_state("RELIANCE")
        assert ps is not None
        assert ps.current_quantity == Decimal("10")

    def test_update_position_close_removes(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("-10"), Decimal("1000"), _now()
        )
        assert guard.get_position_state("RELIANCE") is None

    def test_update_position_naive_raises(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="UTC"):
            guard.update_position(
                ExchangeType.NSE_FO,
                "RELIANCE",
                Decimal("10"),
                Decimal("1000"),
                datetime(2024, 1, 1),
            )

    def test_get_limit_config(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        config = guard.get_limit_config(ExchangeType.NSE_FO)
        assert config.exchange == ExchangeType.NSE_FO

    def test_get_limit_config_missing(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="no position limit configured"):
            guard.get_limit_config(ExchangeType.MCX)

    def test_get_position_state_missing(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        assert guard.get_position_state("NOEXIST") is None

    def test_get_exchange_summary(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        summary = guard.get_exchange_summary(ExchangeType.NSE_FO)
        assert "total_notional" in summary
        assert "position_count" in summary

    def test_reset(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        guard.reset(_now())
        assert guard.get_position_state("RELIANCE") is None

    def test_reset_naive_raises(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="UTC"):
            guard.reset(datetime(2024, 1, 1))

    def test_check_alert_thresholds(self) -> None:
        alert_mgr = MagicMock(spec=MultiChannelAlertManager)
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("100"),
            max_notional_per_symbol=Decimal("1000"),
            max_total_notional=Decimal("5000000"),
            alert_threshold_pct=Decimal("0.8"),
        )
        guard = PositionLimitGuard([config], alert_manager=alert_mgr)
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("90"), Decimal("1000"), _now()
        )
        guard._check_alert_thresholds(_now())
        alert_mgr.send_alert.assert_called_once()
        assert alert_mgr.send_alert.call_args[1]["level"] == AlertLevel.WARNING

    def test_check_alert_thresholds_no_alert_when_below(self) -> None:
        alert_mgr = MagicMock(spec=MultiChannelAlertManager)
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("100"),
            max_notional_per_symbol=Decimal("1000000"),
            max_total_notional=Decimal("5000000"),
            alert_threshold_pct=Decimal("0.8"),
        )
        guard = PositionLimitGuard([config], alert_manager=alert_mgr)
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        guard._check_alert_thresholds(_now())
        alert_mgr.send_alert.assert_not_called()

    def test_check_alert_no_manager(self) -> None:
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("100"),
            max_notional_per_symbol=Decimal("1000"),
            max_total_notional=Decimal("5000000"),
            alert_threshold_pct=Decimal("0.8"),
        )
        guard = PositionLimitGuard([config])
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("90"), Decimal("1000"), _now()
        )
        guard._check_alert_thresholds(_now())

    def test_alert_throttle(self) -> None:
        alert_mgr = MagicMock(spec=MultiChannelAlertManager)
        config = PositionLimitConfig(
            exchange=ExchangeType.NSE_FO,
            max_quantity_per_symbol=Decimal("100"),
            max_notional_per_symbol=Decimal("1000"),
            max_total_notional=Decimal("5000000"),
            alert_threshold_pct=Decimal("0.8"),
        )
        guard = PositionLimitGuard([config], alert_manager=alert_mgr)
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("90"), Decimal("1000"), _now()
        )
        guard._check_alert_thresholds(_now())
        guard._check_alert_thresholds(_now())
        assert alert_mgr.send_alert.call_count == 1

    def test_position_count_for_exchange(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        guard.update_position(
            ExchangeType.NSE_FO, "RELIANCE", Decimal("10"), Decimal("1000"), _now()
        )
        guard.update_position(
            ExchangeType.NSE_FO, "TCS", Decimal("10"), Decimal("1000"), _now()
        )
        count = guard._get_position_count_for_exchange(ExchangeType.NSE_FO)
        assert count == 2

    def test_monitoring_interval_zero_raises(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        with pytest.raises(ConfigError, match="interval_seconds must be positive"):
            guard._validate_monitoring_interval(0)

    def test_create_default_limits(self) -> None:
        limits = create_default_limits()
        assert len(limits) == 3
        exchanges = {lim.exchange for lim in limits}
        assert ExchangeType.NSE_FO in exchanges
        assert ExchangeType.MCX in exchanges
        assert ExchangeType.CDS in exchanges

    @pytest.mark.asyncio
    async def test_stop_monitoring_no_task(self) -> None:
        guard = PositionLimitGuard([_nse_config()])
        await guard.stop_monitoring()


class TestPositionState:
    def test_fields(self) -> None:
        ps = PositionState(
            exchange=ExchangeType.NSE_FO,
            symbol="RELIANCE",
            current_quantity=Decimal("10"),
            current_notional=Decimal("10000"),
            limit_quantity=Decimal("100"),
            limit_notional=Decimal("1000000"),
            total_notional_used=Decimal("10000"),
            total_notional_limit=Decimal("5000000"),
        )
        assert ps.symbol == "RELIANCE"
        assert ps.exchange == ExchangeType.NSE_FO
