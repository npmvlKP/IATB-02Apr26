from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.backtesting.walk_forward import WalkForwardOptimizer
from iatb.core.exceptions import ConfigError


def test_walk_forward_optimizer_runs_expected_number_of_folds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sampler_module = SimpleNamespace(samplers=SimpleNamespace(TPESampler=lambda seed: object()))
    monkeypatch.setattr(
        "iatb.backtesting.walk_forward.importlib.import_module",
        lambda _: sampler_module,
    )
    optimizer = WalkForwardOptimizer(n_splits=5)
    returns = [Decimal("0.001")] * 18
    result = optimizer.run(returns)
    assert len(result.folds) == 5
    assert result.sampler_name == "object"


def test_walk_forward_optimizer_detects_overfitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sampler_module = SimpleNamespace(samplers=SimpleNamespace(TPESampler=lambda seed: object()))
    monkeypatch.setattr(
        "iatb.backtesting.walk_forward.importlib.import_module",
        lambda _: sampler_module,
    )
    scorer_values = iter(
        [
            Decimal("3.0"),
            Decimal("1.0"),
            Decimal("3.2"),
            Decimal("1.2"),
            Decimal("3.1"),
            Decimal("1.3"),
            Decimal("2.8"),
            Decimal("1.1"),
            Decimal("3.5"),
            Decimal("1.2"),
        ]
    )
    optimizer = WalkForwardOptimizer(n_splits=5, scorer=lambda values: next(scorer_values))
    result = optimizer.run([Decimal("0.001")] * 20)
    assert result.overfitting_detected


def test_walk_forward_optimizer_rejects_invalid_configuration() -> None:
    with pytest.raises(ConfigError, match="n_splits must be >= 2"):
        WalkForwardOptimizer(n_splits=1)


def test_walk_forward_optimizer_requires_optuna_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "iatb.backtesting.walk_forward.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    optimizer = WalkForwardOptimizer(n_splits=5)
    with pytest.raises(ConfigError, match="optuna dependency"):
        optimizer.run([Decimal("0.001")] * 20)
