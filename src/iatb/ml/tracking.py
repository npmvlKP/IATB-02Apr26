"""
Experiment tracking and hyperparameter optimization using MLflow and Optuna.

Integrates with DRL reward functions and vectorbt backtesting to track
experiments, log metrics (Sharpe, Sortino), and optimize hyperparameters.
"""

import logging
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import mlflow
import optuna
from pydantic import BaseModel, Field

from iatb.core.exceptions import ConfigError

_LOGGER = logging.getLogger(__name__)

# PyTorch availability check - lazy import to avoid DLL loading issues
_PYTORCH_AVAILABLE: bool = False


class MLflowConfig(BaseModel):
    """Configuration for MLflow tracking.

    Attributes:
        tracking_uri: MLflow tracking server URI.
        experiment_name: Name of the experiment.
        enable_tracking: Whether to enable MLflow tracking.
        artifact_location: Optional custom artifact location.
    """

    tracking_uri: str = Field(
        default="file:///mlruns",
        description="MLflow tracking server URI",
    )
    experiment_name: str = Field(
        default="iatb-experiments",
        description="Name of the experiment",
    )
    enable_tracking: bool = Field(
        default=True,
        description="Whether to enable MLflow tracking",
    )
    artifact_location: str | None = Field(
        default=None,
        description="Optional custom artifact location",
    )


class OptunaConfig(BaseModel):
    """Configuration for Optuna hyperparameter optimization.

    Attributes:
        n_trials: Number of optimization trials.
        timeout: Optional timeout in seconds.
        direction: Optimization direction ("minimize" or "maximize").
        study_name: Name of the Optuna study.
        storage: Optional database storage URI.
    """

    n_trials: int = Field(
        default=100,
        description="Number of optimization trials",
        ge=1,
    )
    timeout: int | None = Field(
        default=None,
        description="Optional timeout in seconds",
    )
    direction: str = Field(
        default="maximize",
        description="Optimization direction ('minimize' or 'maximize')",
    )
    study_name: str = Field(
        default="iatb-optimization",
        description="Name of the Optuna study",
    )
    storage: str | None = Field(
        default=None,
        description="Optional database storage URI",
    )


class ExperimentMetrics(BaseModel):
    """Metrics collected during experiment tracking.

    Attributes:
        sharpe_ratio: Annualized Sharpe ratio.
        sortino_ratio: Annualized Sortino ratio.
        total_return: Total return percentage.
        max_drawdown: Maximum drawdown.
        win_rate: Win rate percentage.
        profit_factor: Profit factor.
        num_trades: Number of trades executed.
        custom_metrics: Additional custom metrics.
    """

    sharpe_ratio: Decimal | None = Field(
        default=None,
        description="Annualized Sharpe ratio",
    )
    sortino_ratio: Decimal | None = Field(
        default=None,
        description="Annualized Sortino ratio",
    )
    total_return: Decimal | None = Field(
        default=None,
        description="Total return percentage",
    )
    max_drawdown: Decimal | None = Field(
        default=None,
        description="Maximum drawdown",
    )
    win_rate: Decimal | None = Field(
        default=None,
        description="Win rate percentage",
    )
    profit_factor: Decimal | None = Field(
        default=None,
        description="Profit factor",
    )
    num_trades: int | None = Field(
        default=None,
        description="Number of trades executed",
    )
    custom_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metrics",
    )


