"""
Forward-testing simulation for paper-trade validation windows.
"""

from dataclasses import dataclass
from decimal import Decimal

from iatb.core.enums import OrderSide
from iatb.core.exceptions import ConfigError


@dataclass(frozen=True)
class ForwardTestConfig:
    duration_days: int
    max_trades: int


@dataclass(frozen=True)
class ForwardTestResult:
    trades_executed: int
    net_pnl: Decimal
    completed: bool


class ForwardTester:
    """Simple paper-trading simulator for forward-test windows."""

    def run(
        self,
        signals: list[OrderSide],
        price_moves: list[Decimal],
        config: ForwardTestConfig,
    ) -> ForwardTestResult:
        _validate_config(config)
        iterations = min(len(signals), len(price_moves), config.duration_days, config.max_trades)
        net_pnl = Decimal("0")
        for index in range(iterations):
            side = signals[index]
            move = price_moves[index]
            if side == OrderSide.BUY:
                net_pnl += move
            else:
                net_pnl -= move
        return ForwardTestResult(
            trades_executed=iterations,
            net_pnl=net_pnl,
            completed=iterations == min(config.duration_days, config.max_trades),
        )


def _validate_config(config: ForwardTestConfig) -> None:
    if config.duration_days <= 0:
        msg = "duration_days must be positive"
        raise ConfigError(msg)
    if config.max_trades <= 0:
        msg = "max_trades must be positive"
        raise ConfigError(msg)
