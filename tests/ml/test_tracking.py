"""
Tests for MLflow + Optuna experiment tracking module.

Tests cover:
- MLflow configuration and setup
- Experiment tracking and logging
- Hyperparameter optimization
- Integration with reward functions
- Edge cases and error handling
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import optuna
import pytest
from iatb.core.exceptions import ConfigError
from iatb.ml.tracking import (
    ExperimentMetrics,
    ExperimentTracker,
    HyperparameterOptimizer,
    MLflowConfig,
    OptunaConfig,
    create_default_optimizer,
    create_default_tracking,
)


class TestMLflowConfig:
    """Tests for MLflowConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = MLflowConfig()
        assert config.tracking_uri == "file:///mlruns"
        assert config.experiment_name == "iatb-experiments"
        assert config.enable_tracking is True
        assert config.artifact_location is None

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = MLflowConfig(
            tracking_uri="http://localhost:5000",
            experiment_name="custom-experiment",
            enable_tracking=False,
            artifact_location="/custom/path",
        )
        assert config.tracking_uri == "http://localhost:5000"
        assert config.experiment_name == "custom-experiment"
        assert config.enable_tracking is False
        assert config.artifact_location == "/custom/path"


class TestOptunaConfig:
    """Tests for OptunaConfig model."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = OptunaConfig()
        assert config.n_trials == 100
        assert config.timeout is None
        assert config.direction == "maximize"
        assert config.study_name == "iatb-optimization"
        assert config.storage is None

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = OptunaConfig(
            n_trials=50,
            timeout=3600,
            direction="minimize",
            study_name="custom-study",
            storage="sqlite:///optuna.db",
        )
        assert config.n_trials == 50
        assert config.timeout == 3600
        assert config.direction == "minimize"
        assert config.study_name == "custom-study"
        assert config.storage == "sqlite:///optuna.db"

    def test_invalid_n_trials(self) -> None:
        """Test that invalid n_trials raises validation error."""
        with pytest.raises(ValueError):
            OptunaConfig(n_trials=0)


class TestExperimentMetrics:
    """Tests for ExperimentMetrics model."""

    def test_empty_metrics(self) -> None:
        """Test empty metrics object."""
        metrics = ExperimentMetrics()
        assert metrics.sharpe_ratio is None
        assert metrics.sortino_ratio is None
        assert metrics.total_return is None
        assert metrics.max_drawdown is None
        assert metrics.win_rate is None
        assert metrics.profit_factor is None
        assert metrics.num_trades is None
        assert metrics.custom_metrics == {}

    def test_with_all_metrics(self) -> None:
        """Test metrics with all values populated."""
        metrics = ExperimentMetrics(
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            total_return=Decimal("25.5"),
            max_drawdown=Decimal("-10.0"),
            win_rate=Decimal("60.0"),
            profit_factor=Decimal("1.8"),
            num_trades=100,
            custom_metrics={"custom": Decimal("5.0")},
        )
        assert metrics.sharpe_ratio == Decimal("1.5")
        assert metrics.sortino_ratio == Decimal("2.0")
        assert metrics.total_return == Decimal("25.5")
        assert metrics.max_drawdown == Decimal("-10.0")
        assert metrics.win_rate == Decimal("60.0")
        assert metrics.profit_factor == Decimal("1.8")
        assert metrics.num_trades == 100
        assert metrics.custom_metrics == {"custom": Decimal("5.0")}


class TestExperimentTracker:
    """Tests for ExperimentTracker class."""

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.create_experiment")
    def test_initialization_creates_experiment(
        self,
        mock_create_experiment: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that initialization creates experiment if it doesn't exist."""
        mock_get_experiment.return_value = None
        mock_create_experiment.return_value = "experiment_id"

        config = MLflowConfig(experiment_name="test-exp")
        ExperimentTracker(config=config)

        mock_set_uri.assert_called_once_with("file:///mlruns")
        mock_get_experiment.assert_called_once_with("test-exp")
        mock_create_experiment.assert_called_once()

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    def test_initialization_uses_existing_experiment(
        self,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that initialization uses existing experiment."""
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "existing_id"
        mock_get_experiment.return_value = mock_experiment

        config = MLflowConfig(experiment_name="existing-exp")
        ExperimentTracker(config=config)

        mock_set_uri.assert_called_once_with("file:///mlruns")
        mock_get_experiment.assert_called_once_with("existing-exp")

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.create_experiment")
    def test_initialization_with_disabled_tracking(
        self,
        mock_create_experiment: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that initialization skips MLflow setup when tracking disabled."""
        config = MLflowConfig(enable_tracking=False)
        ExperimentTracker(config=config)

        mock_set_uri.assert_not_called()
        mock_get_experiment.assert_not_called()
        mock_create_experiment.assert_not_called()

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.create_experiment")
    def test_initialization_failure_raises_config_error(
        self,
        mock_create_experiment: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that MLflow setup failure raises ConfigError."""
        mock_set_uri.side_effect = Exception("Connection failed")

        with pytest.raises(ConfigError, match="Failed to setup MLflow"):
            ExperimentTracker(config=MLflowConfig())

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    def test_start_run(
        self,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test starting a new MLflow run."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run(run_name="test-run", tags={"tag": "value"})

        mock_start_run.assert_called_once_with(
            run_name="test-run",
            tags={"tag": "value"},
            description=None,
        )
        assert tracker.active_run == mock_run

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    def test_start_run_with_disabled_tracking(
        self,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that start_run skips when tracking disabled."""
        tracker = ExperimentTracker(config=MLflowConfig(enable_tracking=False))
        tracker.start_run(run_name="test-run")

        assert tracker.active_run is None

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    def test_log_params(
        self,
        mock_log_params: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test logging parameters."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()
        tracker.log_params({"param1": Decimal("1.5"), "param2": "string", "param3": 10})

        mock_log_params.assert_called_once()
        logged_params = mock_log_params.call_args[0][0]
        assert logged_params["param1"] == 1.5  # Decimal converted to float
        assert logged_params["param2"] == "string"
        assert logged_params["param3"] == 10

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_metrics")
    def test_log_metrics(
        self,
        mock_log_metrics: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test logging metrics."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()

        metrics = ExperimentMetrics(
            sharpe_ratio=Decimal("1.5"),
            sortino_ratio=Decimal("2.0"),
            custom_metrics={"custom": Decimal("5.0")},
        )
        tracker.log_metrics(metrics, step=1)

        mock_log_metrics.assert_called_once()
        logged_metrics = mock_log_metrics.call_args[0][0]
        assert logged_metrics["sharpe_ratio"] == 1.5
        assert logged_metrics["sortino_ratio"] == 2.0
        assert logged_metrics["custom"] == 5.0

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_artifact")
    def test_log_artifact(
        self,
        mock_log_artifact: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test logging artifact."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()
        tracker.log_artifact("/path/to/artifact.txt")

        mock_log_artifact.assert_called_once_with("/path/to/artifact.txt")

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.end_run")
    def test_end_run(
        self,
        mock_end_run: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test ending a run."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()
        tracker.end_run(status="FINISHED")

        mock_end_run.assert_called_once_with("FINISHED")
        assert tracker.active_run is None


class TestHyperparameterOptimizer:
    """Tests for HyperparameterOptimizer class."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        optimizer = HyperparameterOptimizer()
        assert optimizer.config.n_trials == 100
        assert optimizer.config.direction == "maximize"

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = OptunaConfig(n_trials=50, direction="minimize")
        optimizer = HyperparameterOptimizer(config=config)
        assert optimizer.config.n_trials == 50
        assert optimizer.config.direction == "minimize"

    def test_invalid_direction_raises_config_error(self) -> None:
        """Test that invalid direction raises ConfigError."""
        with pytest.raises(ConfigError, match="Invalid direction"):
            HyperparameterOptimizer(config=OptunaConfig(direction="invalid"))

    @patch("optuna.create_study")
    def test_create_study(self, mock_create_study: MagicMock) -> None:
        """Test creating a study."""
        mock_study = MagicMock()
        mock_study.trials = []
        mock_create_study.return_value = mock_study

        optimizer = HyperparameterOptimizer()
        optimizer.create_study()

        mock_create_study.assert_called_once()
        assert optimizer.study == mock_study

    @patch("optuna.create_study")
    def test_optimize(self, mock_create_study: MagicMock) -> None:
        """Test running optimization."""
        mock_study = MagicMock()
        mock_study.trials = [MagicMock(), MagicMock()]
        mock_study.best_value = 0.95
        mock_create_study.return_value = mock_study

        def objective(trial: optuna.Trial) -> float:
            return trial.suggest_float("x", 0, 1)

        optimizer = HyperparameterOptimizer()
        optimizer.optimize(objective, n_trials=2)

        assert len(optimizer.study.trials) == 2
        assert optimizer.study.best_value == 0.95

    @patch("optuna.create_study")
    def test_get_best_params(self, mock_create_study: MagicMock) -> None:
        """Test getting best parameters."""
        mock_study = MagicMock()
        mock_study.trials = [MagicMock()]
        mock_study.best_params = {"param1": 0.5, "param2": 0.8}
        mock_create_study.return_value = mock_study

        optimizer = HyperparameterOptimizer()
        optimizer.create_study()

        best_params = optimizer.get_best_params()
        assert best_params == {"param1": 0.5, "param2": 0.8}

    @patch("optuna.create_study")
    def test_get_best_params_without_study_raises_error(self, mock_create_study: MagicMock) -> None:
        """Test that getting best params without study raises error."""
        optimizer = HyperparameterOptimizer()

        with pytest.raises(ConfigError, match="Study has not been created"):
            optimizer.get_best_params()

    @patch("optuna.create_study")
    def test_get_best_params_without_trials_raises_error(
        self, mock_create_study: MagicMock
    ) -> None:
        """Test that getting best params without trials raises error."""
        mock_study = MagicMock()
        mock_study.trials = []
        mock_create_study.return_value = mock_study

        optimizer = HyperparameterOptimizer()
        optimizer.create_study()

        with pytest.raises(ConfigError, match="Study has no trials"):
            optimizer.get_best_params()

    @patch("optuna.create_study")
    def test_get_best_value(self, mock_create_study: MagicMock) -> None:
        """Test getting best value."""
        mock_study = MagicMock()
        mock_study.trials = [MagicMock()]
        mock_study.best_value = 0.95
        mock_create_study.return_value = mock_study

        optimizer = HyperparameterOptimizer()
        optimizer.create_study()

        best_value = optimizer.get_best_value()
        assert best_value == 0.95


class TestIntegrationWithRewardFunctions:
    """Tests for integration with DRL reward functions."""

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_metrics")
    @patch("mlflow.log_params")
    @patch("mlflow.end_run")
    def test_track_reward_function_metrics(
        self,
        mock_end_run: MagicMock,
        mock_log_params: MagicMock,
        mock_log_metrics: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test tracking metrics from reward functions."""
        from iatb.rl.reward import sharpe_reward, sortino_reward

        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()

        # Calculate rewards
        returns = [Decimal("0.01"), Decimal("0.02"), Decimal("-0.01"), Decimal("0.03")]
        sharpe = sharpe_reward(returns)
        sortino = sortino_reward(returns)

        # Log as experiment metrics
        metrics = ExperimentMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            num_trades=10,
            custom_metrics={"total_pnl": Decimal("100.0")},
        )
        tracker.log_params({"num_returns": len(returns)})
        tracker.log_metrics(metrics)
        tracker.end_run()

        mock_log_params.assert_called_once()
        mock_log_metrics.assert_called_once()
        mock_end_run.assert_called_once()

    @patch("optuna.create_study")
    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_metrics")
    @patch("mlflow.log_params")
    @patch("mlflow.end_run")
    def test_optimize_reward_threshold(
        self,
        mock_end_run: MagicMock,
        mock_log_params: MagicMock,
        mock_log_metrics: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
        mock_create_study: MagicMock,
    ) -> None:
        """Test optimizing reward threshold using Optuna."""
        from iatb.rl.reward import positive_exit_reward

        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        mock_study = MagicMock()
        mock_study.trials = [MagicMock(), MagicMock()]
        mock_study.best_value = 0.95
        mock_study.best_params = {"threshold": 0.75}
        mock_create_study.return_value = mock_study

        tracker = ExperimentTracker(config=MLflowConfig())
        optimizer = HyperparameterOptimizer(config=OptunaConfig(n_trials=2))

        def objective(trial: optuna.Trial) -> float:
            threshold = Decimal(str(trial.suggest_float("threshold", 0.5, 0.9)))
            reward = positive_exit_reward(
                exit_probability=Decimal("0.8"),
                pnl=Decimal("100.0"),
                threshold=threshold,
            )
            return float(reward)

        optimizer.optimize(objective, tracker=tracker)

        assert optimizer.study.best_params["threshold"] == 0.75


class TestHelperFunctions:
    """Tests for helper functions."""

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    def test_create_default_tracking(
        self,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test creating default tracker."""
        mock_get_experiment.return_value = MagicMock()

        tracker = create_default_tracking(
            tracking_uri="http://custom:5000",
            experiment_name="default-exp",
        )

        mock_set_uri.assert_called_once_with("http://custom:5000")
        assert tracker.config.experiment_name == "default-exp"

    def test_create_default_optimizer(self) -> None:
        """Test creating default optimizer."""
        optimizer = create_default_optimizer(n_trials=50, direction="minimize")

        assert optimizer.config.n_trials == 50
        assert optimizer.config.direction == "minimize"


class TestEdgeCasesAndErrorHandling:
    """Tests for edge cases and error handling."""

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_metrics")
    def test_log_metrics_without_active_run(
        self,
        mock_log_metrics: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that logging metrics without active run is handled gracefully."""
        mock_get_experiment.return_value = MagicMock()
        tracker = ExperimentTracker(config=MLflowConfig())

        metrics = ExperimentMetrics(sharpe_ratio=Decimal("1.5"))
        tracker.log_metrics(metrics)

        mock_log_metrics.assert_not_called()

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    def test_end_run_without_active_run(
        self,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test that ending run without active run is handled gracefully."""
        mock_get_experiment.return_value = MagicMock()
        tracker = ExperimentTracker(config=MLflowConfig())

        tracker.end_run()  # Should not raise

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.get_experiment_by_name")
    @patch("mlflow.start_run")
    @patch("mlflow.log_params")
    def test_log_params_with_mixed_types(
        self,
        mock_log_params: MagicMock,
        mock_start_run: MagicMock,
        mock_get_experiment: MagicMock,
        mock_set_uri: MagicMock,
    ) -> None:
        """Test logging parameters with mixed types."""
        mock_get_experiment.return_value = MagicMock()
        mock_run = MagicMock()
        mock_run.info.run_id = "test_run_id"
        mock_start_run.return_value = mock_run

        tracker = ExperimentTracker(config=MLflowConfig())
        tracker.start_run()

        params = {
            "decimal_param": Decimal("1.5"),
            "int_param": 10,
            "float_param": 0.5,
            "string_param": "value",
            "bool_param": True,
        }
        tracker.log_params(params)

        mock_log_params.assert_called_once()
        logged_params = mock_log_params.call_args[0][0]
        assert logged_params["decimal_param"] == 1.5
        assert logged_params["int_param"] == 10
        assert logged_params["float_param"] == 0.5
        assert logged_params["string_param"] == "value"
        assert logged_params["bool_param"] is True