class ExperimentTracker:
    """Main tracker for MLflow experiment tracking and logging.

    Handles MLflow experiment setup, parameter logging, metric logging,
    and model artifact management.

    Attributes:
        config: MLflow configuration.
        active_run: Active MLflow run.
    """

    def __init__(self, config: MLflowConfig | None = None) -> None:
        """Initialize the experiment tracker.

        Args:
            config: Optional MLflow configuration. If None, uses defaults.
        """
        self.config = config or MLflowConfig()
        self.active_run: mlflow.ActiveRun | None = None

        if self.config.enable_tracking:
            self._setup_mlflow()

    def _setup_mlflow(self) -> None:
        """Set up MLflow tracking configuration.

        Raises:
            ConfigError: If MLflow setup fails.
        """
        try:
            mlflow.set_tracking_uri(self.config.tracking_uri)

            # Create or get experiment
            experiment = mlflow.get_experiment_by_name(self.config.experiment_name)
            if experiment is None:
                experiment_id = mlflow.create_experiment(
                    name=self.config.experiment_name,
                    artifact_location=self.config.artifact_location,
                )
                _LOGGER.info(
                    "Created new MLflow experiment",
                    extra={
                        "experiment_name": self.config.experiment_name,
                        "experiment_id": experiment_id,
                    },
                )
            else:
                _LOGGER.info(
                    "Using existing MLflow experiment",
                    extra={
                        "experiment_name": self.config.experiment_name,
                        "experiment_id": experiment.experiment_id,
                    },
                )

        except Exception as e:
            msg = f"Failed to setup MLflow: {e!s}"
            _LOGGER.error("MLflow setup failed", extra={"error": str(e)})
            raise ConfigError(msg) from e

    def start_run(
        self,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
        description: str | None = None,
    ) -> None:
        """Start a new MLflow run.

        Args:
            run_name: Optional name for the run.
            tags: Optional tags for the run.
            description: Optional description for the run.
        """
        if not self.config.enable_tracking:
            _LOGGER.warning("MLflow tracking is disabled, skipping run start")
            return

        try:
            self.active_run = mlflow.start_run(
                run_name=run_name,
                tags=tags,
                description=description,
            )
            _LOGGER.info(
                "Started MLflow run",
                extra={
                    "run_id": self.active_run.info.run_id,
                    "run_name": run_name or "unnamed",
                },
            )
        except Exception as e:
            _LOGGER.error("Failed to start MLflow run", extra={"error": str(e)})
            raise

    def log_params(self, params: dict[str, Any]) -> None:
        """Log parameters to the current MLflow run.

        Args:
            params: Dictionary of parameters to log.
        """
        if not self.config.enable_tracking or self.active_run is None:
            return

        try:
            # Convert Decimal to float for MLflow logging
            mlflow_params: dict[str, Any] = {}
            for key, value in params.items():
                if isinstance(value, Decimal):
                    mlflow_params[key] = float(value)
                else:
                    mlflow_params[key] = value

            mlflow.log_params(mlflow_params)
            _LOGGER.debug(
                "Logged parameters",
                extra={"num_params": len(mlflow_params)},
            )
        except Exception as e:
            _LOGGER.error("Failed to log parameters", extra={"error": str(e)})

    def log_metrics(
        self,
        metrics: ExperimentMetrics,
        step: int | None = None,
    ) -> None:
        """Log metrics to the current MLflow run.

        Args:
            metrics: ExperimentMetrics object containing metrics.
            step: Optional step number for the metrics.
        """
        if not self.config.enable_tracking or self.active_run is None:
            return

        try:
            # Convert to dict and handle Decimal types
            mlflow_metrics: dict[str, float] = {}

            if metrics.sharpe_ratio is not None:
                mlflow_metrics["sharpe_ratio"] = float(metrics.sharpe_ratio)
            if metrics.sortino_ratio is not None:
                mlflow_metrics["sortino_ratio"] = float(metrics.sortino_ratio)
            if metrics.total_return is not None:
                mlflow_metrics["total_return"] = float(metrics.total_return)
            if metrics.max_drawdown is not None:
                mlflow_metrics["max_drawdown"] = float(metrics.max_drawdown)
            if metrics.win_rate is not None:
                mlflow_metrics["win_rate"] = float(metrics.win_rate)
            if metrics.profit_factor is not None:
                mlflow_metrics["profit_factor"] = float(metrics.profit_factor)
            if metrics.num_trades is not None:
                mlflow_metrics["num_trades"] = float(metrics.num_trades)

            # Add custom metrics
            for key, value in metrics.custom_metrics.items():
                if isinstance(value, Decimal):
                    mlflow_metrics[key] = float(value)
                elif isinstance(value, int | float):
                    mlflow_metrics[key] = float(value)

            mlflow.log_metrics(mlflow_metrics, step=step)
            _LOGGER.debug(
                "Logged metrics",
                extra={"num_metrics": len(mlflow_metrics), "step": step},
            )
        except Exception as e:
            _LOGGER.error("Failed to log metrics", extra={"error": str(e)})

    def log_artifact(self, file_path: str | Path) -> None:
        """Log an artifact file to the current MLflow run.

        Args:
            file_path: Path to the artifact file.
        """
        if not self.config.enable_tracking or self.active_run is None:
            return

        try:
            mlflow.log_artifact(str(file_path))
            _LOGGER.debug("Logged artifact", extra={"artifact": str(file_path)})
        except Exception as e:
            _LOGGER.error("Failed to log artifact", extra={"error": str(e)})

    def log_pytorch_model(
        self,
        model: Any,
        input_example: Any | None = None,
    ) -> None:
        """Log a PyTorch model to the current MLflow run.

        Args:
            model: PyTorch model to log.
            input_example: Optional example input for the model.
        """
        if not self.config.enable_tracking or self.active_run is None:
            return

        # Lazy import and check PyTorch availability
        global _PYTORCH_AVAILABLE
        if not _PYTORCH_AVAILABLE:
            try:
                import mlflow.pytorch  # noqa: F401

                _PYTORCH_AVAILABLE = True
                _LOGGER.debug("PyTorch became available for MLflow")
            except (ImportError, OSError):
                _LOGGER.warning("PyTorch not available, skipping PyTorch model logging")
                return

        try:
            mlflow.pytorch.log_model(model, "model", input_example=input_example)
            _LOGGER.info("Logged PyTorch model")
        except Exception as e:
            _LOGGER.error("Failed to log PyTorch model", extra={"error": str(e)})

    def end_run(self, status: str = "FINISHED") -> None:
        """End the current MLflow run.

        Args:
            status: Status of the run ("FINISHED", "FAILED", "KILLED").
        """
        if not self.config.enable_tracking or self.active_run is None:
            return

        try:
            mlflow.end_run(status=status)
            _LOGGER.info("Ended MLflow run", extra={"status": status})
            self.active_run = None
        except Exception as e:
            _LOGGER.error("Failed to end MLflow run", extra={"error": str(e)})


