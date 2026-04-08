import random
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from iatb.core.exceptions import ConfigError
from iatb.ml.transformer_model import TransformerModel

# Set deterministic seeds for reproducibility
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)


def test_transformer_model_train_and_predict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "iatb.ml.transformer_model.importlib.import_module", lambda _: SimpleNamespace()
    )
    model = TransformerModel()
    features = [[Decimal("0.1"), Decimal("0.2"), Decimal("0.3")] for _ in range(4)]
    targets = [Decimal("0.2"), Decimal("0.21"), Decimal("0.22"), Decimal("0.23")]
    mae = model.train(features, targets)
    prediction = model.predict([Decimal("0.1"), Decimal("0.2"), Decimal("0.3")])
    assert mae >= Decimal("0")
    assert prediction.score.is_finite()


def test_transformer_model_validates_inputs_and_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    model = TransformerModel()
    with pytest.raises(ConfigError, match="trained before predict"):
        model.predict([Decimal("0.1")])
    with pytest.raises(ConfigError, match="cannot be empty"):
        model.train([], [])
    with pytest.raises(ConfigError, match="equal length"):
        model.train([[Decimal("0.1")]], [Decimal("0.1"), Decimal("0.2")])
    with pytest.raises(ConfigError, match="empty rows"):
        model.train([[]], [Decimal("0.1")])
    monkeypatch.setattr(
        "iatb.ml.transformer_model.importlib.import_module",
        lambda _: (_ for _ in ()).throw(ModuleNotFoundError),
    )
    with pytest.raises(ConfigError, match="torch dependency"):
        model.initialize()
