# Point [4-2]: Experiment Tracking & Hyperparameter Optimization (MLflow + Optuna)

## Summary

Successfully implemented comprehensive experiment tracking and hyperparameter optimization using MLflow and Optuna for the IATB project.

## Implementation Details

### Core Components

1. **src/iatb/ml/tracking.py** (575 lines)
   - `MLflowConfig`: Configuration for MLflow tracking
   - `OptunaConfig`: Configuration for hyperparameter optimization
   - `ExperimentMetrics`: Data model for tracking experiment metrics
   - `ExperimentTracker`: MLflow experiment tracking with graceful error handling
   - `HyperparameterOptimizer`: Optuna-based hyperparameter optimization
   - Helper functions: `create_default_tracking()`, `create_default_optimizer()`

2. **tests/ml/test_tracking.py** (60 tests, 59 passed, 1 skipped)
   - Comprehensive test coverage for all components
   - Edge case and error handling tests
   - Integration tests with reward functions
   - 92% code coverage achieved

### Key Features

1. **Experiment Tracking**
   - Track parameters, metrics, and artifacts
   - Support for custom metrics
   - Graceful handling when MLflow is disabled
   - Integration with existing DRL reward functions (sharpe_ratio, sortino_ratio)

2. **Hyperparameter Optimization**
   - Optuna-based optimization with configurable trials
   - Support for maximize/minimize directions
   - Integration with MLflow for tracking optimization runs
   - Ability to run with or without tracker

3. **Error Handling**
   - Graceful degradation when MLflow/Optuna unavailable
   - ConfigError for configuration issues
   - Structured logging for debugging

4. **Decimal Precision**
   - All financial metrics use Decimal type
   - Conversion to float only at MLflow boundary (with comments)
   - No float in financial calculations

5. **PyTorch Support**
   - Optional PyTorch model logging
   - Graceful skip when PyTorch unavailable
   - No hard dependency on PyTorch

## Test Coverage

### Coverage Results
- **src/iatb/ml/tracking.py**: 92.00% (193/207 lines)
- **Total Tests**: 60 (59 passed, 1 skipped)
- **Test Categories**:
  - Configuration tests (MLflowConfig, OptunaConfig)
  - ExperimentMetrics tests
  - ExperimentTracker tests
  - HyperparameterOptimizer tests
  - Integration tests with reward functions
  - Helper function tests
  - Edge case and error handling tests

### Uncovered Lines (14 lines)
Most uncovered lines are:
- Line 26: Import guard (optional dependency)
- Lines 287, 291: Error logging paths
- Lines 339-347: PyTorch-specific code (skipped due to DLL issues)
- Lines 445-448, 449-451: Additional error handling paths

## Integration Points

### With RL Module
```python
from iatb.ml.tracking import ExperimentTracker, ExperimentMetrics
from iatb.rl.reward import sharpe_reward, sortino_reward

# Track DRL experiment
tracker = ExperimentTracker()
tracker.start_run()

returns = [...]  # Your returns data
sharpe = sharpe_reward(returns)
sortino = sortino_reward(returns)

metrics = ExperimentMetrics(
    sharpe_ratio=sharpe,
    sortino_ratio=sortino,
    num_trades=10
)
tracker.log_metrics(metrics)
tracker.end_run()
```

### With Backtesting Module
```python
from iatb.ml.tracking import ExperimentTracker, HyperparameterOptimizer
from iatb.backtesting import BacktestResult

# Track backtest metrics
tracker = ExperimentTracker()
result = run_backtest(...)

metrics = ExperimentMetrics(
    sharpe_ratio=result.sharpe_ratio,
    total_return=result.total_return,
    max_drawdown=result.max_drawdown,
    win_rate=result.win_rate
)
tracker.log_metrics(metrics)
```

### Hyperparameter Optimization
```python
from iatb.ml.tracking import HyperparameterOptimizer, ExperimentTracker
import optuna

optimizer = HyperparameterOptimizer(n_trials=100)
tracker = ExperimentTracker()

def objective(trial: optuna.Trial) -> float:
    # Suggest hyperparameters
    lr = trial.suggest_float("learning_rate", 1e-5, 1e-2)
    batch_size = trial.suggest_int("batch_size", 32, 256)
    
    # Train model and get metric
    metric = train_and_evaluate(lr, batch_size)
    return float(metric)

optimizer.optimize(objective, tracker=tracker)
best_params = optimizer.get_best_params()
```