class HyperparameterOptimizer:
    """Hyperparameter optimizer using Optuna.

    Provides interface for running hyperparameter optimization
    studies with objective functions.

    Attributes:
        config: Optuna configuration.
        study: Optuna study object.
    """

    def __init__(self, config: OptunaConfig | None = None) -> None:
        """Initialize the hyperparameter optimizer.

        Args:
            config: Optional Optuna configuration. If None, uses defaults.
        """
        self.config = config or OptunaConfig()
        self.study: optuna.Study | None = None
        self._validate_direction()

    def _validate_direction(self) -> None:
        """Validate optimization direction.

        Raises:
            ConfigError: If direction is invalid.
        """
        if self.config.direction not in ["minimize", "maximize"]:
            msg = f"Invalid direction: {self.config.direction}. Must be 'minimize' or 'maximize'"
            _LOGGER.error("Invalid Optuna direction", extra={"direction": self.config.direction})
            raise ConfigError(msg)

    def create_study(
        self,
        load_if_exists: bool = True,
        sampler: optuna.samplers.BaseSampler | None = None,
        pruner: optuna.pruners.BasePruner | None = None,
    ) -> None:
        """Create or load an Optuna study.

        Args:
            load_if_exists: Whether to load existing study if it exists.
            sampler: Optional sampler for the study.
            pruner: Optional pruner for the study.
        """
        try:
            self.study = optuna.create_study(
                study_name=self.config.study_name,
                direction=self.config.direction,
                storage=self.config.storage,
                load_if_exists=load_if_exists,
                sampler=sampler,
                pruner=pruner,
            )
            _LOGGER.info(
                "Created Optuna study",
                extra={
                    "study_name": self.config.study_name,
                    "direction": self.config.direction,
                },
            )
        except Exception as e:
            _LOGGER.error("Failed to create Optuna study", extra={"error": str(e)})
            raise

    def optimize(
        self,
        objective: Callable[[optuna.Trial], float],
        tracker: ExperimentTracker | None = None,
    ) -> optuna.Study:
        """Run hyperparameter optimization.

        Args:
            objective: Objective function to optimize.
            tracker: Optional ExperimentTracker for logging.

        Returns:
            Optimized Optuna study.
        """
        if self.study is None:
            self.create_study()

        if self.study is None:
            msg = "Failed to create study"
            _LOGGER.error("Study creation failed")
            raise ConfigError(msg)

        try:
            self.study.optimize(
                lambda trial: self._run_trial(trial, objective, tracker),
                n_trials=self.config.n_trials,
                timeout=self.config.timeout,
            )
            _LOGGER.info(
                "Optimization completed",
                extra={
                    "n_trials": len(self.study.trials),
                    "best_value": self.study.best_value,
                },
            )
        except Exception as e:
            _LOGGER.error("Optimization failed", extra={"error": str(e)})
            raise

        return self.study

    def _run_trial(
        self,
        trial: optuna.Trial,
        objective: Callable[[optuna.Trial], float],
        tracker: ExperimentTracker | None = None,
    ) -> float:
        """Run a single optimization trial with optional MLflow tracking.

        Args:
            trial: Optuna trial object.
            objective: Objective function to evaluate.
            tracker: Optional ExperimentTracker for logging.

        Returns:
            Objective value for the trial.
        """
        # Log trial parameters if tracker is available
        if tracker is not None and tracker.config.enable_tracking:
            tracker.start_run(run_name=f"trial-{trial.number}")
            tracker.log_params(trial.params)

        # Run objective
        value = objective(trial)

        # Log objective value if tracker is available
        if tracker is not None and tracker.config.enable_tracking:
            tracker.log_metrics(
                ExperimentMetrics(custom_metrics={"objective_value": Decimal(str(value))})
            )
            tracker.end_run()

        return value

    def get_best_params(self) -> dict[str, Any]:
        """Get best parameters from the study.

        Returns:
            Dictionary of best hyperparameters.

        Raises:
            ConfigError: If study has not been created or has no trials.
        """
        if self.study is None:
            msg = "Study has not been created"
            _LOGGER.error("Study not created")
            raise ConfigError(msg)

        if len(self.study.trials) == 0:
            msg = "Study has no trials"
            _LOGGER.error("No trials in study")
            raise ConfigError(msg)

        return dict(self.study.best_params)

    def get_best_value(self) -> float:
        """Get best objective value from the study.

        Returns:
            Best objective value.

        Raises:
            ConfigError: If study has not been created or has no trials.
        """
        if self.study is None:
            msg = "Study has not been created"
            _LOGGER.error("Study not created")
            raise ConfigError(msg)

        if len(self.study.trials) == 0:
            msg = "Study has no trials"
            _LOGGER.error("No trials in study")
            raise ConfigError(msg)

        return float(self.study.best_value)


def create_default_tracking(
    tracking_uri: str | None = None,
    experiment_name: str | None = None,
) -> ExperimentTracker:
    """Create a default experiment tracker.

    Args:
        tracking_uri: Optional MLflow tracking URI.
        experiment_name: Optional experiment name.

    Returns:
        Configured ExperimentTracker instance.
    """
    config = MLflowConfig()
    if tracking_uri is not None:
        config.tracking_uri = tracking_uri
    if experiment_name is not None:
        config.experiment_name = experiment_name

    return ExperimentTracker(config=config)


def create_default_optimizer(
    n_trials: int | None = None,
    direction: str | None = None,
) -> HyperparameterOptimizer:
    """Create a default hyperparameter optimizer.

    Args:
        n_trials: Optional number of trials.
        direction: Optional optimization direction.

    Returns:
        Configured HyperparameterOptimizer instance.
    """
    config = OptunaConfig()
    if n_trials is not None:
        config.n_trials = n_trials
    if direction is not None:
        config.direction = direction

    return HyperparameterOptimizer(config=config)
