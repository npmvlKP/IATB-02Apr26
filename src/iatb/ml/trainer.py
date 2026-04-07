"""
Unified train/evaluate loop with optional MLflow tracking.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from iatb.core.exceptions import ConfigError


class _TrainableModel(Protocol):
    def predict(self, features: list[Decimal]) -> object:
        ...


@dataclass(frozen=True)
class TrainingRunResult:
    train_mae: Decimal
    validation_mae: Decimal
    experiment_name: str
    run_id: str


class UnifiedTrainer:
    def __init__(self, experiment_name: str = "iatb_ml", enable_tracking: bool = True) -> None:
        self._experiment_name = experiment_name
        self._enable_tracking = enable_tracking

    def train_and_evaluate(
        self,
        model: _TrainableModel,
        train_features: list[list[Decimal]],
        train_targets: list[Decimal],
        validation_features: list[list[Decimal]],
        validation_targets: list[Decimal],
    ) -> TrainingRunResult:
        _validate_dataset(train_features, train_targets, "train")
        _validate_dataset(validation_features, validation_targets, "validation")
        train_mae = _fit_model(model, train_features, train_targets)
        validation_mae = _evaluate_model(model, validation_features, validation_targets)
        run_id = _log_mlflow(
            self._experiment_name,
            train_mae,
            validation_mae,
            self._enable_tracking,
        )
        return TrainingRunResult(train_mae, validation_mae, self._experiment_name, run_id)


def _validate_dataset(features: list[list[Decimal]], targets: list[Decimal], name: str) -> None:
    if not features or not targets:
        msg = f"{name} features and targets cannot be empty"
        raise ConfigError(msg)
    if len(features) != len(targets):
        msg = f"{name} features and targets must have equal length"
        raise ConfigError(msg)
    if any(not row for row in features):
        msg = f"{name} feature rows cannot be empty"
        raise ConfigError(msg)


def _fit_model(
    model: _TrainableModel, features: list[list[Decimal]], targets: list[Decimal]
) -> Decimal:
    train_method = getattr(model, "train", None)
    fit_method = getattr(model, "fit", None)
    if callable(train_method):
        result = train_method(features, targets)
        if isinstance(result, Decimal):
            return result
        return _evaluate_model(model, features, targets)
    if callable(fit_method):
        fit_method(features, targets)
        return _evaluate_model(model, features, targets)
    msg = "model must expose train() or fit()"
    raise ConfigError(msg)


def _evaluate_model(
    model: _TrainableModel, features: list[list[Decimal]], targets: list[Decimal]
) -> Decimal:
    predictions = [_extract_score(model.predict(row)) for row in features]
    errors = [abs(predictions[idx] - targets[idx]) for idx in range(len(targets))]
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def _extract_score(result: object) -> Decimal:
    if isinstance(result, Decimal):
        return result
    score = getattr(result, "score", None)
    if isinstance(score, Decimal):
        return score
    msg = "predict() result must be Decimal or expose Decimal score"
    raise ConfigError(msg)


def _log_mlflow(
    experiment_name: str,
    train_mae: Decimal,
    validation_mae: Decimal,
    enabled: bool,
) -> str:
    if not enabled:
        return "tracking-disabled"
    mlflow = _load_mlflow()
    set_experiment = getattr(mlflow, "set_experiment", None)
    start_run = getattr(mlflow, "start_run", None)
    log_metric = getattr(mlflow, "log_metric", None)
    if not callable(set_experiment) or not callable(start_run) or not callable(log_metric):
        msg = "mlflow API is incomplete for experiment tracking"
        raise ConfigError(msg)
    set_experiment(experiment_name)
    run = start_run()
    log_metric("train_mae", float(train_mae))
    log_metric("validation_mae", float(validation_mae))
    run_id = getattr(getattr(run, "info", object()), "run_id", None)
    if not isinstance(run_id, str):
        msg = "mlflow run_id is unavailable"
        raise ConfigError(msg)
    return run_id


def _load_mlflow() -> object:
    try:
        return importlib.import_module("mlflow")
    except ModuleNotFoundError as exc:
        msg = "mlflow dependency is required when tracking is enabled"
        raise ConfigError(msg) from exc
