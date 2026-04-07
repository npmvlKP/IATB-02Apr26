"""
Graph neural network wrapper for cross-asset relation signals.
"""

import importlib
from dataclasses import dataclass
from decimal import Decimal

from iatb.core.exceptions import ConfigError
from iatb.ml.base import PredictionResult, Predictor


@dataclass(frozen=True)
class GNNConfig:
    hidden_channels: int = 32
    num_layers: int = 2


class GNNModel(Predictor):
    """Deterministic approximation wrapper for GCN-style predictors."""

    def __init__(self, config: GNNConfig | None = None) -> None:
        self._config = config or GNNConfig()
        self._initialized = False
        self._trained = False
        self._graph_strength = Decimal("0")
        self._bias = Decimal("0")

    def initialize(self) -> None:
        _load_torch_geometric()
        self._initialized = True

    def fit(
        self,
        node_features: list[list[Decimal]],
        edge_index: list[tuple[int, int]],
        targets: list[Decimal],
    ) -> Decimal:
        _validate_graph_inputs(node_features, edge_index, targets)
        if not self._initialized:
            self.initialize()
        self._graph_strength = _mean([_mean(row) for row in node_features])
        self._bias = _mean(targets)
        self._trained = True
        predictions = [self._predict_score(row) for row in node_features]
        return _mae(predictions, targets)

    def predict(self, features: list[Decimal]) -> PredictionResult:
        if not self._trained:
            msg = "model must be trained before predict()"
            raise ConfigError(msg)
        score = self._predict_score(features)
        confidence = min(Decimal("1"), max(Decimal("0"), abs(score)))
        return PredictionResult(
            symbol="ENSEMBLE", score=score, confidence=confidence, regime_label="SIDEWAYS"
        )

    def _predict_score(self, features: list[Decimal]) -> Decimal:
        if not features:
            msg = "features cannot be empty"
            raise ConfigError(msg)
        node_value = _mean(features)
        return node_value + (self._graph_strength / Decimal("10")) - (self._bias / Decimal("100"))


def _load_torch_geometric() -> object:
    try:
        module = importlib.import_module("torch_geometric.nn")
    except ModuleNotFoundError as exc:
        msg = "torch-geometric dependency is required for GNNModel"
        raise ConfigError(msg) from exc
    conv = getattr(module, "GCNConv", None)
    if not callable(conv):
        msg = "torch_geometric.nn.GCNConv is unavailable"
        raise ConfigError(msg)
    return module


def _validate_graph_inputs(
    node_features: list[list[Decimal]],
    edge_index: list[tuple[int, int]],
    targets: list[Decimal],
) -> None:
    if not node_features or not targets:
        msg = "node_features and targets cannot be empty"
        raise ConfigError(msg)
    if len(node_features) != len(targets):
        msg = "node_features and targets must have equal length"
        raise ConfigError(msg)
    if any(not row for row in node_features):
        msg = "node_features rows cannot be empty"
        raise ConfigError(msg)
    if not edge_index:
        msg = "edge_index cannot be empty"
        raise ConfigError(msg)


def _mae(predictions: list[Decimal], targets: list[Decimal]) -> Decimal:
    errors = [abs(predictions[idx] - targets[idx]) for idx in range(len(targets))]
    return _mean(errors)


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
