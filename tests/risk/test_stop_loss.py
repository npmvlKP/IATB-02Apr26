from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError
from iatb.risk.stop_loss import atr_stop_price, should_time_exit, trailing_stop_price


def test_atr_and_trailing_stop_prices() -> None:
    buy_stop = atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.BUY, Decimal("2"))
    sell_stop = atr_stop_price(Decimal("100"), Decimal("2"), OrderSide.SELL, Decimal("2"))
    assert buy_stop == Decimal("96")
    assert sell_stop == Decimal("104")
    trailed_buy = trailing_stop_price(Decimal("95"), Decimal("110"), OrderSide.BUY, Decimal("0.01"))
    trailed_sell = trailing_stop_price(
        Decimal("105"), Decimal("90"), OrderSide.SELL, Decimal("0.01")
    )
    assert trailed_buy == Decimal("108.90")
    assert trailed_sell == Decimal("90.90")


def test_time_exit_and_validations() -> None:
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    assert not should_time_exit(start, start + timedelta(minutes=10), 30)
    assert should_time_exit(start, start + timedelta(minutes=31), 30)
    with pytest.raises(ConfigError, match="must be positive"):
        atr_stop_price(Decimal("0"), Decimal("1"), OrderSide.BUY)
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        should_time_exit(start.replace(tzinfo=None), start, 30)  # noqa: DTZ007


def test_trailing_stop_price_validation_errors() -> None:
    with pytest.raises(ConfigError, match="must be positive"):
        trailing_stop_price(Decimal("0"), Decimal("100"), OrderSide.BUY)
    with pytest.raises(ConfigError, match="must be between 0 and 1"):
        trailing_stop_price(Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("0"))
    with pytest.raises(ConfigError, match="must be between 0 and 1"):
        trailing_stop_price(Decimal("95"), Decimal("100"), OrderSide.BUY, Decimal("1"))


def test_should_time_exit_validation_errors() -> None:
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    with pytest.raises(ConfigError, match="timezone-aware UTC"):
        should_time_exit(start, start.replace(tzinfo=None), 30)  # noqa: DTZ007
    with pytest.raises(ConfigError, match="must be positive"):
        should_time_exit(start, start, 0)
