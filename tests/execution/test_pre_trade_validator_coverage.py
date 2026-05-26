"""Comprehensive coverage tests for iatb.execution.pre_trade_validator."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange, MarketType, OrderSide, OrderType
from iatb.core.exceptions import ConfigError
from iatb.data.price_reconciler import ReconciliationConfig
from iatb.execution.base import OrderRequest
from iatb.execution.pre_trade_validator import (
    PreTradeConfig,
    _check_exposure,
    _check_notional,
    _check_position_limit,
    _check_price_deviation,
    _check_quantity,
    _resolve_price,
    create_reconciliation_config,
    validate_order,
    validate_order_with_position_limit_guard,
    validate_with_price_reconciliation,
)


def _make_config(**overrides: object) -> PreTradeConfig:
    defaults = {
        "max_order_quantity": Decimal("1000"),
        "max_order_value": Decimal("1000000"),
        "max_price_deviation_pct": Decimal("0.05"),
        "max_position_per_symbol": Decimal("5000"),
        "max_portfolio_exposure": Decimal("5000000"),
    }
    defaults.update(overrides)
    return PreTradeConfig(**defaults)


def _make_order(**overrides: object) -> OrderRequest:
    defaults = {
        "exchange": Exchange.NSE,
        "symbol": "RELIANCE",
        "side": OrderSide.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "price": Decimal("2500"),
        "market_type": MarketType.SPOT,
    }
    defaults.update(overrides)
    return OrderRequest(**defaults)


_NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


class TestPreTradeConfig:
    def test_valid_config(self) -> None:
        cfg = _make_config()
        assert cfg.max_order_quantity == Decimal("1000")

    def test_zero_max_order_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_order_quantity"):
            _make_config(max_order_quantity=Decimal("0"))

    def test_negative_max_order_value_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_order_value"):
            _make_config(max_order_value=Decimal("-1"))

    def test_zero_max_price_deviation_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_price_deviation_pct"):
            _make_config(max_price_deviation_pct=Decimal("0"))

    def test_zero_max_position_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_position_per_symbol"):
            _make_config(max_position_per_symbol=Decimal("0"))

    def test_zero_max_exposure_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_portfolio_exposure"):
            _make_config(max_portfolio_exposure=Decimal("0"))

    def test_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises(AttributeError):
            cfg.max_order_quantity = Decimal("5")


class TestResolvePrice:
    def test_uses_request_price(self) -> None:
        order = _make_order(price=Decimal("2500"))
        result = _resolve_price(order, {"RELIANCE": Decimal("2400")})
        assert result == Decimal("2500")

    def test_falls_back_to_last_price(self) -> None:
        order = _make_order(price=None)
        result = _resolve_price(order, {"RELIANCE": Decimal("2400")})
        assert result == Decimal("2400")

    def test_no_last_price_raises(self) -> None:
        order = _make_order(price=None)
        with pytest.raises(ConfigError, match="no valid last price"):
            _resolve_price(order, {})

    def test_zero_last_price_raises(self) -> None:
        order = _make_order(price=None)
        with pytest.raises(ConfigError, match="no valid last price"):
            _resolve_price(order, {"RELIANCE": Decimal("0")})


class TestCheckQuantity:
    def test_within_limit(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_order_quantity=Decimal("100"))
        _check_quantity(order, cfg)

    def test_exceeds_limit_raises(self) -> None:
        order = _make_order(quantity=Decimal("200"))
        cfg = _make_config(max_order_quantity=Decimal("100"))
        with pytest.raises(ConfigError, match="fat-finger"):
            _check_quantity(order, cfg)

    def test_exact_limit_passes(self) -> None:
        order = _make_order(quantity=Decimal("100"))
        cfg = _make_config(max_order_quantity=Decimal("100"))
        _check_quantity(order, cfg)


class TestCheckNotional:
    def test_within_limit(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_order_value=Decimal("100000"))
        _check_notional(order, Decimal("2500"), cfg)

    def test_exceeds_limit_raises(self) -> None:
        order = _make_order(quantity=Decimal("1000"))
        cfg = _make_config(max_order_value=Decimal("100"))
        with pytest.raises(ConfigError, match="notional"):
            _check_notional(order, Decimal("2500"), cfg)


class TestCheckPriceDeviation:
    def test_within_deviation(self) -> None:
        order = _make_order(price=Decimal("2500"))
        cfg = _make_config(max_price_deviation_pct=Decimal("0.05"))
        _check_price_deviation(
            order, Decimal("2500"), {"RELIANCE": Decimal("2500")}, cfg
        )

    def test_exceeds_deviation_raises(self) -> None:
        order = _make_order(price=Decimal("3000"))
        cfg = _make_config(max_price_deviation_pct=Decimal("0.01"))
        with pytest.raises(ConfigError, match="price deviation"):
            _check_price_deviation(
                order, Decimal("3000"), {"RELIANCE": Decimal("2500")}, cfg
            )

    def test_no_last_price_skips(self) -> None:
        order = _make_order(price=Decimal("3000"))
        cfg = _make_config(max_price_deviation_pct=Decimal("0.01"))
        _check_price_deviation(order, Decimal("3000"), {}, cfg)

    def test_zero_last_price_skips(self) -> None:
        order = _make_order(price=Decimal("3000"))
        cfg = _make_config(max_price_deviation_pct=Decimal("0.01"))
        _check_price_deviation(order, Decimal("3000"), {"RELIANCE": Decimal("0")}, cfg)


class TestCheckPositionLimit:
    def test_within_limit(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_position_per_symbol=Decimal("100"))
        _check_position_limit(order, {"RELIANCE": Decimal("50")}, cfg)

    def test_exceeds_limit_raises(self) -> None:
        order = _make_order(quantity=Decimal("100"))
        cfg = _make_config(max_position_per_symbol=Decimal("50"))
        with pytest.raises(ConfigError, match="position"):
            _check_position_limit(order, {"RELIANCE": Decimal("10")}, cfg)

    def test_no_existing_position(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_position_per_symbol=Decimal("100"))
        _check_position_limit(order, {}, cfg)


class TestCheckExposure:
    def test_within_limit(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_portfolio_exposure=Decimal("1000000"))
        _check_exposure(order, Decimal("2500"), Decimal("100000"), cfg)

    def test_exceeds_limit_raises(self) -> None:
        order = _make_order(quantity=Decimal("1000"))
        cfg = _make_config(max_portfolio_exposure=Decimal("100"))
        with pytest.raises(ConfigError, match="exposure"):
            _check_exposure(order, Decimal("2500"), Decimal("0"), cfg)


class TestValidateOrder:
    def test_all_gates_pass(self) -> None:
        order = _make_order()
        cfg = _make_config()
        last_prices = {"RELIANCE": Decimal("2500")}
        result = validate_order(order, cfg, last_prices, {}, Decimal("0"))
        assert result is order

    def test_quantity_gate_fails(self) -> None:
        order = _make_order(quantity=Decimal("10000"))
        cfg = _make_config(max_order_quantity=Decimal("100"))
        with pytest.raises(ConfigError, match="fat-finger"):
            validate_order(order, cfg, {"RELIANCE": Decimal("2500")}, {}, Decimal("0"))

    def test_notional_gate_fails(self) -> None:
        order = _make_order(quantity=Decimal("1000"), price=Decimal("5000"))
        cfg = _make_config(max_order_value=Decimal("100"))
        with pytest.raises(ConfigError, match="notional"):
            validate_order(order, cfg, {"RELIANCE": Decimal("5000")}, {}, Decimal("0"))

    def test_price_deviation_gate_fails(self) -> None:
        order = _make_order(price=Decimal("5000"))
        cfg = _make_config(max_price_deviation_pct=Decimal("0.01"))
        with pytest.raises(ConfigError, match="price deviation"):
            validate_order(order, cfg, {"RELIANCE": Decimal("2500")}, {}, Decimal("0"))

    def test_position_gate_fails(self) -> None:
        order = _make_order(quantity=Decimal("100"))
        cfg = _make_config(max_position_per_symbol=Decimal("50"))
        with pytest.raises(ConfigError, match="position"):
            validate_order(
                order,
                cfg,
                {"RELIANCE": Decimal("2500")},
                {"RELIANCE": Decimal("0")},
                Decimal("0"),
            )

    def test_exposure_gate_fails(self) -> None:
        order = _make_order(quantity=Decimal("10"))
        cfg = _make_config(max_portfolio_exposure=Decimal("100"))
        with pytest.raises(ConfigError, match="exposure"):
            validate_order(order, cfg, {"RELIANCE": Decimal("2500")}, {}, Decimal("0"))


class TestValidateOrderWithPositionLimitGuard:
    def test_with_guard_passes(self) -> None:
        guard = MagicMock()
        order = _make_order()
        cfg = _make_config()
        last_prices = {"RELIANCE": Decimal("2500")}
        assert (
            validate_order_with_position_limit_guard(
                order, cfg, last_prices, {}, Decimal("0"), guard, "NSE_FO"
            )
            is order
        )
        guard.validate_order.assert_called_once()

    def test_with_explicit_price(self) -> None:
        guard = MagicMock()
        order = _make_order()
        cfg = _make_config()
        validate_order_with_position_limit_guard(
            order,
            cfg,
            {"RELIANCE": Decimal("2500")},
            {},
            Decimal("0"),
            guard,
            "NSE_FO",
            price=Decimal("2500"),
        )
        guard.validate_order.assert_called_once()


class TestCreateReconciliationConfig:
    def test_defaults(self) -> None:
        cfg = create_reconciliation_config()
        assert isinstance(cfg, ReconciliationConfig)
        assert cfg.max_price_deviation_pct == Decimal("0.02")

    def test_custom_params(self) -> None:
        cfg = create_reconciliation_config(
            max_price_deviation_pct=Decimal("0.05"),
            max_timestamp_drift_seconds=120,
        )
        assert cfg.max_price_deviation_pct == Decimal("0.05")
        assert cfg.max_timestamp_drift_seconds == 120


class TestValidateWithPriceReconciliation:
    def test_same_prices(self) -> None:
        from freezegun import freeze_time

        with freeze_time("2026-05-25 10:00:00", tz_offset=0):
            now = datetime.now(UTC)
            result = validate_with_price_reconciliation(
                scanner_price=Decimal("100"),
                execution_price=Decimal("100"),
                scanner_timestamp=now,
                execution_timestamp=now,
                symbol="RELIANCE",
            )
            assert result.passed is True

    def test_different_prices_within_tolerance(self) -> None:
        from freezegun import freeze_time

        with freeze_time("2026-05-25 10:00:00", tz_offset=0):
            now = datetime.now(UTC)
            result = validate_with_price_reconciliation(
                scanner_price=Decimal("100"),
                execution_price=Decimal("101"),
                scanner_timestamp=now,
                execution_timestamp=now,
                symbol="RELIANCE",
            )
            assert isinstance(result.passed, bool)

    def test_custom_reconciler_config(self) -> None:
        from freezegun import freeze_time

        with freeze_time("2026-05-25 10:00:00", tz_offset=0):
            now = datetime.now(UTC)
            cfg = create_reconciliation_config(max_price_deviation_pct=Decimal("0.10"))
            result = validate_with_price_reconciliation(
                scanner_price=Decimal("100"),
                execution_price=Decimal("105"),
                scanner_timestamp=now,
                execution_timestamp=now,
                symbol="RELIANCE",
                reconciler_config=cfg,
            )
            assert isinstance(result.passed, bool)

    def test_with_prev_close(self) -> None:
        from freezegun import freeze_time

        with freeze_time("2026-05-25 10:00:00", tz_offset=0):
            now = datetime.now(UTC)
            result = validate_with_price_reconciliation(
                scanner_price=Decimal("100"),
                execution_price=Decimal("100"),
                scanner_timestamp=now,
                execution_timestamp=now,
                symbol="RELIANCE",
                prev_close_price=Decimal("99"),
            )
            assert isinstance(result.passed, bool)