## Usage Examples

### 1. Basic Experiment Tracking
```python
from iatb.ml.tracking import create_default_tracking

tracker = create_default_tracking()
tracker.start_run(run_name="my-experiment")

tracker.log_params({"param1": 1.5, "param2": 100})
tracker.log_metrics(ExperimentMetrics(sharpe_ratio=Decimal("2.5")))
tracker.end_run()
```

### 2. Hyperparameter Optimization
```python
from iatb.ml.tracking import create_default_optimizer

optimizer = create_default_optimizer(n_trials=50)

def objective(trial: optuna.Trial) -> float:
    x = trial.suggest_float("x", -10, 10)
    return (x - 2) ** 2

optimizer.optimize(objective)
print(f"Best params: {optimizer.get_best_params()}")
```

### 3. Disable Tracking
```python
from iatb.ml.tracking import MLflowConfig, ExperimentTracker

# Create tracker with tracking disabled
config = MLflowConfig(enable_tracking=False)
tracker = ExperimentTracker(config=config)

# All tracking operations become no-ops
tracker.start_run()  # Does nothing
tracker.log_metrics(...)  # Does nothing
```

## Quality Gates Status

- **G1 (Lint)**: ✓ Pass
- **G2 (Format)**: ✓ Pass
- **G3 (Types)**: ✓ Pass
- **G4 (Security)**: ✓ Pass
- **G5 (Secrets)**: ✓ Pass
- **G6 (Tests)**: ✓ Pass (59/60 passed, 1 skipped)
- **G7 (No Float in Finance)**: ✓ Pass (Decimal used throughout)
- **G8 (No Naive Datetime)**: ✓ Pass
- **G9 (No Print Statements)**: ✓ Pass (structured logging used)
- **G10 (Function Size)**: ✓ Pass (all functions ≤50 LOC)

## Known Issues

1. **PyTorch DLL Loading on Windows**
   - Issue: PyTorch fails to load DLLs in test environment
   - Impact: 1 test skipped (test_log_pytorch_model_success)
   - Workaround: Test marked with @pytest.mark.skipif
   - Production: Not affected (PyTorch is optional dependency)

2. **Total Project Coverage**
   - Current: 10.75% (overall project)
   - Tracking Module: 92.00% (target module)
   - Note: Low total coverage is expected as only tracking module is tested

## Dependencies

### Required
- mlflow>=2.10.0
- optuna>=3.5.0
- pydantic>=2.0.0
- python-dateutil>=2.8.0

### Optional
- torch>=2.0.0 (for PyTorch model logging)

## Next Steps

1. **Integration with Existing Modules**
   - Add tracking calls to RL training loops
   - Add tracking calls to backtesting engine
   - Add hyperparameter optimization for strategy parameters

2. **MLflow UI Setup**
   - Configure MLflow tracking server
   - Set up remote storage for artifacts
   - Configure authentication if needed

3. **Advanced Features**
   - Implement early stopping based on metrics
   - Add model registry support
   - Implement multi-objective optimization

4. **Documentation**
   - Add user guide for experiment tracking
   - Create examples for common use cases
   - Document MLflow server setup

## Testing

Run tests with:
```bash
poetry run pytest tests/ml/test_tracking.py --cov=src/iatb/ml/tracking --cov-fail-under=90 -v
```

Expected output:
- 59 passed, 1 skipped
- 92% coverage for tracking.py

## Git Commit

Branch: `feat/experiment-tracking`
Commit: `feat(ml): MLflow + Optuna experiment tracking and hyperparameter optimization`

Files changed:
- src/iatb/ml/tracking.py (new)
- tests/ml/test_tracking.py (new)
- POINT_4_2_EXECUTION_GUIDE.md (new)

## References

- MLflow Documentation: https://mlflow.org/docs/latest/index.html
- Optuna Documentation: https://optuna.readthedocs.io/en/stable/
- Pydantic Documentation: https://docs.pydantic.dev/latest/