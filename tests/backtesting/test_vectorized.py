from decimal import Decimal

import pytest
from iatb.backtesting.vectorized import VectorizedBacktester
from iatb.core.exceptions import ConfigError


def test_vectorized_backtester_runs_parameter_sweep() -> None:
    evaluator = lambda prices, params: prices[-1] - prices[0] + params["fast_window"]  # noqa: E731
    backtester = VectorizedBacktester(evaluator=evaluator)
    result = backtester.run_sweep(
        close_prices=[Decimal("100"), Decimal("101"), Decimal("103")],
        parameter_grid={
            "fast_window": [Decimal("5"), Decimal("10")],
            "slow_window": [Decimal("20")],
        },
    )
    assert result.best_params["fast_window"] == Decimal("10")
    assert len(result.scores) == 2


def test_vectorized_backtester_rejects_invalid_inputs() -> None:
    backtester = VectorizedBacktester(evaluator=lambda prices, params: Decimal("0"))
    with pytest.raises(ConfigError, match="at least two points"):
        backtester.run_sweep([Decimal("1")], {"fast_window": [Decimal("5")]})
    with pytest.raises(ConfigError, match="parameter_grid cannot be empty"):
        backtester.run_sweep([Decimal("1"), Decimal("2")], {})


def test_vectorized_default_evaluator_requires_vectorbt_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.vectorized.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    backtester = VectorizedBacktester()
    with pytest.raises(ConfigError, match="vectorbt dependency"):
        backtester.run_sweep(
            close_prices=[Decimal("1"), Decimal("2")],
            parameter_grid={"fast_window": [Decimal("5")], "slow_window": [Decimal("10")]},
        )
