"""Coverage tests for iatb.ml.tracking - ExperimentTracker, HyperparameterOptimizer."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.tracking import (
    ExperimentMetrics,
    ExperimentTracker,
    HyperparameterOptimizer,
    MLflowConfig,
    OptunaConfig,
    create_default_tracking,
)


class TestMLflowConfig:
    def test_defaults(self) -> None:
        config = MLflowConfig()
        assert config.tracking_uri == "file:///mlruns"
        assert config.experiment_name == "iatb-experiments"
        assert config.enable_tracking is True

    def test_custom_config(self) -> None:
        config = MLflowConfig(
            tracking_uri="http://localhost:5000", enable_tracking=False
        )
        assert config.tracking_uri == "http://localhost:5000"


class TestOptunaConfig:
    def test_defaults(self) -> None:
        config = OptunaConfig()
        assert config.n_trials == 100
        assert config.direction == "maximize"


class TestExperimentMetrics:
    def test_defaults(self) -> None:
        metrics = ExperimentMetrics()
        assert metrics.sharpe_ratio is None
        assert metrics.custom_metrics == {}

    def test_with_values(self) -> None:
        metrics = ExperimentMetrics(sharpe_ratio=Decimal("1.5"), num_trades=100)
        assert metrics.sharpe_ratio == Decimal("1.5")


class TestExperimentTracker:
    def test_init_disabled_tracking(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        assert tracker.config.enable_tracking is False

    def test_start_run_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.start_run(run_name="test")
        assert tracker.active_run is None

    def test_log_params_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.log_params({"lr": Decimal("0.01")})

    def test_log_metrics_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.log_metrics(ExperimentMetrics())

    def test_end_run_disabled(self) -> None:
        config = MLflowConfig(enable_tracking=False)
        tracker = ExperimentTracker(config=config)
        tracker.end_run()

    def test_start_run_enabled(self) -> None:
        with patch("iatb.ml.tracking.mlflow") as mock_mlflow:
            mock_run = MagicMock()
            mock_run.info.run_id = "test-run"
            mock_mlflow.start_run.return_value = mock_run
            config = MLflowConfig(enable_tracking=True)
            tracker = ExperimentTracker(config=config)
            tracker.start_run(run_name="test")
            assert tracker.active_run is not None

    def test_setup_mlflow_failure_raises(self) -> None:
        with patch("iatb.ml.tracking.mlflow") as mock_mlflow:
            mock_mlflow.set_tracking_uri.side_effect = Exception("conn fail")
            config = MLflowConfig(enable_tracking=True)
            with pytest.raises(ConfigError, match="Failed to setup MLflow"):
                ExperimentTracker(config=config)


class TestHyperparameterOptimizer:
    def test_invalid_direction_raises(self) -> None:
        config = OptunaConfig(direction="invalid")
        with pytest.raises(ConfigError, match="Invalid direction"):
            HyperparameterOptimizer(config=config)

    def test_get_best_params_no_study_raises(self) -> None:
        with patch("iatb.ml.tracking.optuna"):
            opt = HyperparameterOptimizer()
            opt.study = None
            with pytest.raises(ConfigError, match="Study has not been created"):
                opt.get_best_params()

    def test_get_best_params_success(self) -> None:
        with patch("iatb.ml.tracking.optuna"):
            opt = HyperparameterOptimizer()
            mock_study = MagicMock()
            mock_study.trials = [MagicMock()]
            mock_study.best_params = {"lr": 0.01}
            opt.study = mock_study
            result = opt.get_best_params()
            assert result == {"lr": 0.01}


class TestCreateDefaultTracking:
    def test_defaults(self) -> None:
        with patch("iatb.ml.tracking.mlflow"):
            tracker = create_default_tracking()
            assert isinstance(tracker, ExperimentTracker)
