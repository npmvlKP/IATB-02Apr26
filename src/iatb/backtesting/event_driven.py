"""
Event-driven backtesting integration.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError

EngineRunner = Callable[[list[object]], list[Decimal]]


@dataclass(frozen=True)
class EventDrivenResult:
    equity_curve: list[Decimal]
    total_pnl: Decimal
    trades: int


class EventDrivenBacktester:
    """Execute event streams through an OpenEngine-compatible runner."""

    def __init__(self, engine_runner: EngineRunner | None = None) -> None:
        self._runner = engine_runner or _default_engine_runner

    def run(self, events: list[object], starting_equity: Decimal) -> EventDrivenResult:
        if starting_equity <= Decimal("0"):
            msg = "starting_equity must be positive"
            raise ConfigError(msg)
        pnl_series = self._runner(events)
        equity_curve = _equity_curve(starting_equity, pnl_series)
        total_pnl = sum(pnl_series, Decimal("0"))
        return EventDrivenResult(
            equity_curve=equity_curve,
            total_pnl=total_pnl,
            trades=len(pnl_series),
        )


def _default_engine_runner(events: list[object]) -> list[Decimal]:
    module = _load_openengine_module()
    runner = getattr(module, "simulate_events", None)
    if not callable(runner):
        msg = "openengine simulate_events callable is unavailable"
        raise ConfigError(msg)
    raw = runner(events)
    if not isinstance(raw, list):
        msg = "simulate_events must return list of Decimal-compatible values"
        raise ConfigError(msg)
    return [Decimal(str(item)) for item in raw]


def _equity_curve(starting_equity: Decimal, pnl_series: list[Decimal]) -> list[Decimal]:
    current = starting_equity
    curve = [starting_equity]
    for pnl in pnl_series:
        current += pnl
        curve.append(current)
    return curve


def _load_openengine_module() -> object:
    try:
        return importlib.import_module("openengine")
    except ModuleNotFoundError as exc:
        msg = "openengine dependency is required for event-driven backtesting"
        raise ConfigError(msg) from exc
