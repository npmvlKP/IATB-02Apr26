from decimal import Decimal
from types import SimpleNamespace

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult
from iatb.ml.trainer import UnifiedTrainer


class _TrainModel:
    def train(self, features: list[list[Decimal]], targets: list[Decimal]) -> Decimal:
        _ = features
        _ = targets
        return Decimal("0.05")

    def predict(self, features: list[Decimal]) -> PredictionResult:
        _ = features
        return PredictionResult("NIFTY", Decimal("0.2"), Decimal("0.7"), "BULL")


class _FitModel:
    def fit(self, features: list[list[Decimal]], targets: list[Decimal]) -> None:
        _ = features
        _ = targets

    def predict(self, features: list[Decimal]) -> Decimal:
        _ = features
        return Decimal("0.1")


def test_unified_trainer_train_and_eval_without_tracking() -> None:
    trainer = UnifiedTrainer(enable_tracking=False)
    result = trainer.train_and_evaluate(
        _TrainModel(),
        [[Decimal("1")], [Decimal("2")]],
        [Decimal("0.2"), Decimal("0.25")],
        [[Decimal("1.5")], [Decimal("2.5")]],
        [Decimal("0.2"), Decimal("0.2")],
    )
    assert result.run_id == "tracking-disabled"
    assert result.train_mae == Decimal("0.05")


def test_unified_trainer_fit_path_and_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RunInfo:
        run_id = "run-123"

    class _Run:
        info = _RunInfo()

    fake_mlflow = SimpleNamespace(
        set_experiment=lambda name: None,
        start_run=lambda: _Run(),
        log_metric=lambda key, value: None,
    )
    monkeypatch.setattr("iatb.ml.trainer.importlib.import_module", lambda _: fake_mlflow)
    trainer = UnifiedTrainer(enable_tracking=True)
    result = trainer.train_and_evaluate(
        _FitModel(),
        [[Decimal("1")], [Decimal("2")]],
        [Decimal("0.1"), Decimal("0.2")],
        [[Decimal("3")], [Decimal("4")]],
        [Decimal("0.1"), Decimal("0.1")],
    )
    assert result.run_id == "run-123"


def test_unified_trainer_validates_and_reports_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    trainer = UnifiedTrainer(enable_tracking=False)
    with pytest.raises(ConfigError, match="cannot be empty"):
        trainer.train_and_evaluate(_FitModel(), [], [], [[Decimal("1")]], [Decimal("1")])
    with pytest.raises(ConfigError, match="equal length"):
        trainer.train_and_evaluate(
            _FitModel(),
            [[Decimal("1")]],
            [Decimal("1"), Decimal("2")],
            [[Decimal("1")]],
            [Decimal("1")],
        )
    with pytest.raises(ConfigError, match="empty"):
        trainer.train_and_evaluate(
            _FitModel(), [[]], [Decimal("1")], [[Decimal("1")]], [Decimal("1")]
        )
    monkeypatch.setattr(
        "iatb.ml.trainer.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="mlflow dependency"):
        UnifiedTrainer(enable_tracking=True).train_and_evaluate(
            _FitModel(),
            [[Decimal("1")]],
            [Decimal("0.1")],
            [[Decimal("1")]],
            [Decimal("0.1")],
        )
