from decimal import Decimal

import pytest
from iatb.backtesting.forward_test import ForwardTestConfig, ForwardTester
from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError


def test_forward_tester_runs_paper_trade_window() -> None:
    tester = ForwardTester()
    result = tester.run(
        signals=[OrderSide.BUY, OrderSide.SELL, OrderSide.BUY],
        price_moves=[Decimal("10"), Decimal("4"), Decimal("-2")],
        config=ForwardTestConfig(duration_days=3, max_trades=5),
    )
    assert result.trades_executed == 3
    assert result.net_pnl == Decimal("4")
    assert result.completed


def test_forward_tester_rejects_invalid_config() -> None:
    tester = ForwardTester()
    with pytest.raises(ConfigError, match="duration_days must be positive"):
        tester.run([], [], ForwardTestConfig(duration_days=0, max_trades=1))
    with pytest.raises(ConfigError, match="max_trades must be positive"):
        tester.run([], [], ForwardTestConfig(duration_days=1, max_trades=0))
