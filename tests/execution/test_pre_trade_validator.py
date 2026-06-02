"""Comprehensive tests for pre_trade_validator.py module."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.enums import Exchange, OrderSide, ProductType
from iatb.core.exceptions import ConfigError
from iatb.execution.base import OrderRequest
from iatb.execution.pre_trade_validator import (
    PreTradeConfig,
    _check_exposure,
    _check_market_session,
    _check_notional,
    _check_position_limit,
    _check_price_deviation,
    _check_quantity,
    _resolve_price,
    validate_order,
    validate_order_with_position_limit_guard,
)


def _make_request(
    symbol: str = "NIFTY",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("10"),
    price: Decimal | None = None,
    product_type: ProductType | None = None,
) -> OrderRequest:
    return OrderRequest(
        exchange=Exchange.NSE,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        product_type=product_type,
    )


def _make_config(
    max_order_quantity: Decimal = Decimal("1000"),
    max_order_value: Decimal = Decimal("1000000"),
    max_price_deviation_pct: Decimal = Decimal("0.05"),
    max_position_per_symbol: Decimal = Decimal("5000"),
    max_portfolio_exposure: Decimal = Decimal("5000000"),
) -> PreTradeConfig:
    return PreTradeConfig(
        max_order_quantity=max_order_quantity,
        max_order_value=max_order_value,
        max_price_deviation_pct=max_price_deviation_pct,
        max_position_per_symbol=max_position_per_symbol,
        max_portfolio_exposure=max_portfolio_exposure,
    )


class TestPreTradeConfig:
    def test_valid_config(self) -> None:
        config = _make_config()
        assert config.max_order_quantity == Decimal("1000")

    def test_zero_max_order_quantity_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_order_quantity must be positive"):
            _make_config(max_order_quantity=Decimal("0"))

    def test_negative_max_order_value_raises(self) -> None:
        with pytest.raises(ConfigError, match="max_order_value must be positive"):
            _make_config(max_order_value=Decimal("-1"))

    def test_zero_max_price_deviation_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="max_price_deviation_pct must be positive"
        ):
            _make_config(max_price_deviation_pct=Decimal("0"))

    def test_negative_max_position_per_symbol_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="max_position_per_symbol must be positive"
        ):
            _make_config(max_position_per_symbol=Decimal("-10"))

    def test_negative_max_portfolio_exposure_raises(self) -> None:
        with pytest.raises(
            ConfigError, match="max_portfolio_exposure must be positive"
        ):
            _make_config(max_portfolio_exposure=Decimal("-1"))


class TestResolvePrice:
    def test_uses_request_price(self) -> None:
        request = _make_request(price=Decimal("100"))
        price = _resolve_price(request, {"NIFTY": Decimal("200")})
        assert price == Decimal("100")

    def test_uses_last_price_when_no_request_price(self) -> None:
        request = _make_request()
        price = _resolve_price(request, {"NIFTY": Decimal("200")})
        assert price == Decimal("200")

    def test_raises_when_no_price_available(self) -> None:
        request = _make_request()
        with pytest.raises(ConfigError, match="no valid last price"):
            _resolve_price(request, {})

    def test_raises_when_last_price_zero(self) -> None:
        request = _make_request()
        with pytest.raises(ConfigError, match="no valid last price"):
            _resolve_price(request, {"NIFTY": Decimal("0")})

    def test_raises_when_last_price_negative(self) -> None:
        request = _make_request()
        with pytest.raises(ConfigError, match="no valid last price"):
            _resolve_price(request, {"NIFTY": Decimal("-1")})


class TestCheckQuantity:
    def test_within_limit(self) -> None:
        request = _make_request(quantity=Decimal("100"))
        config = _make_config(max_order_quantity=Decimal("1000"))
        _check_quantity(request, config)

    def test_exceeds_limit_raises(self) -> None:
        request = _make_request(quantity=Decimal("2000"))
        config = _make_config(max_order_quantity=Decimal("1000"))
        with pytest.raises(ConfigError, match="fat-finger"):
            _check_quantity(request, config)

    def test_exact_limit_passes(self) -> None:
        request = _make_request(quantity=Decimal("1000"))
        config = _make_config(max_order_quantity=Decimal("1000"))
        _check_quantity(request, config)


class TestCheckNotional:
    def test_within_limit(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        _check_notional(request, Decimal("100"), _make_config())

    def test_exceeds_limit_raises(self) -> None:
        request = _make_request(quantity=Decimal("10000"))
        with pytest.raises(ConfigError, match="notional"):
            _check_notional(
                request,
                Decimal("1000"),
                _make_config(max_order_value=Decimal("100")),
            )

    def test_exact_limit_passes(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        _check_notional(
            request, Decimal("100"), _make_config(max_order_value=Decimal("1000"))
        )


class TestCheckPriceDeviation:
    def test_within_deviation(self) -> None:
        request = _make_request(price=Decimal("102"))
        last_prices = {"NIFTY": Decimal("100")}
        config = _make_config(max_price_deviation_pct=Decimal("0.05"))
        _check_price_deviation(request, Decimal("102"), last_prices, config)

    def test_exceeds_deviation_raises(self) -> None:
        request = _make_request(price=Decimal("110"))
        last_prices = {"NIFTY": Decimal("100")}
        config = _make_config(max_price_deviation_pct=Decimal("0.05"))
        with pytest.raises(ConfigError, match="price deviation"):
            _check_price_deviation(request, Decimal("110"), last_prices, config)

    def test_no_last_price_skips_check(self) -> None:
        request = _make_request(price=Decimal("999"))
        config = _make_config()
        _check_price_deviation(request, Decimal("999"), {}, config)

    def test_zero_last_price_skips_check(self) -> None:
        request = _make_request(price=Decimal("999"))
        config = _make_config()
        _check_price_deviation(request, Decimal("999"), {"NIFTY": Decimal("0")}, config)

    def test_negative_last_price_skips_check(self) -> None:
        request = _make_request(price=Decimal("999"))
        config = _make_config()
        _check_price_deviation(
            request, Decimal("999"), {"NIFTY": Decimal("-1")}, config
        )


class TestCheckPositionLimit:
    def test_within_limit(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        positions = {"NIFTY": Decimal("100")}
        config = _make_config(max_position_per_symbol=Decimal("5000"))
        _check_position_limit(request, positions, config)

    def test_exceeds_limit_raises(self) -> None:
        request = _make_request(quantity=Decimal("101"))
        positions = {"NIFTY": Decimal("4900")}
        config = _make_config(max_position_per_symbol=Decimal("5000"))
        with pytest.raises(ConfigError, match="position"):
            _check_position_limit(request, positions, config)

    def test_no_existing_position(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        config = _make_config(max_position_per_symbol=Decimal("5000"))
        _check_position_limit(request, {}, config)

    def test_negative_existing_position(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        positions = {"NIFTY": Decimal("-100")}
        config = _make_config(max_position_per_symbol=Decimal("5000"))
        _check_position_limit(request, positions, config)


class TestCheckExposure:
    def test_within_exposure(self) -> None:
        request = _make_request(quantity=Decimal("10"))
        config = _make_config()
        _check_exposure(request, Decimal("100"), Decimal("1000"), config)

    def test_exceeds_exposure_raises(self) -> None:
        request = _make_request(quantity=Decimal("100"))
        config = _make_config(max_portfolio_exposure=Decimal("100"))
        with pytest.raises(ConfigError, match="exposure"):
            _check_exposure(request, Decimal("100"), Decimal("1000"), config)


class TestCheckMarketSession:
    """Tests for Gate 6: Market session validation."""

    def test_during_regular_session_passes(self) -> None:
        """09:30 IST = 04:00 UTC -> within session, should pass."""
        now_utc = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
        request = _make_request()
        _check_market_session(request, now_utc)  # Should not raise

    def test_at_session_start_passes(self) -> None:
        """09:15 IST = 03:45 UTC -> session start, should pass."""
        now_utc = datetime(2026, 1, 2, 3, 45, tzinfo=UTC)
        request = _make_request()
        _check_market_session(request, now_utc)  # Should not raise

    def test_before_session_raises(self) -> None:
        """08:00 IST = 02:30 UTC -> before session, should reject."""
        now_utc = datetime(2026, 1, 2, 2, 30, tzinfo=UTC)
        request = _make_request()
        with pytest.raises(ConfigError, match="outside market session"):
            _check_market_session(request, now_utc)

    def test_after_session_raises(self) -> None:
        """16:00 IST = 10:30 UTC -> after session, should reject."""
        now_utc = datetime(2026, 1, 2, 10, 30, tzinfo=UTC)
        request = _make_request()
        with pytest.raises(ConfigError, match="outside market session"):
            _check_market_session(request, now_utc)

    def test_cnc_pre_open_passes(self) -> None:
        """09:05 IST = 03:35 UTC -> pre-open, CNC allowed."""
        now_utc = datetime(2026, 1, 2, 3, 35, tzinfo=UTC)
        request = _make_request(product_type=ProductType.CNC)
        _check_market_session(request, now_utc)  # Should not raise

    def test_non_cnc_pre_open_raises(self) -> None:
        """09:05 IST = 03:35 UTC -> pre-open, MIS not allowed."""
        now_utc = datetime(2026, 1, 2, 3, 35, tzinfo=UTC)
        request = _make_request(product_type=ProductType.MIS)
        with pytest.raises(ConfigError, match="outside market session"):
            _check_market_session(request, now_utc)

    def test_mis_last_15_min_raises(self) -> None:
        """15:20 IST = 09:50 UTC -> last 15 min, MIS not allowed."""
        now_utc = datetime(2026, 1, 2, 9, 50, tzinfo=UTC)
        request = _make_request(product_type=ProductType.MIS)
        with pytest.raises(ConfigError, match="MIS order rejected"):
            _check_market_session(request, now_utc)

    def test_nrml_last_15_min_passes(self) -> None:
        """15:20 IST = 09:50 UTC -> last 15 min, NRML allowed."""
        now_utc = datetime(2026, 1, 2, 9, 50, tzinfo=UTC)
        request = _make_request(product_type=ProductType.NRML)
        _check_market_session(request, now_utc)  # Should not raise

    def test_none_utc_raises(self) -> None:
        """Naive datetime should raise ConfigError."""
        now_naive = datetime(2026, 1, 2, 4, 0)  # No tzinfo
        request = _make_request()
        with pytest.raises(ConfigError, match="timezone-aware"):
            _check_market_session(request, now_naive)

    def test_midnight_raises(self) -> None:
        """00:00 IST = 18:30 UTC previous day -> outside session."""
        now_utc = datetime(2026, 1, 2, 18, 30, tzinfo=UTC)
        request = _make_request()
        with pytest.raises(ConfigError, match="outside market session"):
            _check_market_session(request, now_utc)


class TestValidateOrder:
    def test_valid_order_passes(self) -> None:
        request = _make_request(quantity=Decimal("10"), price=Decimal("100"))
        config = _make_config()
        last_prices = {"NIFTY": Decimal("100")}
        positions: dict[str, Decimal] = {}
        now_utc = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
        result = validate_order(
            request, config, last_prices, positions, Decimal("0"), now_utc=now_utc
        )
        assert result is request

    def test_fat_finger_rejected(self) -> None:
        request = _make_request(quantity=Decimal("10000"))
        config = _make_config(max_order_quantity=Decimal("100"))
        with pytest.raises(ConfigError, match="fat-finger"):
            validate_order(
                request,
                config,
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )

    def test_notional_rejected(self) -> None:
        request = _make_request(quantity=Decimal("10000"), price=Decimal("100"))
        config = _make_config(
            max_order_quantity=Decimal("20000"),
            max_order_value=Decimal("100"),
        )
        with pytest.raises(ConfigError, match="notional"):
            validate_order(
                request,
                config,
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )

    def test_position_limit_rejected(self) -> None:
        request = _make_request(quantity=Decimal("1000"))
        config = _make_config(max_position_per_symbol=Decimal("500"))
        with pytest.raises(ConfigError, match="position"):
            validate_order(
                request,
                config,
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )

    def test_exposure_rejected(self) -> None:
        request = _make_request(quantity=Decimal("100"), price=Decimal("100"))
        config = _make_config(max_portfolio_exposure=Decimal("50"))
        with pytest.raises(ConfigError, match="exposure"):
            validate_order(
                request,
                config,
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )

    def test_no_last_price_raises(self) -> None:
        request = _make_request()
        config = _make_config()
        with pytest.raises(ConfigError, match="no valid last price"):
            validate_order(
                request,
                config,
                {},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )

    @pytest.mark.enable_market_session
    def test_outside_market_session_rejected(self) -> None:
        """Validate_order should reject orders outside market session."""
        request = _make_request(quantity=Decimal("10"), price=Decimal("100"))
        config = _make_config()
        with pytest.raises(ConfigError, match="outside market session"):
            validate_order(
                request,
                config,
                {"NIFTY": Decimal("100")},
                {},
                Decimal("0"),
                now_utc=datetime(2026, 1, 2, 2, 30, tzinfo=UTC),
            )


class TestValidateOrderWithPositionLimitGuard:
    def test_calls_position_limit_guard(self) -> None:
        request = _make_request(quantity=Decimal("10"), price=Decimal("100"))
        config = _make_config()
        last_prices = {"NIFTY": Decimal("100")}
        mock_guard = MagicMock()
        mock_guard.validate_order = MagicMock()
        now_utc = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
        validate_order_with_position_limit_guard(
            request=request,
            config=config,
            last_prices=last_prices,
            current_positions={},
            total_exposure=Decimal("0"),
            position_limit_guard=mock_guard,
            exchange="nse_fo",
            now_utc=now_utc,
        )
        mock_guard.validate_order.assert_called_once()
        call_kwargs = mock_guard.validate_order.call_args[1]
        assert call_kwargs["exchange"] == "nse_fo"
        assert call_kwargs["symbol"] == "NIFTY"
        assert call_kwargs["quantity"] == Decimal("10")
        assert call_kwargs["price"] == Decimal("100")
        assert call_kwargs["now_utc"] == now_utc

    def test_uses_explicit_price(self) -> None:
        request = _make_request(quantity=Decimal("10"), price=Decimal("200"))
        config = _make_config()
        last_prices = {"NIFTY": Decimal("150")}
        mock_guard = MagicMock()
        mock_guard.validate_order = MagicMock()
        validate_order_with_position_limit_guard(
            request=request,
            config=config,
            last_prices=last_prices,
            current_positions={},
            total_exposure=Decimal("0"),
            position_limit_guard=mock_guard,
            exchange="nse_fo",
            price=Decimal("150"),
            now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
        )
        call_kwargs = mock_guard.validate_order.call_args[1]
        assert call_kwargs["price"] == Decimal("150")

    def test_guard_validation_failure_propagates(self) -> None:
        request = _make_request(quantity=Decimal("10"), price=Decimal("100"))
        config = _make_config()
        last_prices = {"NIFTY": Decimal("100")}
        mock_guard = MagicMock()
        mock_guard.validate_order.side_effect = ConfigError("position limit exceeded")
        with pytest.raises(ConfigError, match="position limit exceeded"):
            validate_order_with_position_limit_guard(
                request=request,
                config=config,
                last_prices=last_prices,
                current_positions={},
                total_exposure=Decimal("0"),
                position_limit_guard=mock_guard,
                exchange="nse_fo",
                now_utc=datetime(2026, 1, 2, 4, 0, tzinfo=UTC),
            )
