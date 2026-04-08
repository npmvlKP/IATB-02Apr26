import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.ml.gnn_model import GNNModel

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_gnn_model_fit_and_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.ml.gnn_model.importlib.import_module",
        lambda _: SimpleNamespace(GCNConv=lambda *args: None),
    )
    model = GNNModel()
    nodes = [[Decimal("0.1"), Decimal("0.2")], [Decimal("0.2"), Decimal("0.3")]]
    edges = [(0, 1), (1, 0)]
    targets = [Decimal("0.15"), Decimal("0.25")]
    mae = model.fit(nodes, edges, targets)
    prediction = model.predict([Decimal("0.3"), Decimal("0.4")])
    assert mae >= Decimal("0")
    assert prediction.confidence <= Decimal("1")


def test_gnn_model_validates_inputs_and_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    model = GNNModel()
    with pytest.raises(ConfigError, match="trained before predict"):
        model.predict([Decimal("0.1")])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.fit([], [(0, 1)], [])
    with pytest.raises(ConfigError, match="equal length"):
        model.fit([[Decimal("0.1")]], [(0, 1)], [Decimal("0.1"), Decimal("0.2")])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.fit([[]], [(0, 1)], [Decimal("0.1")])
    with pytest.raises(ConfigError, match="edge_index cannot be empty"):
        model.fit([[Decimal("0.1")]], [], [Decimal("0.1")])
    monkeypatch.setattr(
        "iatb.ml.gnn_model.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="torch-geometric dependency"):
        model.initialize()
