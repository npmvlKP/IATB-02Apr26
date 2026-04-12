import random
from decimal import Decimal

import numpy as np
import pytest
import torch
from iatb.backtesting.vectorized import VectorizedBacktester
from iatb.core.exceptions import ConfigError

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


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


def test_vectorized_backtester_with_single_parameter() -> None:
    """Test backtester with a single parameter combination."""

    def evaluator(prices, params):
        return prices[-1] - prices[0]

    backtester = VectorizedBacktester(evaluator=evaluator)
    result = backtester.run_sweep(
        close_prices=[Decimal("100"), Decimal("110"), Decimal("120")],
        parameter_grid={
            "fast_window": [Decimal("5")],
        },
    )
    assert len(result.scores) == 1
    assert result.best_score == Decimal("20")


def test_vectorized_backtester_with_multiple_parameters() -> None:
    """Test backtester with multiple parameter combinations."""

    def custom_evaluator(prices, params):
        # Simple strategy: return profit if fast > slow
        if params["fast"] > params["slow"]:
            return prices[-1] - prices[0]
        return Decimal("0")

    backtester = VectorizedBacktester(evaluator=custom_evaluator)
    result = backtester.run_sweep(
        close_prices=[Decimal("100"), Decimal("105"), Decimal("110")],
        parameter_grid={
            "fast": [Decimal("10"), Decimal("20")],
            "slow": [Decimal("5"), Decimal("15")],
        },
    )
    # Should have 4 combinations: (10,5), (10,15), (20,5), (20,15)
    assert len(result.scores) == 4


def test_vectorized_backtester_empty_result() -> None:
    """Test backtester when evaluator returns zero for all params."""

    def evaluator(prices, params):
        return Decimal("0")

    backtester = VectorizedBacktester(evaluator=evaluator)
    result = backtester.run_sweep(
        close_prices=[Decimal("100"), Decimal("100"), Decimal("100")],
        parameter_grid={
            "fast_window": [Decimal("5"), Decimal("10")],
        },
    )
    assert result.best_score == Decimal("0")


def test_vectorized_backtester_with_negative_scores() -> None:
    """Test backtester when evaluator can return negative values."""

    def variable_evaluator(prices, params):
        # Returns profit/loss based on parameter value
        if params["fast"] < Decimal("8"):
            return Decimal("100")  # Profit
        else:
            return Decimal("-50")  # Loss

    backtester = VectorizedBacktester(evaluator=variable_evaluator)
    result = backtester.run_sweep(
        close_prices=[Decimal("100"), Decimal("105"), Decimal("110")],
        parameter_grid={
            "fast": [Decimal("5"), Decimal("10")],
        },
    )
    # Best score should be the profitable one (100)
    assert result.best_score == Decimal("100")
    assert len(result.scores) == 2
    assert result.best_params["fast"] == Decimal("5")
