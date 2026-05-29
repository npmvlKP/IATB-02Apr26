# Tests for Decimal values in observability metrics.
from __future__ import annotations

from decimal import Decimal

from iatb.core.observability.metrics import (
    _decimal_to_prometheus_gauge_value,
    daily_pnl,
    portfolio_value,
    record_trade,
    trade_pnl,
    update_daily_pnl,
    update_portfolio_value,
)


class TestDecimalToPrometheusGaugeValue:
    """Tests for the _decimal_to_prometheus_gauge_value boundary helper."""

    def test_positive_decimal_conversion(self) -> None:
        result = _decimal_to_prometheus_gauge_value(Decimal("100.50"))
        assert result == 100.50
        assert isinstance(result, float)

    def test_negative_decimal_conversion(self) -> None:
        result = _decimal_to_prometheus_gauge_value(Decimal("-250.75"))
        assert result == -250.75
        assert isinstance(result, float)

    def test_zero_decimal_conversion(self) -> None:
        result = _decimal_to_prometheus_gauge_value(Decimal("0"))
        assert result == 0.0
        assert isinstance(result, float)

    def test_high_precision_decimal_conversion(self) -> None:
        result = _decimal_to_prometheus_gauge_value(Decimal("12345.67890"))
        assert abs(result - 12345.67890) < 0.00001
        assert isinstance(result, float)

    def test_integer_decimal_conversion(self) -> None:
        result = _decimal_to_prometheus_gauge_value(Decimal("5000"))
        assert result == 5000.0
        assert isinstance(result, float)


class TestRecordTradeDecimal:
    """Tests for record_trade with Decimal PnL values."""

    def test_record_trade_with_decimal_pnl(self) -> None:
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=Decimal("100.50"),
            ticker="RELIANCE",
        )
        gauge = trade_pnl.labels(exchange="NSE", ticker="RELIANCE")
        assert gauge._value.get() == 100.50  # noqa: PLR2004 – prometheus internal

    def test_record_trade_with_none_pnl(self) -> None:
        record_trade(
            exchange="NSE", side="BUY", status="SUCCESS", pnl=None, ticker="RELIANCE"
        )
        # When pnl is None, the gauge should not be updated
        assert True  # no crash = pass

    def test_record_trade_with_pnl_no_ticker(self) -> None:
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=Decimal("100.50"),
            ticker=None,
        )
        # When ticker is None, the gauge should not be updated
        assert True  # no crash = pass

    def test_record_trade_with_negative_decimal_pnl(self) -> None:
        record_trade(
            exchange="NSE",
            side="SELL",
            status="SUCCESS",
            pnl=Decimal("-250.75"),
            ticker="TCS",
        )
        gauge = trade_pnl.labels(exchange="NSE", ticker="TCS")
        assert gauge._value.get() == -250.75  # noqa: PLR2004 – prometheus internal

    def test_record_trade_with_zero_decimal_pnl(self) -> None:
        record_trade(
            exchange="NSE",
            side="BUY",
            status="SUCCESS",
            pnl=Decimal("0"),
            ticker="INFY",
        )
        gauge = trade_pnl.labels(exchange="NSE", ticker="INFY")
        assert gauge._value.get() == 0.0


class TestUpdatePortfolioValueDecimal:
    """Tests for update_portfolio_value with Decimal values."""

    def test_update_portfolio_value_decimal(self) -> None:
        update_portfolio_value(value=Decimal("100000.50"))
        assert portfolio_value._value.get() == 100000.50  # noqa: PLR2004

    def test_update_portfolio_value_decimal_negative(self) -> None:
        update_portfolio_value(value=Decimal("-5000.00"))
        assert portfolio_value._value.get() == -5000.0

    def test_update_portfolio_value_decimal_zero(self) -> None:
        update_portfolio_value(value=Decimal("0"))
        assert portfolio_value._value.get() == 0.0

    def test_update_portfolio_value_decimal_large(self) -> None:
        update_portfolio_value(value=Decimal("99999999.99"))
        assert abs(portfolio_value._value.get() - 99999999.99) < 0.01


class TestUpdateDailyPnLDecimal:
    """Tests for update_daily_pnl with Decimal values."""

    def test_update_daily_pnl_decimal(self) -> None:
        update_daily_pnl(pnl=Decimal("5000.75"))
        assert daily_pnl._value.get() == 5000.75  # noqa: PLR2004

    def test_update_daily_pnl_decimal_loss(self) -> None:
        update_daily_pnl(pnl=Decimal("-2000.50"))
        assert daily_pnl._value.get() == -2000.5

    def test_update_daily_pnl_decimal_zero(self) -> None:
        update_daily_pnl(pnl=Decimal("0"))
        assert daily_pnl._value.get() == 0.0

    def test_update_daily_pnl_decimal_fractional(self) -> None:
        update_daily_pnl(pnl=Decimal("0.01"))
        assert daily_pnl._value.get() == 0.01
