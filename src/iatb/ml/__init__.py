"""
Machine-learning module for predictive modeling and ensemble inference.
"""

from iatb.ml.base import PredictionResult, Predictor
from iatb.ml.feature_engine import FeatureEngineer
from iatb.ml.model_registry import (
    ModelHealth,
    ModelRegistry,
    ModelStatus,
    RegistryStatus,
    get_registry,
)
from iatb.ml.predictor import EnsemblePredictor
from iatb.ml.readiness import check_ml_readiness

_LAZY_IMPORTS: dict[str, tuple[str, list[str]]] = {
    "gnn_model": ("iatb.ml.gnn_model", ["GNNConfig", "GNNModel"]),
    "hmm_model": ("iatb.ml.hmm_model", ["HMMConfig", "HMMRegimeModel"]),
    "lstm_model": ("iatb.ml.lstm_model", ["LSTMConfig", "LSTMModel"]),
    "tracking": (
        "iatb.ml.tracking",
        [
            "ExperimentMetrics",
            "ExperimentTracker",
            "HyperparameterOptimizer",
            "MLflowConfig",
            "OptunaConfig",
            "create_default_optimizer",
            "create_default_tracking",
        ],
    ),
    "trainer": ("iatb.ml.trainer", ["TrainingRunResult", "UnifiedTrainer"]),
    "transformer_model": (
        "iatb.ml.transformer_model",
        ["TransformerConfig", "TransformerModel"],
    ),
}

__all__ = [
    "EnsemblePredictor",
    "ExperimentMetrics",
    "ExperimentTracker",
    "FeatureEngineer",
    "GNNConfig",
    "GNNModel",
    "HyperparameterOptimizer",
    "HMMConfig",
    "HMMRegimeModel",
    "LSTMConfig",
    "LSTMModel",
    "MLflowConfig",
    "ModelHealth",
    "ModelRegistry",
    "ModelStatus",
    "OptunaConfig",
    "PredictionResult",
    "Predictor",
    "RegistryStatus",
    "TrainingRunResult",
    "TransformerConfig",
    "TransformerModel",
    "UnifiedTrainer",
    "check_ml_readiness",
    "create_default_optimizer",
    "create_default_tracking",
    "get_registry",
]


def __getattr__(name: str) -> object:
    for _module_path, names in _LAZY_IMPORTS.values():
        if name in names:
            import importlib

            mod = importlib.import_module(
                next(k for k, v in _LAZY_IMPORTS.items() if name in v[1])
            )
            return getattr(mod, name)
    msg = f"module 'iatb.ml' has no attribute {name!r}"
    raise AttributeError(msg)
