"""Coverage tests for iatb.ml.trainer - UnifiedTrainer and helpers."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.trainer import (
    TrainingRunResult,
    UnifiedTrainer,
    _evaluate_model,
    _extract_score,
    _fit_model,
    _log_mlflow,
    _validate_dataset,
)


class TestValidateDataset:
    def test_empty_features_raises(self) -> None:
        with pytest.raises(ConfigError, match="train features"):
            _validate_dataset([], [Decimal("1")], "train")

    def test_empty_targets_raises(self) -> None:
        with pytest.raises(ConfigError, match="train features"):
            _validate_dataset([[Decimal("1")]], [], "train")

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ConfigError, match="equal length"):
            _validate_dataset([[Decimal("1")], [Decimal("2")]], [Decimal("1")], "train")

    def test_empty_feature_row_raises(self) -> None:
        with pytest.raises(ConfigError, match="feature rows cannot be empty"):
            _validate_dataset(
                [[Decimal("1")], []], [Decimal("1"), Decimal("2")], "train"
            )

    def test_valid_dataset_passes(self) -> None:
        _validate_dataset(
            [[Decimal("1")], [Decimal("2")]],
            [Decimal("1"), Decimal("2")],
            "validation",
        )


class TestExtractScore:
    def test_decimal_passthrough(self) -> None:
        assert _extract_score(Decimal("0.5")) == Decimal("0.5")

    def test_object_with_score_attribute(self) -> None:
        obj = MagicMock()
        obj.score = Decimal("0.75")
        assert _extract_score(obj) == Decimal("0.75")

    def test_invalid_result_raises(self) -> None:
        with pytest.raises(ConfigError, match="Decimal or expose Decimal score"):
            _extract_score("invalid")


class TestEvaluateModel:
    def test_computes_mae_correctly(self) -> None:
        model = MagicMock()
        model.predict.side_effect = [Decimal("10"), Decimal("20")]
        features = [[Decimal("1")], [Decimal("2")]]
        targets = [Decimal("12"), Decimal("18")]
        mae = _evaluate_model(model, features, targets)
        expected = (Decimal("2") + Decimal("2")) / Decimal("2")
        assert mae == expected


class TestFitModel:
    def test_train_method_returns_decimal(self) -> None:
        model = MagicMock()
        model.train.return_value = Decimal("0.15")
        result = _fit_model(model, [[Decimal("1")]], [Decimal("1")])
        assert result == Decimal("0.15")

    def test_no_train_or_fit_raises(self) -> None:
        model = MagicMock(spec=["predict"])
        model.predict.return_value = Decimal("1")
        with pytest.raises(ConfigError, match=r"train\(\) or fit\(\)"):
            _fit_model(model, [[Decimal("1")]], [Decimal("1")])


class TestLogMlflow:
    def test_tracking_disabled_returns_placeholder(self) -> None:
        result = _log_mlflow("exp", Decimal("0.1"), Decimal("0.2"), False)
        assert result == "tracking-disabled"


class TestUnifiedTrainer:
    def test_init_defaults(self) -> None:
        trainer = UnifiedTrainer(enable_tracking=False)
        assert trainer._experiment_name == "iatb_ml"
        assert trainer._enable_tracking is False

    def test_train_and_evaluate_empty_train_raises(self) -> None:
        trainer = UnifiedTrainer(enable_tracking=False)
        with pytest.raises(ConfigError, match="train features"):
            trainer.train_and_evaluate(
                MagicMock(), [], [Decimal("1")], [[Decimal("1")]], [Decimal("1")]
            )


class TestTrainingRunResult:
    def test_creation(self) -> None:
        result = TrainingRunResult(
            train_mae=Decimal("0.1"),
            validation_mae=Decimal("0.2"),
            experiment_name="test",
            run_id="run-123",
        )
        assert result.train_mae == Decimal("0.1")
