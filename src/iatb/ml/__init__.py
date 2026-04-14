"""
Machine-learning module for predictive modeling and ensemble inference.
"""

from iatb.ml.base import PredictionResult, Predictor
from iatb.ml.feature_engine import FeatureEngineer
from iatb.ml.gnn_model import GNNConfig, GNNModel
from iatb.ml.hmm_model import HMMConfig, HMMRegimeModel
from iatb.ml.lstm_model import LSTMConfig, LSTMModel
from iatb.ml.model_registry import (
    ModelHealth,
    ModelRegistry,
    ModelStatus,
    RegistryStatus,
    get_registry,
)
from iatb.ml.predictor import EnsemblePredictor
from iatb.ml.readiness import check_ml_readiness
from iatb.ml.tracking import (
    ExperimentMetrics,
    ExperimentTracker,
    HyperparameterOptimizer,
    MLflowConfig,
    OptunaConfig,
    create_default_optimizer,
    create_default_tracking,
)
from iatb.ml.trainer import TrainingRunResult, UnifiedTrainer
from iatb.ml.transformer_model import TransformerConfig, TransformerModel

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
