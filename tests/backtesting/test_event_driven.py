from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.backtesting.event_driven import EventDrivenBacktester
from iatb.core.exceptions import ConfigError


def test_event_driven_backtester_builds_equity_curve() -> None:
    backtester = EventDrivenBacktester(engine_runner=lambda events: [Decimal("10"), Decimal("-4")])
    result = backtester.run(events=[{"signal": "BUY"}], starting_equity=Decimal("1000"))
    assert result.total_pnl == Decimal("6")
    assert result.equity_curve == [Decimal("1000"), Decimal("1010"), Decimal("1006")]


def test_event_driven_backtester_rejects_non_positive_equity() -> None:
    backtester = EventDrivenBacktester(engine_runner=lambda events: [])
    with pytest.raises(ConfigError, match="starting_equity must be positive"):
        backtester.run(events=[], starting_equity=Decimal("0"))


def test_event_driven_default_runner_requires_openengine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.event_driven.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    backtester = EventDrivenBacktester()
    with pytest.raises(ConfigError, match="openengine dependency"):
        backtester.run(events=[], starting_equity=Decimal("1000"))


def test_event_driven_default_runner_requires_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.event_driven.importlib.import_module",
        lambda _: SimpleNamespace(),
    )
    backtester = EventDrivenBacktester()
    with pytest.raises(ConfigError, match="simulate_events callable is unavailable"):
        backtester.run(events=[], starting_equity=Decimal("1000"))
